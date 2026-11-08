import Testing
import Foundation
@testable import EngineKit

private func workerCalendar() -> Calendar {
    var cal = Calendar(identifier: .gregorian)
    cal.timeZone = TimeZone(identifier: "Asia/Shanghai")!
    return cal
}

private func workerDate(_ year: Int, _ month: Int, _ day: Int) -> Date {
    workerCalendar().date(from: DateComponents(year: year, month: month, day: day))!
}

private func profile(_ name: String, needsTable: Bool) -> WorkerProfile {
    WorkerProfile(
        name: name,
        systemPrompt: "SYSTEM-\(name)",
        modelURL: URL(fileURLWithPath: "/tmp/not-used.gguf"),
        quant: "Q5_K_M",
        context: 2048,
        thinkTags: true,
        needsDateTable: needsTable)
}

private let calendarToolCall = """
<tool_call>
{"name": "add_calendar_event", "arguments": {"title": "吃药", "start_time": "2026-11-07 15:00", "end_time": "2026-11-07 15:30", "location": "", "note": ""}}
</tool_call>
"""

private final class StageBox: @unchecked Sendable {
    private let lock = NSLock()
    private var value: [DispatchStage] = []

    func add(_ stage: DispatchStage) {
        lock.lock()
        value.append(stage)
        lock.unlock()
    }

    var stages: [DispatchStage] {
        lock.lock()
        defer { lock.unlock() }
        return value
    }
}

@Suite("WorkerDispatcher 提示词拼装与解析")
struct WorkerDispatcherTests {

    @Test("日历工人：user = task + 三周日期表，system 原样")
    func calendarAppendsTable() async throws {
        let dispatcher = WorkerDispatcher(
            profiles: [profile("calendar_worker", needsTable: true)],
            runner: { profile, messages in
                #expect(profile.name == "calendar_worker")
                #expect(messages.count == 2)
                #expect(messages[0].role == "system")
                #expect(messages[0].content == "SYSTEM-calendar_worker")
                #expect(messages[1].content.hasPrefix("派单：添加日历事件：吃药，明天下午三点。"))
                #expect(messages[1].content.contains("日期参考：本周周一=2026-11-02"))
                return calendarToolCall
            })
        let call = try await dispatcher.dispatch(
            worker: "calendar_worker", task: "添加日历事件：吃药，明天下午三点。", now: workerDate(2026, 11, 6))
        #expect(call.toolName == "add_calendar_event")
        #expect(call.arguments["start_time"] == "2026-11-07 15:00")
        #expect(call.worker == "calendar_worker")
    }

    @Test("翻译工人：不追加日期表")
    func translateNoTable() async throws {
        let dispatcher = WorkerDispatcher(
            profiles: [profile("translate_worker", needsTable: false)],
            runner: { _, messages in
                #expect(messages[1].content == "派单：将以下文本翻译成英文：你好")
                #expect(!messages[1].content.contains("日期参考"))
                return #"<tool_call>{"name": "translate_text", "arguments": {"text": "你好", "target_lang": "en"}}</tool_call>"#
            })
        let call = try await dispatcher.dispatch(
            worker: "translate_worker", task: "将以下文本翻译成英文：你好", now: workerDate(2026, 11, 6))
        #expect(call.toolName == "translate_text")
    }

    @Test("DispatchTool 进度回调：started → workerOutput → finished")
    func dispatchStages() async throws {
        let box = StageBox()
        let dispatcher = WorkerDispatcher(
            profiles: [profile("calendar_worker", needsTable: true)],
            runner: { _, _ in calendarToolCall })
        let tool = DispatchTool(
            dispatcher: dispatcher,
            executor: { _ in ToolResult(status: "ok", content: "已写入") },
            now: { workerDate(2026, 11, 6) },
            onStage: { box.add($0) })
        _ = try await tool.execute(["worker": "calendar_worker", "task": "添加日历事件：吃药，明天下午三点。"])

        let stages = box.stages
        #expect(stages.count == 3)
        guard stages.count == 3 else { return }
        guard case .started(let worker, let task) = stages[0] else {
            Issue.record("第一段应为 started")
            return
        }
        #expect(worker == "calendar_worker")
        #expect(task.hasPrefix("派单：添加日历事件"))
        guard case .workerOutput(let worker2, let toolName, let args) = stages[1] else {
            Issue.record("第二段应为 workerOutput")
            return
        }
        #expect(worker2 == "calendar_worker")
        #expect(toolName == "add_calendar_event")
        #expect(args["start_time"] == "2026-11-07 15:00")
        guard case .finished(_, let toolName2, let status, let detail) = stages[2] else {
            Issue.record("第三段应为 finished")
            return
        }
        #expect(toolName2 == "add_calendar_event")
        #expect(status == "ok")
        #expect(detail == "已写入")
    }

