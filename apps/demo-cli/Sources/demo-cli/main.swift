import Foundation
import EngineKit

// demo-cli：Mac 基准 CLI。交互对话 + 一次性生成两种模式，收尾打印 tok/s / pp_ts / 峰值 RSS
// 用法：
//   demo-cli --model <gguf> [--quant Q4_K_M] [--context 4096] [--speed balanced] [--max-tokens 256] [--temperature 0.7]
//   demo-cli ... [--tools] [--trust-tools]          # --tools 开启日历工具；--trust-tools 跳过每次确认（强提醒）
//   demo-cli ... --worker-model <gguf> [--worker-quant Q5_K_M] [--worker-context 4096]
//                                                   # 多模型模式：本地为领队，工人模型按需懒加载，走 dispatch_to_worker
//   demo-cli ... [--think-tags]                     # 空思考块注入（SFT3 起模型训练模板同款，SFT2/官方模型勿开；多模型模式强制开启）
//   demo-cli ... -p "你好，介绍一下你自己"           # 一次性模式（基准用）
//   demo-cli --calc "1/3+1/6"                        # CAS 计算（不加载模型）：求值/求导/定积分/解方程/统计
//   demo-cli --calc-repl                             # CAS 交互计算模式
//   demo-cli --calc-selftest                         # CAS 一期验收（69 题纯计算子集 + P95）
//   demo-cli ... --math                              # 注册 math_eval 工具（二期训练前的实验入口）
// 速度档：powerSaver / balanced / performance / turbo

struct CLIOptions {
    var modelPath: String?
    var quant = "Q4_K_M"
    var context = 4096
    var speed = SpeedTier.balanced
    var maxTokens = 256
    var temperature = 0.7
    var prompt: String?
    var tools = false
    var trustTools = false
    var thinkTags = false
    var workerModelPath: String?
    var workerQuant = "Q5_K_M"
    var workerContext = 4096
    /// CAS 一期独立入口：nil=不启用；""=无表达式的一次性计算（stats 用）；非空=一次性计算
    var calc: String?
    var calcRepl = false
    var calcOp: String?
    var calcVariable: String?
    var calcLower: String?
    var calcUpper: String?
    var calcStat: String?
    var calcData: String?
    var calcSelftest = false
    /// 模型工具模式：注册 math_eval（二期训练前的实验入口）
    var mathTool = false
}

func parseSpeed(_ s: String) -> SpeedTier {
    switch s {
    case "powerSaver": return .powerSaver
    case "performance": return .performance
    case "turbo": return .turbo
    default: return .balanced
    }
}

func parseArgs() -> CLIOptions {
    var opts = CLIOptions()
    var args = Array(CommandLine.arguments.dropFirst())
    func take(_ a: inout [String]) -> String? {
        guard !a.isEmpty else { return nil }
        return a.removeFirst()
    }
    while !args.isEmpty {
        let a = args.removeFirst()
        switch a {
        case "--model": opts.modelPath = take(&args)
        case "--quant": opts.quant = take(&args) ?? opts.quant
        case "--context": opts.context = Int(take(&args) ?? "") ?? opts.context
        case "--speed": opts.speed = parseSpeed(take(&args) ?? "")
        case "--max-tokens": opts.maxTokens = Int(take(&args) ?? "") ?? opts.maxTokens
        case "--temperature": opts.temperature = Double(take(&args) ?? "") ?? opts.temperature
        case "-p", "--prompt": opts.prompt = take(&args)
        case "--tools": opts.tools = true
        case "--trust-tools": opts.trustTools = true
        case "--think-tags": opts.thinkTags = true
        case "--worker-model": opts.workerModelPath = take(&args)
        case "--worker-quant": opts.workerQuant = take(&args) ?? opts.workerQuant
        case "--worker-context": opts.workerContext = Int(take(&args) ?? "") ?? opts.workerContext
        case "--calc":
            if let next = args.first, !next.hasPrefix("--") {
                opts.calc = args.removeFirst()
            } else {
                opts.calc = ""
            }
        case "--calc-repl": opts.calcRepl = true
        case "--calc-op": opts.calcOp = take(&args)
        case "--calc-variable": opts.calcVariable = take(&args)
        case "--calc-lower": opts.calcLower = take(&args)
        case "--calc-upper": opts.calcUpper = take(&args)
        case "--calc-stat": opts.calcStat = take(&args)
        case "--calc-data": opts.calcData = take(&args)
        case "--calc-selftest": opts.calcSelftest = true
        case "--math": opts.mathTool = true
        default:
            print("未知参数：\(a)", to: &standardError)
        }
    }
    return opts
}

