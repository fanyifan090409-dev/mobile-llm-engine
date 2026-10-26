import Foundation

// 模型规格：GGUF 路径 + 量化档位展示名 + KV 上限（与内存预算联算，M3 完整实现）
public struct ModelSpec {
    public let fileURL: URL
    public let quant: String      // "Q4_K_M" 等，展示用
    public let context: Int       // KV 上限
    /// 空思考块注入（/no_think 项）：SFT3 起训练模板 enable_thinking=false 在每个 assistant
    /// 回合头后注入官方空思考块 <think>\n\n</think>\n\n，训练/推理必须同开同关。
    /// SFT2 及官方原版模型训练时无此块 → 默认关，避免分布偏移
    public let thinkTags: Bool

    public init(fileURL: URL, quant: String, context: Int, thinkTags: Bool = false) {
        self.fileURL = fileURL
        self.quant = quant
        self.context = context
        self.thinkTags = thinkTags
    }
}