    @Test("已带「派单：」前缀时不重复添加")
    func dispatchPrefixNotDuplicated() async throws {
        let dispatcher = WorkerDispatcher(
            profiles: [profile("calendar_worker", needsTable: false)],
            runner: { _, messages in
                #expect(messages[1].content == "派单：添加日历事件：吃药")
                return calendarToolCall
            })
        _ = try await dispatcher.dispatch(worker: "calendar_worker", task: "派单：添加日历事件：吃药")
    }

    @Test("未知工人抛错")
    func unknownWorker() async {
        let dispatcher = WorkerDispatcher(profiles: [profile("calendar_worker", needsTable: true)],
                                          runner: { _, _ in "" })
        do {
            _ = try await dispatcher.dispatch(worker: "nobody", task: "x")
            Issue.record("未知工人应抛错")
        } catch {}
    }

    @Test("工人无工具调用抛错")
    func noToolCall() async {
        let dispatcher = WorkerDispatcher(profiles: [profile("calendar_worker", needsTable: true)],
                                          runner: { _, _ in "你好，我是工人" })
        do {
            _ = try await dispatcher.dispatch(worker: "calendar_worker", task: "x")
            Issue.record("无工具调用应抛错")
        } catch {}
    }

    @Test("四种工人共用同一模型文件时复用同一缓存键")
    func sharedEngineCacheKey() {
        let calendar = profile("calendar_worker", needsTable: true)
        let reminder = profile("reminder_worker", needsTable: true)
        #expect(WorkerDispatcher.cacheKey(for: calendar) == WorkerDispatcher.cacheKey(for: reminder))

        let otherContext = WorkerProfile(
            name: calendar.name, systemPrompt: calendar.systemPrompt,
            modelURL: calendar.modelURL, quant: calendar.quant, context: 4096,
            thinkTags: calendar.thinkTags, needsDateTable: calendar.needsDateTable)
        #expect(WorkerDispatcher.cacheKey(for: calendar) != WorkerDispatcher.cacheKey(for: otherContext))
    }

    @Test("DispatchTool：无 executor 返回未执行提示，feedbackStyle=result")
    func dispatchToolPreview() async throws {
        let dispatcher = WorkerDispatcher(
            profiles: [profile("calendar_worker", needsTable: true)],
            runner: { _, _ in calendarToolCall })
        let tool = DispatchTool(dispatcher: dispatcher, now: { workerDate(2026, 11, 6) })
        #expect(tool.spec.feedbackStyle == .result)
        let result = try await tool.execute(["worker": "calendar_worker", "task": "添加日历事件：吃药，明天下午三点。"])
        #expect(result.status == "ok")
        #expect(result.content.contains("已生成工具调用（未执行）"))
    }

    @Test("DispatchTool：executor 结果原样回填")
    func dispatchToolExecutor() async throws {
        let dispatcher = WorkerDispatcher(
            profiles: [profile("calendar_worker", needsTable: true)],
            runner: { _, _ in calendarToolCall })
        let tool = DispatchTool(
            dispatcher: dispatcher,
            executor: { call in
                #expect(call.toolName == "add_calendar_event")
                return ToolResult(status: "ok", content: "已添加日历事件：吃药，2026-11-07 15:00-15:30")
            },
            now: { workerDate(2026, 11, 6) })
        let result = try await tool.execute(["worker": "calendar_worker", "task": "添加日历事件：吃药，明天下午三点。"])
        #expect(result.status == "ok")
        #expect(result.content == "已添加日历事件：吃药，2026-11-07 15:00-15:30")
    }
}
