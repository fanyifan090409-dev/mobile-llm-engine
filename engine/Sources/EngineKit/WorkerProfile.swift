import Foundation

/// 工人配置：名字 + 训练同款 system prompt + 模型规格。
/// needsDateTable：日历/提醒工人必须 true（SFT20c 的日期表输入契约）。
public struct WorkerProfile: Sendable {
    public let name: String
    public let systemPrompt: String
    public let modelURL: URL
    public let quant: String
    public let context: Int
    public let thinkTags: Bool
    public let needsDateTable: Bool

    public init(name: String, systemPrompt: String, modelURL: URL, quant: String,
                context: Int = 4096, thinkTags: Bool = true, needsDateTable: Bool) {
        self.name = name
        self.systemPrompt = systemPrompt
        self.modelURL = modelURL
        self.quant = quant
        self.context = context
        self.thinkTags = thinkTags
        self.needsDateTable = needsDateTable
    }

    var modelSpec: ModelSpec {
        ModelSpec(fileURL: modelURL, quant: quant, context: context, thinkTags: thinkTags)
    }
}
