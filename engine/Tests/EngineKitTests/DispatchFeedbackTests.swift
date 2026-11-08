import Testing
import Foundation
@testable import EngineKit

private struct ResultTool: LocalTool {
    let spec = ToolSpec(
        name: "dispatch_to_worker",
        description: "派单",
        parameters: [
            ToolParameterSpec(name: "worker", type: "string", description: "工人", required: true),
            ToolParameterSpec(name: "task", type: "string", description: "任务", required: true),
        ],
        feedbackStyle: .result)
    let status: String
    func execute(_ arguments: [String: Any]) async throws -> ToolResult {
        ToolResult(status: status, content: status == "ok" ? "已添加日历事件" : "时间表达无法解析")
    }
}

private func dispatchText() -> String {
    #"<tool_call>{"name": "dispatch_to_worker", "arguments": {"worker": "calendar_worker", "task": "明天下午三点开会"}}</tool_call>"#
}

@Suite("ToolLoop feedbackStyle=result")
struct DispatchFeedbackTests {

    @Test("成功回填：{\"status\":\"ok\",\"result\":\"…\"}，不含 event_id")
    func resultStyleOK() async {
        let outcome = await ToolLoop.process(accumulated: dispatchText(), tools: [ResultTool(status: "ok")],
                                             round: 1, validationFailures: 0)
        guard case .feedback(let content, _) = outcome else {
            Issue.record("应回填")
            return
        }
        let json = (try? JSONSerialization.jsonObject(with: Data(content.utf8))) as? [String: Any]
        #expect(json?["status"] as? String == "ok")
        #expect(json?["result"] as? String == "已添加日历事件")
        #expect(json?["event_id"] == nil)
    }

    @Test("失败回填：{\"status\":\"error\",\"result\":\"…\"}，不含 message")
    func resultStyleError() async {
        let outcome = await ToolLoop.process(accumulated: dispatchText(), tools: [ResultTool(status: "error")],
                                             round: 1, validationFailures: 0)
        guard case .feedback(let content, _) = outcome else {
            Issue.record("应回填")
            return
        }
        let json = (try? JSONSerialization.jsonObject(with: Data(content.utf8))) as? [String: Any]
        #expect(json?["status"] as? String == "error")
        #expect(json?["result"] as? String == "时间表达无法解析")
        #expect(json?["message"] == nil)
    }
}
