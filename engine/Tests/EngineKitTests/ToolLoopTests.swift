import Testing
import Foundation
@testable import EngineKit

// T2 验收：ToolLoop 决策核心全链路四路径（docs/plans/工具执行层-ToolKit.md 第 6 节 T2）
// 正常调用 / 缺参失败回填 / 幻觉工具名拒绝 / 超时兜底 + 轮数与失败上限

private func calendarSpec() -> ToolSpec {
    ToolSpec(
        name: "add_calendar_event",
        description: "向用户日历添加事件",
        parameters: [
            ToolParameterSpec(name: "title", type: "string", description: "事件名称", required: true),
            ToolParameterSpec(name: "start_time", type: "string", description: "开始时间 YYYY-MM-DD HH:mm", required: true,
                              pattern: #"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$"#),
            ToolParameterSpec(name: "end_time", type: "string", description: "结束时间 YYYY-MM-DD HH:mm", required: true,
                              pattern: #"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$"#),
        ])
}

private func toolCallText(_ json: String) -> String {
    "<tool_call>\n\(json)\n</tool_call>"
}

/// 正常工具：返回 ok + 事件 ID
private struct EchoTool: LocalTool {
    let spec: ToolSpec
    func execute(_ arguments: [String: Any]) async throws -> ToolResult {
        ToolResult(status: "ok", content: "evt_echo")
    }
}

/// 取消工具：模拟用户确认时点「否」——业务失败（不抛错，status=error）
private struct CancelTool: LocalTool {
    let spec: ToolSpec
    func execute(_ arguments: [String: Any]) async throws -> ToolResult {
        ToolResult(status: "error", content: "用户取消了操作，未写入日历")
    }
}

/// 慢工具：睡 10 秒触发超时兜底
private struct SlowTool: LocalTool {
    let spec: ToolSpec
    func execute(_ arguments: [String: Any]) async throws -> ToolResult {
        try await Task.sleep(nanoseconds: 10_000_000_000)
        return ToolResult(status: "ok", content: "evt_slow")
    }
}

private func feedbackJSON(_ content: String) -> [String: Any]? {
    guard let data = content.data(using: .utf8) else { return nil }
    return (try? JSONSerialization.jsonObject(with: data)) as? [String: Any]
}

@Suite("ToolLoop 全链路四路径")
struct ToolLoopTests {

    @Test("正常调用：解析→校验→执行→回填 ok JSON + executed 事件")
    func normalCall() async {
        let tool = EchoTool(spec: calendarSpec())
        let text = toolCallText(#"{"name": "add_calendar_event", "arguments": {"title": "会议", "start_time": "2026-11-05 14:30", "end_time": "2026-11-05 15:30"}}"#)
        let outcome = await ToolLoop.process(accumulated: text, tools: [tool], round: 1, validationFailures: 0)

        guard case .feedback(let content, let event) = outcome else {
            Issue.record("合法调用应回填反馈")
            return
        }
        #expect(event.status == .executed)
        #expect(event.toolName == "add_calendar_event")
        let json = feedbackJSON(content)
        #expect(json?["status"] as? String == "ok")
        #expect(json?["event_id"] as? String == "evt_echo")
    }

    @Test("缺参失败回填：校验失败不执行，回填 error JSON + rejected 事件")
    func missingParameterFeedback() async {
        let tool = EchoTool(spec: calendarSpec())
        // 缺 end_time
        let text = toolCallText(#"{"name": "add_calendar_event", "arguments": {"title": "会议", "start_time": "2026-11-05 14:30"}}"#)
        let outcome = await ToolLoop.process(accumulated: text, tools: [tool], round: 1, validationFailures: 0)

        guard case .feedback(let content, let event) = outcome else {
            Issue.record("缺参应回填纠错")
            return
        }
        #expect(event.status == .rejected)
        let json = feedbackJSON(content)
        #expect(json?["status"] as? String == "error")
        #expect((json?["message"] as? String)?.contains("end_time") == true)
    }

    @Test("业务失败（用户取消）：不抛错但 status=error → failed 事件 + error 回填")
    func userCancelMappedToFailed() async {
        let tool = CancelTool(spec: calendarSpec())
        let text = toolCallText(#"{"name": "add_calendar_event", "arguments": {"title": "会议", "start_time": "2026-11-05 14:30", "end_time": "2026-11-05 15:30"}}"#)
        let outcome = await ToolLoop.process(accumulated: text, tools: [tool], round: 1, validationFailures: 0)

        guard case .feedback(let content, let event) = outcome else {
            Issue.record("用户取消应回填错误")
            return
        }
        #expect(event.status == .failed)
        #expect(event.resultText.contains("取消"))
        #expect(feedbackJSON(content)?["status"] as? String == "error")
    }

    @Test("幻觉工具名拒绝：白名单外的工具不执行，回填拒绝文案")
    func unknownToolRejected() async {
        let tool = EchoTool(spec: calendarSpec())
        let text = toolCallText(#"{"name": "delete_all_events", "arguments": {}}"#)
        let outcome = await ToolLoop.process(accumulated: text, tools: [tool], round: 1, validationFailures: 0)

        guard case .feedback(_, let event) = outcome else {
            Issue.record("幻觉工具名应回填拒绝")
            return
        }
        #expect(event.status == .rejected)
        #expect(event.toolName == "delete_all_events")
    }

    @Test("超时兜底：工具执行超 5 秒 → failed 事件 + 超时文案")
    func timeoutFallback() async {
        let tool = SlowTool(spec: calendarSpec())
        let text = toolCallText(#"{"name": "add_calendar_event", "arguments": {"title": "会议", "start_time": "2026-11-05 14:30", "end_time": "2026-11-05 15:30"}}"#)
        let start = Date()
        let outcome = await ToolLoop.process(accumulated: text, tools: [tool], round: 1, validationFailures: 0, timeout: 0.5)
        let elapsed = Date().timeIntervalSince(start)

        guard case .feedback(let content, let event) = outcome else {
            Issue.record("超时应回填错误")
            return
        }
        #expect(event.status == .failed)
        #expect((feedbackJSON(content)?["message"] as? String)?.contains("超时") == true)
        #expect(elapsed < 5, "0.5s 超时不该等满 10s")
    }

    @Test("轮数上限：第 4 轮直接终止（stop）")
    func roundLimit() async {
        let tool = EchoTool(spec: calendarSpec())
        let text = toolCallText(#"{"name": "add_calendar_event", "arguments": {"title": "会议", "start_time": "2026-11-05 14:30", "end_time": "2026-11-05 15:30"}}"#)
        let outcome = await ToolLoop.process(accumulated: text, tools: [tool], round: 4, validationFailures: 0)
        guard case .stop = outcome else {
            Issue.record("第 4 轮应终止循环")
            return
        }
    }

    @Test("连续校验失败上限：两次拒绝后终止")
    func validationFailureLimit() async {
        let tool = EchoTool(spec: calendarSpec())
        let text = toolCallText(#"{"name": "add_calendar_event", "arguments": {}}"#)
        let outcome = await ToolLoop.process(accumulated: text, tools: [tool], round: 1, validationFailures: 2)
        guard case .stop = outcome else {
            Issue.record("连续失败 2 次后应终止")
            return
        }
    }

    @Test("纯文本无工具调用：noToolCall 继续正常生成")
    func plainTextNoToolCall() async {
        let tool = EchoTool(spec: calendarSpec())
        let outcome = await ToolLoop.process(accumulated: "今天天气不错。", tools: [tool], round: 1, validationFailures: 0)
        guard case .noToolCall = outcome else {
            Issue.record("纯文本应返回 noToolCall")
            return
        }
    }
}
