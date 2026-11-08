import Foundation
import SherpaOnnx

// P0 冒烟：确认官方 SPM 包已链接，语音能力后续在 Modality/ 下接入
enum VoicePOC {
    static var versionLine: String {
        "sherpa-onnx \(getSherpaOnnxVersion()) · onnxruntime \(getSherpaOnnxOnnxruntimeVersion())"
    }
}
