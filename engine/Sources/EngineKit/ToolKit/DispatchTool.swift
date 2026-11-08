import Foundation

/// 领队的 dispatch_to_worker 工具：把子任务交给工人模型，返回工人的工具调用或执行结果。
/// 回填形状用 .result（领队 SFT20 训练数据是 {"status":"ok","result":"…"}）。
public struct DispatchTool: LocalTool {
    /// 工人工具执行器：应用层注入（日历/提醒写 EventKit）；不注入则只返回工人的工具调用，不落盘。
    public typealias Executor = (WorkerToolCall) async throws -> ToolResult

    public let spec = ToolSpec(
        name: "dispatch_to_worker",
        description: "把子任务派给工人模型执行",
        parameters: [
            ToolParameterSpec(name: "worker", type: "string", description: "工人名，如 calendar_worker", required: true),
            ToolParameterSpec(name: "task", type: "string", description: "完整子任务描述", required: true),
        ],
        feedbackStyle: .result)

    private let dispatcher: WorkerDispatcher
    private let executor: Executor?
    private let now: () -> Date
    private let onStage: (@Sendable (DispatchStage) -> Void)?

    public init(dispatcher: WorkerDispatcher, executor: Executor? = nil,
                now: @escaping () -> Date = { Date() },
                onStage: (@Sendable (DispatchStage) -> Void)? = nil) {
        self.dispatcher = dispatcher
        self.executor = executor
        self.now = now
        self.onStage = onStage
    }

    public func execute(_ arguments: [String: Any]) async throws -> ToolResult {
        guard let worker = arguments["worker"] as? String,
              let task = arguments["task"] as? String else {
            onStage?(.finished(worker: "", toolName: "", status: "error",
                               detail: "派单参数缺 worker 或 task"))
            return ToolResult(status: "error", content: "派单参数缺 worker 或 task")
        }
        let call: WorkerToolCall
        do {
            call = try await dispatcher.dispatch(worker: worker, task: task, now: now(), onStage: onStage)
        } catch {
            onStage?(.finished(worker: worker, toolName: "", status: "error",
                               detail: "工人执行失败：\(error)"))
            return ToolResult(status: "error", content: "工人执行失败：\(error)")
        }

        if let executor {
            do {
                let result = try await executor(call)
                onStage?(.finished(worker: call.worker, toolName: call.toolName,
                                   status: result.status, detail: result.content))
                return result
            } catch {
                onStage?(.finished(worker: call.worker, toolName: call.toolName,
                                   status: "error", detail: "工人工具执行失败：\(error)"))
                return ToolResult(status: "error", content: "工人工具执行失败：\(error)")
            }
        }
        let json = (try? JSONSerialization.data(withJSONObject: call.arguments, options: [.sortedKeys]))
            .flatMap { String(data: $0, encoding: .utf8) } ?? "{}"
        let content = "已生成工具调用（未执行）：\(call.toolName) \(json)"
        onStage?(.finished(worker: call.worker, toolName: call.toolName, status: "ok", detail: content))
        return ToolResult(status: "ok", content: content)
    }
}
