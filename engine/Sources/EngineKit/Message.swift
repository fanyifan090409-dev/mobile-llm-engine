// 对话消息：role 取值 system/user/assistant/tool。
// tool 消息带 toolCallId（对齐训练轨迹的 call_xxx；Qwen3 XML 模板不把它渲染进 token 流，仅结构层保留）
public struct Message: Codable, Equatable {
    public let role: String
    public let content: String
    public let toolCallId: String?

    public init(role: String, content: String, toolCallId: String? = nil) {
        self.role = role
        self.content = content
        self.toolCallId = toolCallId
    }
}
