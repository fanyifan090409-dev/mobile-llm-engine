#import "TexoRunner.h"
#include <onnxruntime_c_api.h>
#include <vector>

static NSError *TexoError(const OrtApi *api, OrtStatus *status) {
    NSString *message = status ? [NSString stringWithUTF8String:api->GetErrorMessage(status)] : @"未知错误";
    if (status) api->ReleaseStatus(status);
    return [NSError errorWithDomain:@"TexoRunner" code:1
                           userInfo:@{NSLocalizedDescriptionKey: message ?: @"未知错误"}];
}

@implementation TexoRunner {
    const OrtApi *_api;
    OrtEnv *_env;
    OrtSession *_encoder;
    OrtSession *_decoder;
    OrtMemoryInfo *_memoryInfo;
}

- (nullable instancetype)initWithEncoderPath:(NSString *)encoderPath
                                 decoderPath:(NSString *)decoderPath
                                       error:(NSError **)error {
    self = [super init];
    if (!self) return nil;
    _api = OrtGetApiBase()->GetApi(ORT_API_VERSION);
    if (!_api) {
        if (error) *error = [NSError errorWithDomain:@"TexoRunner" code:1
                                            userInfo:@{NSLocalizedDescriptionKey: @"ONNX Runtime API 版本不匹配"}];
        return nil;
    }
    OrtStatus *status = _api->CreateEnv(ORT_LOGGING_LEVEL_WARNING, "texo", &_env);
    if (status) {
        if (error) *error = TexoError(_api, status);
        return nil;
    }
    OrtSessionOptions *options = nullptr;
    status = _api->CreateSessionOptions(&options);
    if (status) {
        if (error) *error = TexoError(_api, status);
        return nil;
    }
    _api->SetIntraOpNumThreads(options, 4);
    _api->SetSessionGraphOptimizationLevel(options, ORT_ENABLE_ALL);
    status = _api->CreateSession(_env, encoderPath.fileSystemRepresentation, options, &_encoder);
    if (status) {
        _api->ReleaseSessionOptions(options);
        if (error) *error = TexoError(_api, status);
        return nil;
    }
    status = _api->CreateSession(_env, decoderPath.fileSystemRepresentation, options, &_decoder);
    _api->ReleaseSessionOptions(options);
    if (status) {
        if (error) *error = TexoError(_api, status);
        return nil;
    }
    status = _api->CreateCpuMemoryInfo(OrtArenaAllocator, OrtMemTypeDefault, &_memoryInfo);
    if (status) {
        if (error) *error = TexoError(_api, status);
        return nil;
    }
    return self;
}

- (nullable NSArray<NSNumber *> *)generateTokensWithPixels:(NSData *)pixels
                                                 maxLength:(NSInteger)maxLength
                                                     error:(NSError **)error {
    @synchronized (self) {
        if (!_encoder || !_decoder) {
            if (error) *error = [NSError errorWithDomain:@"TexoRunner" code:2
                                                userInfo:@{NSLocalizedDescriptionKey: @"Texo 会话未初始化"}];
            return nil;
        }
        const int64_t pixelShape[4] = {1, 3, 384, 384};
        OrtValue *pixelValue = nullptr;
        OrtStatus *status = _api->CreateTensorWithDataAsOrtValue(
            _memoryInfo, (void *)pixels.bytes, pixels.length, pixelShape, 4,
            ONNX_TENSOR_ELEMENT_DATA_TYPE_FLOAT, &pixelValue);
        if (status) {
            if (error) *error = TexoError(_api, status);
            return nil;
        }
        const char *encoderInputs[] = {"pixel_values"};
        const char *encoderOutputs[] = {"last_hidden_state"};
        OrtValue *hidden = nullptr;
        status = _api->Run(_encoder, nullptr, encoderInputs, &pixelValue, 1, encoderOutputs, 1, &hidden);
        _api->ReleaseValue(pixelValue);
        if (status) {
            if (error) *error = TexoError(_api, status);
            return nil;
        }

        std::vector<int64_t> ids = {0};
        for (NSInteger step = 0; step < maxLength; step++) {
            const int64_t idShape[2] = {1, (int64_t)ids.size()};
            OrtValue *idValue = nullptr;
            status = _api->CreateTensorWithDataAsOrtValue(
                _memoryInfo, ids.data(), ids.size() * sizeof(int64_t), idShape, 2,
                ONNX_TENSOR_ELEMENT_DATA_TYPE_INT64, &idValue);
            if (status) {
                _api->ReleaseValue(hidden);
                if (error) *error = TexoError(_api, status);
                return nil;
            }
            const char *decoderInputs[] = {"input_ids", "encoder_hidden_states"};
            OrtValue *decoderValues[2] = {idValue, hidden};
            const char *decoderOutputs[] = {"logits"};
            OrtValue *logits = nullptr;
            status = _api->Run(_decoder, nullptr, decoderInputs, decoderValues, 2, decoderOutputs, 1, &logits);
            _api->ReleaseValue(idValue);
            if (status) {
                _api->ReleaseValue(hidden);
                if (error) *error = TexoError(_api, status);
                return nil;
            }

            float *data = nullptr;
            status = _api->GetTensorMutableData(logits, (void **)&data);
            OrtTensorTypeAndShapeInfo *info = nullptr;
            if (!status) status = _api->GetTensorTypeAndShape(logits, &info);
            if (status) {
                _api->ReleaseValue(logits);
                _api->ReleaseValue(hidden);
                if (error) *error = TexoError(_api, status);
                return nil;
            }
            size_t dimensionCount = 0;
            _api->GetDimensionsCount(info, &dimensionCount);
            std::vector<int64_t> dimensions(dimensionCount);
            _api->GetDimensions(info, dimensions.data(), dimensionCount);
            _api->ReleaseTensorTypeAndShapeInfo(info);
            if (dimensions.size() != 3) {
                _api->ReleaseValue(logits);
                _api->ReleaseValue(hidden);
                if (error) *error = [NSError errorWithDomain:@"TexoRunner" code:3
                                                    userInfo:@{NSLocalizedDescriptionKey: @"decoder 输出维度异常"}];
                return nil;
            }
            const int64_t sequenceLength = dimensions[1];
            const int64_t vocabSize = dimensions[2];
            const float *last = data + (sequenceLength - 1) * vocabSize;
            int best = 0;
            for (int64_t i = 1; i < vocabSize; i++) {
                if (last[i] > last[best]) best = (int)i;
            }
            _api->ReleaseValue(logits);
            if (best == 2) break; // </s>
            ids.push_back(best);
        }
        _api->ReleaseValue(hidden);

        NSMutableArray<NSNumber *> *tokens = [NSMutableArray arrayWithCapacity:ids.size()];
        for (size_t i = 1; i < ids.size(); i++) {
            [tokens addObject:@(ids[i])];
        }
        return tokens;
    }
}

- (void)dealloc {
    if (_memoryInfo) _api->ReleaseMemoryInfo(_memoryInfo);
    if (_decoder) _api->ReleaseSession(_decoder);
    if (_encoder) _api->ReleaseSession(_encoder);
    if (_env) _api->ReleaseEnv(_env);
}

@end
