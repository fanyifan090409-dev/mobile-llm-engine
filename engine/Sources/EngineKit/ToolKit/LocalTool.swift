import Foundation

/// 本地工具协议：应用层（apps/）实现，引擎层只依赖此协议执行。
/// execute 内部自行处理确认弹窗（写操作默认每次确认是产品决策，确认逻辑下沉到工具实现，
/// 引擎只负责 await，见 docs/plans/工具执行层-ToolKit.md 第 3 节）。
public protocol LocalTool {
    var spec: ToolSpec { get }
    func execute(_ arguments: [String: Any]) async throws -> ToolResult
}

/// 工具调用的终态：引擎把一次完整工具调用作为事件发给上层（UI 展示/日志用）
public enum ToolCallStatus: Sendable {
    /// 校验通过且工具执行成功
    case executed
    /// 校验失败（工具名不在白名单 / 参数不合 schema），未执行
    case rejected
    /// 校验通过但执行抛错或超时
    case failed
}

/// 单次工具调用事件：名字、入参、终态、结果文本（ok 为 event_id 等描述；错误为原因）
public struct ToolCallEvent: Sendable {
    public let toolName: String
    public let arguments: [String: String]
    public let status: ToolCallStatus
    public let resultText: String

    public init(toolName: String, arguments: [String: String], status: ToolCallStatus, resultText: String) {
        self.toolName = toolName
        self.arguments = arguments
        self.status = status
        self.resultText = resultText
    }
}