func printStats(_ s: TokenEvent.Stats) {
    print(String(
        format: "\n--- 统计：解码 %.1f tok/s | 预填充 %.1f tok/s | 峰值内存 %d MB ---",
        s.tokensPerSecond, s.promptTokensPerSecond, s.peakMemoryMB))
}

struct DemoCLI {
    static func main() async {
        let opts = parseArgs()
        if opts.calcSelftest {
            exit(CalcSelfTest.run() ? 0 : 1)
        }
        if opts.calcRepl {
            exit(CalcCLI.run(nil, opts: opts))
        }
        if let calcInput = opts.calc {
            exit(CalcCLI.run(calcInput, opts: opts))
        }
        guard let modelPath = opts.modelPath else {
            print("缺少 --model <gguf 路径>", to: &standardError)
            exit(1)
        }
        guard FileManager.default.fileExists(atPath: modelPath) else {
            print("模型文件不存在：\(modelPath)", to: &standardError)
            exit(1)
        }

        let engine = EngineCore()
        let useWorkers = opts.workerModelPath != nil
        // SFT20 领队/工人都是 --no-think 训练：多模型模式强制注入空思考块；单模型仍按 --think-tags
        let spec = ModelSpec(fileURL: URL(fileURLWithPath: modelPath), quant: opts.quant,
                             context: opts.context, thinkTags: opts.thinkTags || useWorkers)
        do {
            try await engine.load(spec)
        } catch {
            print("模型加载失败：\(error)", to: &standardError)
            exit(1)
        }

        let confirm: @Sendable (String) async -> Bool = { summary in
            print("\n[确认] 将执行：\(summary)\n确认执行？(y/N) ", terminator: "")
            fflush(stdout)
            return (readLine() ?? "").lowercased() == "y"
        }
        let calendarTool = CalendarTool(confirm: confirm, trustAlways: opts.trustTools)
        let reminderTool = ReminderTool(confirm: confirm, trustAlways: opts.trustTools)
        var leaderSystem: String?

        if let workerPath = opts.workerModelPath {
            guard FileManager.default.fileExists(atPath: workerPath) else {
                print("工人模型文件不存在：\(workerPath)", to: &standardError)
                exit(1)
            }
            let dispatcher = WorkerDispatcher(profiles: WorkerProfiles.sft20(
                workerModelURL: URL(fileURLWithPath: workerPath),
                quant: opts.workerQuant, context: opts.workerContext))
            let executor: DispatchTool.Executor = { call in
                print("\n[工人] \(call.toolName) \(call.arguments)")
                let args: [String: Any] = call.arguments.mapValues { $0 as Any }
                switch call.toolName {
                case "add_calendar_event":
                    let result = try await calendarTool.execute(args)
                    guard result.status == "ok" else { return result }
                    let title = call.arguments["title"] ?? ""
                    let start = call.arguments["start_time"] ?? ""
                    let end = call.arguments["end_time"] ?? ""
                    let location = call.arguments["location"] ?? ""
                    let place = location.isEmpty ? "" : "，地点：\(location)"
                    return ToolResult(status: "ok", content: "已添加日历事件：\(title)，\(start)-\(end)\(place)")
                case "set_reminder":
                    let result = try await reminderTool.execute(args)
                    guard result.status == "ok" else { return result }
                    return ToolResult(status: "ok",
                                      content: "已设置提醒：\(call.arguments["content"] ?? "")，\(call.arguments["remind_time"] ?? "")")
                default:
                    return ToolResult(status: "error", content: "演示版暂未接入 \(call.toolName) 执行")
                }
            }
            try? engine.registerTool(DispatchTool(dispatcher: dispatcher, executor: executor))
            leaderSystem = WorkerProfiles.leaderSystemPrompt + "\n" + DateHint.todayLine()
            print("多模型模式：领队 + 工人（\(opts.workerQuant)，ctx \(opts.workerContext)）")
            print("链路：领队 → dispatch_to_worker → 工人 → 日历/提醒工具")
            if opts.trustTools {
                print("⚠️  完全信任模式已开启：工人写操作不再询问确认，直接执行。")
            } else {
                print("写操作每次都会要求确认（--trust-tools 可跳过确认）")
            }
        } else {
            if opts.tools {
                try? engine.registerTool(calendarTool)
                try? engine.registerTool(reminderTool)
                if opts.trustTools {
                    // 完全信任模式强提醒：写操作不再确认，直接执行
                    print("⚠️  完全信任模式已开启：日历写入将不再询问确认，直接执行。请谨慎使用。")
                } else {
                    print("工具模式已开启：写操作每次都会要求确认（--trust-tools 可跳过确认）")
                }
            }
            if opts.mathTool {
                try? engine.registerTool(MathEvalTool())
                print("数学工具已开启：math_eval（CAS 精确计算；模型尚未做工具调用专项训练，当前为实验模式）")
            }
        }

        if let p = opts.prompt {
            // 一次性模式：单轮生成，统计收尾即退出（基准脚本用）
            await runOnce(engine, prompt: p, opts: opts, leaderSystem: leaderSystem)
        } else {
            // 交互模式：多轮对话，历史累积在上下文里
            print("demo-cli 就绪（\(opts.quant)，ctx \(opts.context)，Ctrl-D 退出）")
            var history: [Message] = []
            while true {
                print("\n你> ", terminator: "")
                fflush(stdout)
                guard let line = readLine() else { break }
                if line.isEmpty { continue }
                history.append(Message(role: "user", content: line))
                var full = ""
                print("助手> ", terminator: "")
                fflush(stdout)
                do {
                    for try await event in engine.generate(makeRequest(
                        messages: history, opts: opts, leaderSystem: leaderSystem)) {
                        switch event {
                        case .token(let t):
                            print(t, terminator: "")
                            fflush(stdout)
                            full += t
                        case .toolCall(let tc):
                            print("\n[工具] \(tc.toolName) → \(tc.status)：\(tc.resultText)")
                        case .stats(let s):
                            printStats(s)
                        }
                    }
                } catch {
                    print("\n生成出错：\(error)", to: &standardError)
                }
                history.append(Message(role: "assistant", content: full))
            }
        }

        engine.unload()
    }

