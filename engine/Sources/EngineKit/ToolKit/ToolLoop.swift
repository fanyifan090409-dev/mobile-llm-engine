import Foundation

/// 工具循环决策核心：给一段模型输出（含 </tool_call>），决定下一步动作并执行工具。
/// 与 EngineCore 解耦——解码/回填由 EngineCore 负责，这里只做
/// 解析 → 白名单 → schema 校验 → 执行（超时）→ 定策，单测可用 mock 工具全路径覆盖。
public enum ToolLoop {

    /// 单轮决策结果
    public enum TurnOutcome {
        /// 输出里没有完整工具调用，继续正常生成
        case noToolCall
        /// 回填工具结果后继续生成：content 为 role="tool" 消息体（JSON 字符串，对齐训练轨迹形状）
        case feedback(content: String, event: ToolCallEvent)
        /// 终止循环（轮数用尽 / 连续校验失败），转纯文本兜底
        case stop
    }

    public enum ToolLoopError: Error {
        case timeout
    }

    /// 循环上限 3 轮（计划第 3 节）；校验失败只回填改一次，再失败终止
    public static let maxRounds = 3
    public static let maxValidationFailures = 2

    /// - Parameters:
    ///   - round: 本次调用是第几轮（从 1 起）
    ///   - validationFailures: 到目前为连续拒绝/校验失败次数
    ///   - timeout: 工具执行超时秒数；nil=不限时。默认 5s 是纯计算型工具的兜底；
    ///     含用户确认等待的工具（日历写入）由集成方传 nil——确认时长由用户决定，
    ///     引擎不能替用户设限（计划第 9 节拍板确认下沉工具内部后的修正）
    public static func process(
        accumulated: String,
        tools: [LocalTool],
        round: Int,
        validationFailures: Int,
        timeout: Double? = 5.0
    ) async -> TurnOutcome {
        guard round <= maxRounds else { return .stop }
        guard validationFailures < maxValidationFailures else { return .stop }

        guard let parsed = ToolCallParser.parseCall(from: accumulated) else {
            return .noToolCall
        }

        // 白名单拒绝：幻觉工具名不执行（计划第 3 节②）
        guard let tool = tools.first(where: { $0.spec.name == parsed.name }) else {
            let event = ToolCallEvent(
                toolName: parsed.name, arguments: [:], status: .rejected,
                resultText: "工具 \(parsed.name) 不在白名单")
            return .feedback(content: Self.errorJSON("没有名为 \(parsed.name) 的工具，无法执行"), event: event)
        }

        // schema 校验（必填/类型/正则）
        let validated: [String: String]
        switch ToolCallValidator.validate(spec: tool.spec, arguments: parsed.arguments) {
        case .success(let args):
            validated = args
        case .failure(let err):
            let event = ToolCallEvent(
                toolName: parsed.name, arguments: [:], status: .rejected,
                resultText: err.description)
            return .feedback(content: Self.errorJSON(err.description), event: event)
        }

        do {
            let result = try await Self.withTimeout(timeout) {
                try await tool.execute(validated)
            }
            // 工具自身业务失败（如用户取消、写入被拒）≠ 抛错：status 字段区分，事件如实上报
            if result.status == "ok" {
                let event = ToolCallEvent(
                    toolName: parsed.name, arguments: validated, status: .executed,
                    resultText: result.content)
                return .feedback(content: Self.okJSON(result.content), event: event)
            } else {
                let event = ToolCallEvent(
                    toolName: parsed.name, arguments: validated, status: .failed,
                    resultText: result.content)
                return .feedback(content: Self.errorJSON(result.content), event: event)
            }
        } catch ToolLoopError.timeout {
            let event = ToolCallEvent(
                toolName: parsed.name, arguments: validated, status: .failed,
                resultText: "工具执行超时")
            return .feedback(content: Self.errorJSON("工具执行超时，请稍后重试"), event: event)
        } catch {
            let event = ToolCallEvent(
                toolName: parsed.name, arguments: validated, status: .failed,
                resultText: "\(error)")
            return .feedback(content: Self.errorJSON("工具执行失败：\(error)"), event: event)
        }
    }

    /// 成功回填：{"status": "ok", "event_id": "..."}（训练轨迹同款形状）
    private static func okJSON(_ eventID: String) -> String {
        jsonString(["status": "ok", "event_id": eventID])
    }

    /// 失败回填：{"status": "error", "message": "..."}（校验失败/超时/抛错共用）
    private static func errorJSON(_ message: String) -> String {
        jsonString(["status": "error", "message": message])
    }

    private static func jsonString(_ dict: [String: String]) -> String {
        guard let data = try? JSONSerialization.data(withJSONObject: dict, options: []) else { return "{}" }
        return String(data: data, encoding: .utf8) ?? "{}"
    }

    /// 执行超时：nil 不限时（含用户确认等待的工具用）；
    /// 有值时 race 一个 sleep 任务，到期抛 .timeout 并取消工具任务
    private static func withTimeout<T: Sendable>(
        _ seconds: Double?,
        _ body: @escaping () async throws -> T
    ) async throws -> T {
        guard let seconds else { return try await body() }
        return try await withThrowingTaskGroup(of: T.self) { group in
            group.addTask { try await body() }
            group.addTask {
                try await Task.sleep(nanoseconds: UInt64(seconds * 1_000_000_000))
                throw ToolLoopError.timeout
            }
            guard let first = try await group.next() else { throw ToolLoopError.timeout }
            group.cancelAll()
            return first
        }
    }
}
