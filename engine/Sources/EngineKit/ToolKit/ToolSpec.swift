import Foundation

// ToolKit 契约（docs/plans/工具执行层-ToolKit.md 已拍板）：
// 引擎层纯 Swift 零平台依赖；工具调用格式对齐训练数据（Qwen3 XML <tool_call> 内嵌 JSON）

public struct ToolParameterSpec: Codable, Sendable {
    public let name: String
    /// JSON Schema 类型：string / integer / number / boolean
    public let type: String
    /// 给模型的参数说明（多工具清单注入期使用）
    public let description: String
    public let required: Bool
    /// 可选正则约束（与训练期 QC 同款规则，如时间 `^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$`）
    public let pattern: String?

    public init(name: String, type: String, description: String, required: Bool, pattern: String? = nil) {
        self.name = name
        self.type = type
        self.description = description
        self.required = required
        self.pattern = pattern
    }
}

public struct ToolSpec: Codable, Sendable {
    public let name: String
    public let description: String
    public let parameters: [ToolParameterSpec]
    /// 工具定义触发文本：注册此工具时引擎作为 system 消息注入。
    /// 必须与 SFT3 训练数据前插的 system 文本逐字一致（SYNTH_SYS_SCHED1），
    /// 否则训练/推理分布偏移（tech-debt #2 根因）；nil = 不注入（纯文本模型可用）
    public let usagePrompt: String?

    public init(name: String, description: String, parameters: [ToolParameterSpec], usagePrompt: String? = nil) {
        self.name = name
        self.description = description
        self.parameters = parameters
        self.usagePrompt = usagePrompt
    }

    /// 参数名 → 规格索引（校验与清单生成共用）
    public func parameter(named name: String) -> ToolParameterSpec? {
        parameters.first { $0.name == name }
    }
}

/// 工具执行结果，回填给模型的格式与训练数据一致：{"status": "ok"|"error", ...}
public struct ToolResult: Codable, Sendable {
    public let status: String
    /// ok 时为给模型的结果描述（如 event_id）；error 时为可读错误原因
    public let content: String

    public init(status: String, content: String) {
        self.status = status
        self.content = content
    }
}