    /// 领队 system 消息只放在请求首部，不写进 history——否则多轮会重复累积
    static func makeRequest(messages: [Message], opts: CLIOptions,
                            leaderSystem: String?) -> GenerationRequest {
        var msgs = messages
        if let leaderSystem {
            msgs.insert(Message(role: "system", content: leaderSystem), at: 0)
        }
        let tools: [String]?
        if opts.workerModelPath != nil {
            tools = ["dispatch_to_worker"]
        } else if opts.tools || opts.mathTool {
            var names: [String] = []
            if opts.tools { names.append("add_calendar_event") }
            if opts.mathTool { names.append("math_eval") }
            tools = names
        } else {
            tools = nil
        }
        return GenerationRequest(messages: msgs, maxTokens: opts.maxTokens,
                                 temperature: opts.temperature, speed: opts.speed,
                                 tools: tools)
    }

    static func runOnce(_ engine: EngineCore, prompt: String, opts: CLIOptions,
                        leaderSystem: String?) async {
        do {
            for try await event in engine.generate(makeRequest(
                messages: [Message(role: "user", content: prompt)],
                opts: opts, leaderSystem: leaderSystem)) {
                switch event {
                case .token(let t):
                    print(t, terminator: "")
                    fflush(stdout)
                case .toolCall(let tc):
                    print("\n[工具] \(tc.toolName) → \(tc.status)：\(tc.resultText)")
                case .stats(let s):
                    printStats(s)
                }
            }
        } catch {
            print("\n生成出错：\(error)", to: &standardError)
            exit(1)
        }
    }
}

// stderr 重定向：print 默认走 stdout，报错要进 stderr 才能与输出流分离
var standardError = FileHandle.standardError
extension FileHandle: TextOutputStream {
    public func write(_ string: String) {
        if let data = string.data(using: .utf8) { write(data) }
    }
}

// 顶层入口：main.swift 与其他文件并存时不能用 @main，改信号量等待 async main 跑完
let mainDone = DispatchSemaphore(value: 0)
Task {
    await DemoCLI.main()
    mainDone.signal()
}
mainDone.wait()
