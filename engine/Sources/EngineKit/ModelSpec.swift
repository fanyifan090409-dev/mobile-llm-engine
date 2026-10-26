import Foundation

// 模型规格：GGUF 路径 + 量化档位展示名 + KV 上限（与内存预算联算，M3 完整实现）
public struct ModelSpec {
    public let fileURL: URL
    public let quant: String      // "Q4_K_M" 等，展示用
    public let context: Int       // KV 上限

    public init(fileURL: URL, quant: String, context: Int) {
        self.fileURL = fileURL
        self.quant = quant
        self.context = context
    }
}
