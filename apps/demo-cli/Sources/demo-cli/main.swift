import Foundation
import EngineKit

// demo-cli：Mac 基准 CLI。交互对话 + 一次性生成两种模式，收尾打印 tok/s / pp_ts / 峰值 RSS
// 用法：
//   demo-cli --model <gguf> [--quant Q4_K_M] [--context 4096] [--speed balanced] [--max-tokens 256] [--temperature 0.7]
//   demo-cli ... [--tools] [--trust-tools]          # --tools 开启日历工具；--trust-tools 跳过每次确认（强提醒）
//   demo-cli ... -p "你好，介绍一下你自己"           # 一次性模式（基准用）
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
        guard let modelPath = opts.modelPath else {
            print("缺少 --model <gguf 路径>", to: &standardError)
            exit(1)
        }
        guard FileManager.default.fileExists(atPath: modelPath) else {
            print("模型文件不存在：\(modelPath)", to: &standardError)
            exit(1)
        }

        let engine = EngineCore()
        let spec = ModelSpec(fileURL: URL(fileURLWithPath: modelPath), quant: opts.quant, context: opts.context)
        do {
            try await engine.load(spec)
        } catch {
            print("模型加载失败：\(error)", to: &standardError)
            exit(1)
        }

        if opts.tools {
            let confirm: @Sendable (String) async -> Bool = { summary in
                print("\n[确认] 将执行：\(summary)\n确认写入日历？(y/N) ", terminator: "")
                fflush(stdout)
                return (readLine() ?? "").lowercased() == "y"
            }
            try? engine.registerTool(CalendarTool(confirm: confirm, trustAlways: opts.trustTools))
            if opts.trustTools {
                // 完全信任模式强提醒：写操作不再确认，直接执行
                print("⚠️  完全信任模式已开启：日历写入将不再询问确认，直接执行。请谨慎使用。")
            } else {
                print("工具模式已开启：写操作每次都会要求确认（--trust-tools 可跳过确认）")
            }
        }

        if let p = opts.prompt {
            // 一次性模式：单轮生成，统计收尾即退出（基准脚本用）
            await runOnce(engine, prompt: p, opts: opts)
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
                    for try await event in engine.generate(GenerationRequest(
                        messages: history, maxTokens: opts.maxTokens,
                        temperature: opts.temperature, speed: opts.speed,
                        tools: opts.tools ? ["add_calendar_event"] : nil)) {
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

    static func runOnce(_ engine: EngineCore, prompt: String, opts: CLIOptions) async {
        do {
            for try await event in engine.generate(GenerationRequest(
                messages: [Message(role: "user", content: prompt)],
                maxTokens: opts.maxTokens, temperature: opts.temperature, speed: opts.speed,
                tools: opts.tools ? ["add_calendar_event"] : nil)) {
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
