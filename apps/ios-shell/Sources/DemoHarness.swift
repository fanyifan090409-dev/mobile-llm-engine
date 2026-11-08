import Foundation
import EventKit
import EngineKit

// ==================== 演示壳专用 harness ====================
// 把「工具调用 / 日期换算 / 意图路由 / 多轮 / 性能」写成声明式用例，真机自动跑全套并落盘 JSONL。
// 触发：Documents/harness.run 内容为 "go"（启动时检测）；结果：Documents/harness-results.jsonl。
// 用户报的每个 bug 必须新增一条用例，套件全绿才算修完（回归纪律，见 docs/plans/演示壳Harness化-v1.md）。

struct HarnessExpect: Codable, Equatable {
    var tool: String?               // 期望触发的工具；nil = 不应触发任何工具
    var titleContains: String?
    var locationContains: String?
    var startDateRule: String?      // tomorrow / nextFriday / 2026-11-25（绝对日期）
    var startTime: String?          // HH:mm
    var replyContainsAny: [String]?
    var minReplyChars: Int?
    var englishOnly: Bool?
    var minDecodeTps: Double?
    var endAfterStartMinutes: Int?
}

struct HarnessCase: Codable {
    var id: String
    var category: String
    var prompt: String
    var tools: String               // always / never / auto（auto = 走意图路由，验证路由本身）
    var followUps: [String]?
    var followExpect: HarnessExpect?  // 多轮最后一句的期望（turn 级）
    var repeats: Int?               // 重复轮数（性能题取多轮较优值）
    var maxTokens: Int?             // 单轮 token 预算（默认 256）
    var expect: HarnessExpect
}

struct HarnessToolCall: Codable {
    var name: String
    var status: String
    var args: [String: String]
    var result: String
}

struct HarnessCaseResult: Codable {
    var id: String
    var category: String
    var pass: Bool
    var reasons: [String]
    var reply: String
    var toolCalls: [HarnessToolCall]
    var decodeTps: Double?
    var promptTps: Double?
    var peakMB: Int?
    var elapsedS: Double
}

private struct HarnessSummaryLine: Codable {
    var type = "summary"
    var pass: Int
    var total: Int
    var failed: [String]
    var ts: String
}

struct HarnessSummary {
    var total: Int
    var passed: Int
    var failed: [String]
    var jsonPath: String

    var displayText: String {
        if failed.isEmpty {
            return "Harness 套件 \(passed)/\(total) 全部通过 ✅（结果：harness-results.jsonl）"
        }
        return "Harness 套件 \(passed)/\(total) 通过，失败：\(failed.joined(separator: "、"))（详情见 harness-results.jsonl）"
    }
}

// 一次生成回合的原始采集
private struct HarnessTurn {
    var reply = ""
    var calls: [HarnessToolCall] = []
    var decodeTps: Double?
    var promptTps: Double?
    var peakMB: Int?
    var error: String?
}

enum DemoHarness {

