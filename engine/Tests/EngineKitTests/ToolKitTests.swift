import Testing
import Foundation
@testable import EngineKit

// T1 验收单测四类（docs/plans/工具执行层-ToolKit.md 第 6 节 T1）：
// registry 查重拒绝 / 白名单拒绝 / 时间正则边界 / markdown 围栏容错

/// 与训练契约同款参数的日程工具规格（测试替身，不真正写日历）
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
            ToolParameterSpec(name: "location", type: "string", description: "地点", required: false),
        ])
}

private struct StubTool: LocalTool {
    let spec: ToolSpec
    func execute(_ arguments: [String: Any]) async throws -> ToolResult {
        ToolResult(status: "ok", content: "evt_stub")
    }
}

@Suite("ToolRegistry 白名单")
struct ToolRegistryTests {

    @Test("同名工具二次注册必须抛错（查重拒绝）")
    func duplicateRegistrationRejected() throws {
        let reg = ToolRegistry()
        try reg.register(StubTool(spec: calendarSpec()))
        #expect(throws: ToolKitError.self) {
            try reg.register(StubTool(spec: calendarSpec()))
        }
    }

    @Test("未注册的工具名查不到（幻觉工具名走拒绝路径）")
    func unknownToolReturnsNil() throws {
        let reg = ToolRegistry()
        try reg.register(StubTool(spec: calendarSpec()))
        #expect(reg.tool(named: "add_calendar_event") != nil)
        #expect(reg.tool(named: "delete_everything") == nil)
    }
}

@Suite("ToolCallValidator 参数校验")
struct ToolCallValidatorTests {

    @Test("合法参数全通过并收敛为字符串")
    func validArgumentsPass() {
        let args: [String: Any] = [
            "title": "团队会议",
            "start_time": "2026-11-05 14:30",
            "end_time": "2026-11-05 15:30",
            "location": "会议室 A",
        ]
        let r = ToolCallValidator.validate(spec: calendarSpec(), arguments: args)
        guard case .success(let n) = r else {
            Issue.record("合法参数不应校验失败")
            return
        }
        #expect(n["title"] == "团队会议")
        #expect(n["start_time"] == "2026-11-05 14:30")
    }

    @Test("缺必填参数失败且文案点名参数名")
    func missingRequiredFails() {
        let args: [String: Any] = [
            "title": "团队会议",
            "start_time": "2026-11-05 14:30",
        ]
        let r = ToolCallValidator.validate(spec: calendarSpec(), arguments: args)
        guard case .failure(let err) = r else {
            Issue.record("缺 end_time 应校验失败")
            return
        }
        #expect(err.description.contains("end_time"))
    }

    @Test("时间格式边界：分钟缺位/斜杠分隔/秒数多余都拒绝")
    func timePatternBoundaries() {
        let bad = [
            "2026-11-05 14:3",     // 分钟缺位
            "2026/11/05 14:30",    // 斜杠分隔
            "2026-11-05 14:30:00", // 多出秒数
            "2026-11-5 14:30",     // 月份缺位
        ]
        for t in bad {
            let args: [String: Any] = [
                "title": "x", "start_time": t,
                "end_time": "2026-11-05 15:30",
            ]
            guard case .failure = ToolCallValidator.validate(spec: calendarSpec(), arguments: args) else {
                Issue.record("时间 \(t) 应被正则拒绝")
                return
            }
        }
    }

    @Test("时间字段不带引号的数字值也收敛为字符串")
    func unquotedNumberCoerced() {
        // JSON 里 2026 这类值可能被模型写成裸数字，NSNumber 路径应兜住
        let args: [String: Any] = [
            "title": "x",
            "start_time": "2026-11-05 14:30",
            "end_time": "2026-11-05 15:30",
            "location": 12.5,
        ]
        guard case .success(let n) = ToolCallValidator.validate(spec: calendarSpec(), arguments: args) else {
            Issue.record("数字型可选参数应收敛为字符串")
            return
        }
        #expect(n["location"] == "12.5")
    }
}

@Suite("ToolCallParser 容错解析")
struct ToolCallParserTests {

    @Test("标准契约形状：正文穿插前后文也能提取")
    func extractStandardShape() throws {
        let text = "好的，我来帮你：\n<tool_call>\n{\"name\": \"add_calendar_event\", \"arguments\": {\"title\": \"会议\", \"start_time\": \"2026-11-05 14:30\", \"end_time\": \"2026-11-05 15:30\"}}\n</tool_call>"
        let bodies = ToolCallParser.extractBodies(from: text)
        #expect(bodies.count == 1)
        let call = try #require(ToolCallParser.parse(bodies[0]))
        #expect(call.name == "add_calendar_event")
        #expect(call.arguments["title"] as? String == "会议")
    }

    @Test("markdown 围栏包裹容错：```json 首尾剥掉")
    func fencedBodyParsed() throws {
        let body = "```json\n{\"name\": \"add_calendar_event\", \"arguments\": {\"title\": \"会议\"}}\n```"
        let call = try #require(ToolCallParser.parse(body))
        #expect(call.name == "add_calendar_event")
    }

    @Test("形状漂移容错：外层多套 tool_call 键剥掉（M1.5 抽查 #4 实测形状）")
    func unwrapExtraToolCallKey() throws {
        let body = #"{"tool_call": {"name": "add_calendar_event", "arguments": {"title": "会议", "start_time": "2026-11-05 14:30", "end_time": "2026-11-05 15:30"}}}"#
        let call = try #require(ToolCallParser.parse(body))
        #expect(call.name == "add_calendar_event")
        #expect(call.arguments["start_time"] as? String == "2026-11-05 14:30")
    }

    @Test("arguments 被二次序列化成字符串也能解出来")
    func stringifiedArgumentsParsed() throws {
        let body = #"{"name": "add_calendar_event", "arguments": "{\"title\": \"会议\"}"}"#
        let call = try #require(ToolCallParser.parse(body))
        #expect(call.arguments["title"] as? String == "会议")
    }

    @Test("无 <tool_call> 标签返回空（纯闲聊不误触发）")
    func noTagReturnsEmpty() {
        let bodies = ToolCallParser.extractBodies(from: "今天天气不错，不需要加日历。")
        #expect(bodies.isEmpty)
    }

    @Test("parseCall 兜底：无 XML 包裹的裸 JSON 调用也能解析（官方 1.7B 实测形状）")
    func bareJSONCallParsed() throws {
        let text = "好的，我来帮你：\n{\"name\": \"add_calendar_event\", \"arguments\": {\"title\": \"会议\", \"start_time\": \"2026-11-05 14:30\", \"end_time\": \"2026-11-05 15:30\"}}"
        let call = try #require(ToolCallParser.parseCall(from: text))
        #expect(call.name == "add_calendar_event")
        #expect(call.arguments["title"] as? String == "会议")
    }
}
