#import <Foundation/Foundation.h>

NS_ASSUME_NONNULL_BEGIN

// Texo ONNX 推理（ORT C API 薄封装）：encoder 一次，decoder 逐 token 贪心。
// 线程模型：单实例串行使用（TexoOCR 侧加锁），模型 25MB、CPU EP。
@interface TexoRunner : NSObject

- (nullable instancetype)initWithEncoderPath:(NSString *)encoderPath
                                 decoderPath:(NSString *)decoderPath
                                       error:(NSError **)error;

// pixels: float32 NCHW [1,3,384,384]，已按 Texo 均值/方差归一化。
// 返回 token id（不含起始 token 与 eos）。
- (nullable NSArray<NSNumber *> *)generateTokensWithPixels:(NSData *)pixels
                                                 maxLength:(NSInteger)maxLength
                                                     error:(NSError **)error;

@end

NS_ASSUME_NONNULL_END