    // v1 场景集：每条对应用户真机反馈或既有能力基线
    static let defaultCases: [HarnessCase] = [
        HarnessCase(
            id: "cal-parent-meeting", category: "tool",
            prompt: "帮我在手机日历里加一个事件：家长会，时间明天下午三点，地点学校，时长约一小时。",
            tools: "always",
            expect: HarnessExpect(tool: "add_calendar_event", titleContains: "家长会",
                                  locationContains: "学校", startDateRule: "tomorrow", startTime: "15:00",
                                  endAfterStartMinutes: 30)),
        HarnessCase(
            id: "cal-friday-class", category: "tool",
            prompt: "帮我在手机日历里加一个事件：健身私教课，时间周五晚上七点，地点健身房，时长约一小时。",
            tools: "always",
            expect: HarnessExpect(tool: "add_calendar_event", titleContains: "健身",
                                  locationContains: "健身房", startDateRule: "nextFriday", startTime: "19:00",
                                  endAfterStartMinutes: 30)),
        HarnessCase(
            id: "cal-explicit-date", category: "tool",
            prompt: "帮我在手机日历里加一个事件：生日派对，时间11月25日晚上八点，地点家里，时长约一小时。",
            tools: "always",
            expect: HarnessExpect(tool: "add_calendar_event", titleContains: "生日",
                                  locationContains: "家里", startDateRule: "2026-11-25", startTime: "20:00",
                                  endAfterStartMinutes: 30)),
        HarnessCase(
            id: "cal-tomorrow-2pm", category: "tool",
            prompt: "帮我在手机日历里加一个事件：雅思考试，时间明天下午两点，地点考点，时长约一小时。",
            tools: "always",
            expect: HarnessExpect(tool: "add_calendar_event", titleContains: "雅思",
                                  locationContains: "考点", startDateRule: "tomorrow", startTime: "14:00",
                                  endAfterStartMinutes: 30)),
        HarnessCase(
            id: "translate-express", category: "chat",
            prompt: "翻译成英文：快递到哪了",
            tools: "never",
            expect: HarnessExpect(englishOnly: true)),
        HarnessCase(
            id: "translate-with-calendar-word", category: "chat",
            prompt: "把这句话翻译成英文：明天下午三点开会。",
            tools: "never",
            expect: HarnessExpect(englishOnly: true)),
        HarnessCase(
            id: "qa-yasi", category: "chat",
            prompt: "啥是雅思？用一句话解释。",
            tools: "never",
            expect: HarnessExpect(replyContainsAny: ["雅思", "IELTS"])),
        HarnessCase(
            id: "summarize-300", category: "chat",
            prompt: "写一篇关于「秋天的北京」的短文（300字左右）。",
            tools: "never",
            maxTokens: 512,
            expect: HarnessExpect(minReplyChars: 40)),
        HarnessCase(
            id: "router-auto-calendar", category: "router",
            prompt: "帮我在日历里加一个会议：明天上午十点，地点办公室，时长约一小时。",
            tools: "auto",
            expect: HarnessExpect(tool: "add_calendar_event", startDateRule: "tomorrow", startTime: "10:00",
                                  endAfterStartMinutes: 30)),
        HarnessCase(
            id: "router-auto-chat", category: "router",
            prompt: "你好，用一句话介绍你自己。",
            tools: "auto",
            expect: HarnessExpect(minReplyChars: 5)),
        HarnessCase(
            id: "multi-turn-followup", category: "multiTurn",
            prompt: "帮我在手机日历里加一个事件：家长会，时间明天下午三点，地点学校，时长约一小时。",
            tools: "always",
            followUps: ["刚才添加的事件是什么时间？"],
            followExpect: HarnessExpect(replyContainsAny: ["15:00", "三点", "3点"]),
            expect: HarnessExpect(tool: "add_calendar_event", startDateRule: "tomorrow", startTime: "15:00")),
        HarnessCase(
            id: "perf-short-essay", category: "perf",
            prompt: "写一篇300字左右的短文，介绍你理想中的一天，从早上起床写到晚上睡觉。",
            tools: "never",
            repeats: 2,
            maxTokens: 512,
            expect: HarnessExpect(minReplyChars: 40, minDecodeTps: 20)),
    ]

    // MARK: - 执行

    static func run(engine: EngineCore, log: AppLog) async -> HarnessSummary {
        let cases = loadCases(log: log)
        let docs = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
        let outURL = docs.appendingPathComponent("harness-results.jsonl")
        try? FileManager.default.removeItem(at: outURL)
        FileManager.default.createFile(atPath: outURL.path, contents: nil)
        let handle = try? FileHandle(forWritingTo: outURL)
        defer { try? handle?.close() }

        log.log("HARNESS-START：\(cases.count) 例，结果写 \(outURL.lastPathComponent)")
        // 未授权时工具类用例直接判失败（避免卡在系统授权弹窗把套件挂死）
        let calendarOK = calendarAuthorized
        if !calendarOK {
            log.log("HARNESS 警告：日历未授权，工具类用例将直接判失败（请先在 App 内授权一次）")
        }
        var results: [HarnessCaseResult] = []
        // 时间解析是纯本地逻辑，先跑自检；模型用例再验证端到端工具调用
        let timeFailures = TimeHints.selfTest()
        let timeResult = HarnessCaseResult(
            id: "time-hints-selftest", category: "time", pass: timeFailures.isEmpty,
            reasons: timeFailures, reply: "", toolCalls: [], decodeTps: nil, promptTps: nil,
            peakMB: nil, elapsedS: 0)
        results.append(timeResult)
        log.log("HARNESS \(timeResult.pass ? "PASS" : "FAIL") \(timeResult.id)" +
                (timeFailures.isEmpty ? "" : "：\(timeFailures.joined(separator: "；"))"))
        if let data = try? JSONEncoder().encode(timeResult), let h = handle {
            h.write(data)
            h.write("\n".data(using: .utf8)!)
        }
        // 语音链路自检也先于模型用例：模型缺失时保留 3 条失败记录，套件总数稳定
        let voiceResults = await runVoiceCases(log: log)
        for r in voiceResults {
            results.append(r)
            log.log("HARNESS \(r.pass ? "PASS" : "FAIL") \(r.id)" +
                    (r.reasons.isEmpty ? "" : "：\(r.reasons.joined(separator: "；"))"))
            if let data = try? JSONEncoder().encode(r), let h = handle {
                h.write(data)
                h.write("\n".data(using: .utf8)!)
            }
        }
        for c in cases {
            let r = await runCase(c, engine: engine, log: log, calendarAuthorized: calendarOK)
            results.append(r)
            log.log("HARNESS \(r.pass ? "PASS" : "FAIL") \(r.id)" +
                    (r.reasons.isEmpty ? "" : "：\(r.reasons.joined(separator: "；"))"))
            if let data = try? JSONEncoder().encode(r), let h = handle {
                h.write(data)
                h.write("\n".data(using: .utf8)!)
            }
        }
        let failed = results.filter { !$0.pass }.map(\.id)
        let summary = HarnessSummary(total: results.count, passed: results.count - failed.count,
                                     failed: failed, jsonPath: outURL.path)
        let line = HarnessSummaryLine(pass: summary.passed, total: summary.total,
                                      failed: failed, ts: ISO8601DateFormatter().string(from: Date()))
        if let data = try? JSONEncoder().encode(line), let h = handle {
            h.write(data)
            h.write("\n".data(using: .utf8)!)
        }
        log.log("HARNESS-DONE：\(summary.passed)/\(summary.total) 通过" +
                (failed.isEmpty ? "" : "，失败：\(failed.joined(separator: ","))"))
        return summary
    }

    private static func loadCases(log: AppLog) -> [HarnessCase] {
        let url = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("harness-cases.json")
        guard let data = try? Data(contentsOf: url),
              let cases = try? JSONDecoder().decode([HarnessCase].self, from: data) else {
            return defaultCases
        }
        log.log("HARNESS：使用 Documents/harness-cases.json 覆盖（\(cases.count) 例）")
        return cases
    }

    // MARK: - 语音自检（P1 回归）

    @MainActor
    private static func runVoiceCases(log: AppLog) -> [HarnessCaseResult] {
        let started = Date()
        let voice = VoiceService()
        let modelsReady = voice.isASRAvailable && voice.isTTSAvailable
        let modelsResult = HarnessCaseResult(
            id: "voice-models", category: "voice", pass: modelsReady,
            reasons: modelsReady ? [] : ["语音模型缺失：Documents/VoiceModels（ASR/TTS）"],
            reply: modelsReady ? "ASR/TTS 模型已安装" : "",
            toolCalls: [], decodeTps: nil, promptTps: nil, peakMB: nil,
            elapsedS: (Date().timeIntervalSince(started) * 10).rounded() / 10)
        guard modelsReady else {
            let missing = ["语音模型缺失：Documents/VoiceModels"]
            return [modelsResult,
                    HarnessCaseResult(id: "voice-tts-synth", category: "voice", pass: false,
                                      reasons: missing, reply: "", toolCalls: [],
                                      decodeTps: nil, promptTps: nil, peakMB: nil, elapsedS: 0),
                    HarnessCaseResult(id: "voice-asr-roundtrip", category: "voice", pass: false,
                                      reasons: missing, reply: "", toolCalls: [],
                                      decodeTps: nil, promptTps: nil, peakMB: nil, elapsedS: 0)]
        }

        // 合成一句带时间与动作的中文，既验 TTS，又作为 ASR 的已知输入
        let phrase = "明天下午三点提醒我开会。"
        let ttsStarted = Date()
        let audio = voice.synthesize(phrase)
        var ttsReasons: [String] = []
        var ttsReply = ""
        if let audio {
            let seconds = Double(audio.samples.count) / Double(audio.sampleRate)
            ttsReply = String(format: "%.2f 秒 @ %d Hz", seconds, audio.sampleRate)
            if audio.sampleRate != 24000 {
                ttsReasons.append("采样率异常：\(audio.sampleRate) != 24000")
            }
            if seconds < 0.5 {
                ttsReasons.append(String(format: "音频过短：%.2f 秒", seconds))
            }
        } else {
            ttsReasons.append(voice.notice ?? "TTS 合成失败")
        }
        let ttsResult = HarnessCaseResult(
            id: "voice-tts-synth", category: "voice", pass: ttsReasons.isEmpty,
            reasons: ttsReasons, reply: ttsReply, toolCalls: [], decodeTps: nil, promptTps: nil,
            peakMB: nil, elapsedS: (Date().timeIntervalSince(ttsStarted) * 10).rounded() / 10)

        let asrStarted = Date()
        var asrReasons: [String] = []
        var asrReply = ""
        if let audio, let text = voice.transcribe(samples: audio.samples, sampleRate: audio.sampleRate) {
            asrReply = text
            if !text.contains("开会") {
                asrReasons.append("转写未命中「开会」：\(text)")
            } else if !["明天", "三点", "提醒"].contains(where: { text.contains($0) }) {
                asrReasons.append("转写缺少关键上下文：\(text)")
            }
        } else {
            asrReasons.append(voice.notice ?? "ASR 识别失败")
        }
        let asrResult = HarnessCaseResult(
            id: "voice-asr-roundtrip", category: "voice", pass: asrReasons.isEmpty,
            reasons: asrReasons, reply: asrReply, toolCalls: [], decodeTps: nil, promptTps: nil,
            peakMB: nil, elapsedS: (Date().timeIntervalSince(asrStarted) * 10).rounded() / 10)

        log.log("HARNESS voice 自检：\(ttsReply)，ASR「\(asrReply)」")
        return [modelsResult, ttsResult, asrResult]
    }

    private static func runCase(_ c: HarnessCase, engine: EngineCore, log: AppLog,
                                calendarAuthorized: Bool) async -> HarnessCaseResult {
        let started = Date()
        if c.expect.tool == "add_calendar_event", !calendarAuthorized {
            return HarnessCaseResult(
                id: c.id, category: c.category, pass: false,
                reasons: ["日历未授权：请先在 App 内完成一次日历授权"],
                reply: "", toolCalls: [], decodeTps: nil, promptTps: nil, peakMB: nil,
                elapsedS: (Date().timeIntervalSince(started) * 10).rounded() / 10)
        }
        var history: [Message] = []
        var firstTurn: HarnessTurn?
        var lastTurn: HarnessTurn?
        var bestTps: Double?
        var bestPeak: Int?
        let repeats = max(1, c.repeats ?? 1)

        for round in 0..<repeats {
            history.removeAll()
            let turns = [c.prompt] + (c.followUps ?? [])
            var turnResults: [HarnessTurn] = []
            for text in turns {
                let whitelist = whitelist(c.tools, text)
                // 与 UI 同款：工具轮前置日期锚点 + 相对时间显式提示
                let content = whitelist != nil ? DemoModel.toolContent(text) : text
                history.append(Message(role: "user", content: content))
                let turn = await generate(engine: engine, history: history, tools: whitelist,
                                           maxTokens: c.maxTokens ?? 256)
                history.append(Message(role: "assistant", content: turn.reply))
                turnResults.append(turn)
                if let id = executedEventID(turn.calls) { cleanupCalendarEvent(id: id) }
            }
            if round == 0 { firstTurn = turnResults.first }
            lastTurn = turnResults.last
            bestTps = max(bestTps ?? 0, turnResults.compactMap(\.decodeTps).max() ?? 0)
            bestPeak = max(bestPeak ?? 0, turnResults.compactMap(\.peakMB).max() ?? 0)
            if repeats > 1 { log.log("HARNESS \(c.id) 第 \(round + 1)/\(repeats) 轮") }
        }

        var reasons: [String] = []
        // 首轮断言：工具名 / 参数 / 回复
        if let first = firstTurn {
            evaluate(c.expect, turn: first, prefix: "", reasons: &reasons)
        }
        // 多轮追问断言
        if let fe = c.followExpect, let last = lastTurn {
            evaluate(fe, turn: last, prefix: "追问：", reasons: &reasons)
        }
        let reply = lastTurn?.reply ?? ""
        let calls = firstTurn?.calls ?? []
        let pass = reasons.isEmpty
        return HarnessCaseResult(
            id: c.id, category: c.category, pass: pass, reasons: reasons,
            reply: String(reply.prefix(600)), toolCalls: calls,
            decodeTps: bestTps.map { ($0 * 10).rounded() / 10 },
            promptTps: firstTurn?.promptTps.map { ($0 * 10).rounded() / 10 },
            peakMB: bestPeak, elapsedS: (Date().timeIntervalSince(started) * 10).rounded() / 10)
    }

    private static func generate(engine: EngineCore, history: [Message], tools: [String]?,
                                 maxTokens: Int) async -> HarnessTurn {
        var turn = HarnessTurn()
        do {
            for try await event in engine.generate(GenerationRequest(
                messages: history, maxTokens: maxTokens, temperature: 0, speed: .balanced,
                tools: tools)) {
                switch event {
                case .token(let t):
                    turn.reply += t
                case .toolCall(let e):
                    let status: String
                    switch e.status {
                    case .executed: status = "executed"
                    case .rejected: status = "rejected"
                    case .failed: status = "failed"
                    }
                    turn.calls.append(HarnessToolCall(
                        name: e.toolName, status: status, args: e.arguments, result: e.resultText))
                case .stats(let s):
                    turn.decodeTps = s.tokensPerSecond
                    turn.promptTps = s.promptTokensPerSecond
                    turn.peakMB = s.peakMemoryMB
                }
            }
        } catch {
            turn.error = "\(error)"
        }
        return turn
    }

    // always=强制挂工具；never=不挂；auto=走 UI 同款意图路由（验证路由本身）
    private static func whitelist(_ mode: String, _ text: String) -> [String]? {
        switch mode {
        case "always": return ["add_calendar_event"]
        case "never": return nil
        default: return DemoModel.looksLikeCalendarRequest(text) ? ["add_calendar_event"] : nil
        }
    }

    // MARK: - 断言

    private static func evaluate(_ e: HarnessExpect, turn: HarnessTurn, prefix: String, reasons: inout [String]) {
        if let err = turn.error {
            reasons.append("\(prefix)生成出错：\(err)")
            return
        }
        let calls = turn.calls
        if let tool = e.tool {
            guard let call = calls.first(where: { $0.name == tool }) else {
                reasons.append("\(prefix)未触发工具 \(tool)（实际：\(calls.map(\.name).joined(separator: ",") )）")
                return
            }
            if call.status != "executed" {
                reasons.append("\(prefix)工具 \(tool) 状态 \(call.status)：\(call.result)")
            }
            if let t = e.titleContains, !(call.args["title"] ?? "").contains(t) {
                reasons.append("\(prefix)标题不符：期望含「\(t)」，实际「\(call.args["title"] ?? "")」")
            }
            if let l = e.locationContains, !(call.args["location"] ?? "").contains(l) {
                reasons.append("\(prefix)地点不符：期望含「\(l)」，实际「\(call.args["location"] ?? "")」")
            }
            if let rule = e.startDateRule, let time = e.startTime {
                let expected = expectedStart(rule: rule, time: time)
                let actual = call.args["start_time"] ?? ""
                if actual != expected {
                    reasons.append("\(prefix)时间不符：期望 \(expected)，实际 \(actual)")
                }
            }
            if let minDur = e.endAfterStartMinutes,
               let start = parseDateTime(call.args["start_time"] ?? ""),
               let end = parseDateTime(call.args["end_time"] ?? ""),
               end.timeIntervalSince(start) < Double(minDur * 60) {
                reasons.append("\(prefix)时长异常：\(call.args["start_time"] ?? "")→\(call.args["end_time"] ?? "") 不足 \(minDur) 分钟")
            }
        } else if !calls.isEmpty {
            reasons.append("\(prefix)误触发工具：\(calls.map(\.name).joined(separator: ","))")
        }
        if let any = e.replyContainsAny,
           !any.contains(where: { turn.reply.contains($0) }) {
            reasons.append("\(prefix)回复未命中关键词 \(any)：\(turn.reply.prefix(80))")
        }
        if let minChars = e.minReplyChars, turn.reply.count < minChars {
            reasons.append("\(prefix)回复过短：\(turn.reply.count) < \(minChars)")
        }
        if e.englishOnly == true {
            let ascii = turn.reply.unicodeScalars.filter { $0.isASCII && $0.properties.isAlphabetic }.count
            if ascii < 10 || turn.reply.contains("日历") {
                reasons.append("\(prefix)英文输出检查失败：\(turn.reply.prefix(80))")
            }
        }
        if let minTps = e.minDecodeTps, let tps = turn.decodeTps, tps < minTps {
            reasons.append("\(prefix)解码过慢：\(tps) < \(minTps) tok/s")
        }
    }

    // 相对/绝对日期规则 → 期望的 "yyyy-MM-dd HH:mm"
    static func expectedStart(rule: String, time: String, now: Date = Date()) -> String {
        var cal = Calendar.current
        cal.timeZone = TimeZone.current
        let parts = time.split(separator: ":").compactMap { Int($0) }
        let hour = parts.count == 2 ? parts[0] : 9
        let minute = parts.count == 2 ? parts[1] : 0
        var day: Date
        switch rule {
        case "tomorrow":
            day = cal.date(byAdding: .day, value: 1, to: now) ?? now
        case "nextFriday":
            // 下一个周五（严格晚于今天），与「周五晚上七点」训练分布一致
            let weekday = 6   // Calendar 周日=1 … 周五=6
            var comps = DateComponents()
            comps.weekday = weekday
            comps.hour = hour
            comps.minute = minute
            day = cal.nextDate(after: cal.startOfDay(for: now), matching: comps,
                               matchingPolicy: .nextTime) ?? now
        default:
            let fmt = DateFormatter()
            fmt.dateFormat = "yyyy-MM-dd"
            fmt.locale = Locale(identifier: "en_US_POSIX")
            day = fmt.date(from: rule) ?? now
        }
        var dc = cal.dateComponents([.year, .month, .day], from: day)
        dc.hour = hour
        dc.minute = minute
        guard let composed = cal.date(from: dc) else { return rule + " " + time }
        let out = DateFormatter()
        out.dateFormat = "yyyy-MM-dd HH:mm"
        out.locale = Locale(identifier: "en_US_POSIX")
        return out.string(from: composed)
    }

    private static var calendarAuthorized: Bool {
        let status = EKEventStore.authorizationStatus(for: .event)
        if #available(iOS 17.0, *) { return status == .fullAccess }
        return status == .authorized
    }

    private static let dateTimeFormatter: DateFormatter = {
        let f = DateFormatter()
        f.dateFormat = "yyyy-MM-dd HH:mm"
        f.locale = Locale(identifier: "en_US_POSIX")
        return f
    }()

    private static func parseDateTime(_ s: String) -> Date? {
        dateTimeFormatter.date(from: s)
    }

    private static func executedEventID(_ calls: [HarnessToolCall]) -> String? {
        guard let call = calls.first(where: { $0.name == "add_calendar_event" && $0.status == "executed" }),
              !call.result.isEmpty else { return nil }
        return call.result
    }

    // harness 自清理：测试事件写完即删，用户日历不留痕
    private static func cleanupCalendarEvent(id: String) {
        let store = EKEventStore()
        if let event = store.event(withIdentifier: id) {
            try? store.remove(event, span: .thisEvent, commit: true)
        }
    }
}
