import Foundation
import Darwin
import CLLaMA

// EngineCore：LocalEngine 的 M1 实现。
// 线程模型：C 调用（加载/解码/采样）全部在串行 generation 队列执行，
// 流式事件经 AsyncThrowingStream 的 continuation 回到调用方。
public final class EngineCore: LocalEngine {
    private var model: ModelHandle?
    private var ctx: ContextHandle?
    private var thinkTags = false   // 空思考块注入开关，与 ModelSpec.thinkTags 同源（训练模板 enable_thinking 对齐）
    private let queue = DispatchQueue(label: "enginekit.generation", qos: .userInitiated)
    private let registry = ToolRegistry()

    public init() {
        CLLaMABackend.ensureInitialized()
    }

    /// 白名单编译期注册（不动态加载）；重名抛错
    public func registerTool(_ tool: LocalTool) throws {
        try registry.register(tool)
    }

    // 内存档位雏形表：low/standard/high ↔ 0.6B/1.7B/4B 的粗略物理内存门槛（M3 换真机预算+热控）
    public func resolveTier(deviceMemory: Int) -> MemoryTier? {
        if deviceMemory >= 6_000 { return .high }      // ≥6GB 可上 4B 档
        if deviceMemory >= 3_000 { return .standard }  // 3-6GB 上 1.7B 档
        if deviceMemory >= 1_500 { return .low }       // 1.5-3GB 仅 0.6B 档
        return nil                                     // 内存过小，无法运行
    }

    public func load(_ spec: ModelSpec) async throws {
        try await withCheckedThrowingContinuation { (cont: CheckedContinuation<Void, Error>) in
            queue.async {
                do {
                    try self.loadSync(spec)
                    cont.resume()
                } catch {
                    cont.resume(throwing: error)
                }
            }
        }
    }

    // 速度档 → 解码线程数：powerSaver 2 线程 / balanced 4 / performance 8 / turbo 全部核心（0=自动）。
    // ngl 固定全层上 Metal（Mac 上最快）；功率档的 ngl/投机解码映射留到 M3 热控
    private func threads(for speed: SpeedTier) -> Int32 {
        switch speed {
        case .powerSaver:   return 2
        case .balanced:     return 4
        case .performance:  return 8
        case .turbo:        return 0
        }
    }

    public func generate(_ req: GenerationRequest) -> AsyncThrowingStream<TokenEvent, Error> {
        AsyncThrowingStream { continuation in
            queue.async {
                self.runGeneration(req, continuation)
            }
        }
    }

    // 卸载排队到生成队列之后：正在跑的生成结束后才释放，避免 use-after-free
    public func unload() {
        queue.sync {
            releaseResources()
        }
    }

    // 实际释放（调用方保证已在 generation 队列上，避免同队列 sync 死锁）
    private func releaseResources() {
        ctx = nil   // 先释放 ctx（KV），再释放 model（权重）——llama.cpp 要求
        model = nil
    }

    private func loadSync(_ spec: ModelSpec) throws {
        // 重复加载先释放旧模型，避免双份权重同时驻留
        releaseResources()
        let m = try ModelHandle.load(fileURL: spec.fileURL, nGPU: -1)
        let c = try m.makeContext(context: Int32(spec.context), batch: 2048)
        model = m
        ctx = c
        thinkTags = spec.thinkTags
    }

    private func runGeneration(_ req: GenerationRequest, _ cont: AsyncThrowingStream<TokenEvent, Error>.Continuation) {
        guard let model, let ctx else {
            cont.finish(throwing: EngineError.notLoaded)
            return
        }
        do {
            // 工具模式：req.tools 是本次启用的白名单子集；请求带 tools 但一个都解析不到 → 纯文本兜底
            let activeTools = req.tools?.compactMap { registry.tool(named: $0) } ?? []
            let toolMode = req.tools != nil && !activeTools.isEmpty
            let msgs = Self.messagesWithToolSystem(req.messages, tools: activeTools, toolMode: toolMode)

            let (full, sysCount) = try chatTokens(model: model, messages: msgs)
            var prompt = full
            // 防 KV 溢出：prompt + maxTokens 超上限时截断；工具定义的 system 触发文本不能丢，只截历史部分
            let budget = Int(ctx.nCtx) - req.maxTokens - 8
            if prompt.count > budget {
                let keep = max(0, budget - sysCount)
                prompt = Array(prompt.prefix(sysCount)) + Array(prompt.suffix(keep))
            }
            runGenerationWithPrompt(prompt, model: model, ctx: ctx, req: req, cont: cont,
                                    activeTools: activeTools, toolMode: toolMode)
        } catch {
            cont.finish(throwing: error)
        }
    }

    // 工具定义 system 注入：SFT3 训练数据的 schedule 轨迹前插了与合成期逐字一致的触发文本
    // （「你是手机助手。当用户要求添加日历事件时…」），推理侧必须注入同款文本，
    // 否则模型学不到「看到工具定义才输出 tool_call」的条件行为（tech-debt #2 根因）。
    // usagePrompt 为空跳过；用户已自带 system 消息时不重复注入
    private static func messagesWithToolSystem(_ messages: [Message], tools: [LocalTool], toolMode: Bool) -> [Message] {
        guard toolMode, !messages.contains(where: { $0.role == "system" }) else { return messages }
        let prompts = tools.compactMap { $0.spec.usagePrompt }
        guard !prompts.isEmpty else { return messages }
        return [Message(role: "system", content: prompts.joined(separator: "\n\n"))] + messages
    }

    private func runGenerationWithPrompt(
        _ prompt: [llama_token],
        model: ModelHandle,
        ctx: ContextHandle,
        req: GenerationRequest,
        cont: AsyncThrowingStream<TokenEvent, Error>.Continuation,
        activeTools: [LocalTool],
        toolMode: Bool
    ) {
        do {
            let sampler = try SamplerHandle.chain(temperature: Float(req.temperature), seed: UInt32.random(in: 0...UInt32.max))

            // 预填充：整段 prompt 一次 decode，计时算 pp_ts
            let ppStart = DispatchTime.now()
            try ctx.decode(tokens: prompt)
            let ppSeconds = Self.seconds(since: ppStart)
            let ppTs = Double(prompt.count) / max(ppSeconds, 0.001)

            // 自回归循环：采样 → 吐字 → 单 token decode；
            // 工具模式下累积文本命中 </tool_call> 即暂停解码，执行工具并把结果回填进上下文续跑
            let genStart = DispatchTime.now()
            var generated = 0
            var accumulated = ""        // 本段（一轮）累积文本，工具调用检测窗口
            var toolRounds = 0          // 已执行工具轮数
            var validationFailures = 0  // 连续拒绝/校验失败次数
            var loopStop = false
            var token = sampler.sample(ctx)
            while generated < req.maxTokens && !loopStop {
                if model.isEog(token) { break }
                let piece = model.piece(token)
                cont.yield(.token(piece))
                accumulated += piece
                generated += 1
                try ctx.decode(tokens: [token])  // 先让当前 token 进 KV，回填段接在其后

                // 触发检测：XML 包裹（训练契约）或裸 JSON 的 arguments 键（官方模型实测形状）；
                // 未解析出完整调用时 parseCall 返回 nil → noToolCall 继续生成，中途触发无害
                if toolMode && (accumulated.contains("</tool_call>") || accumulated.contains("\"arguments\"")) {
                    let outcome = Self.awaitToolLoop(
                        accumulated: accumulated, tools: activeTools,
                        round: toolRounds + 1, validationFailures: validationFailures)
                    switch outcome {
                    case .noToolCall:
                        break  // 没解析出完整调用（含误报），继续生成
                    case .stop:
                        loopStop = true  // 轮数用尽/连续失败：终止循环，纯文本兜底
                    case .feedback(let content, let event):
                        cont.yield(.toolCall(event))
                        toolRounds += 1
                        validationFailures = (event.status == .rejected) ? validationFailures + 1 : 0
                        // 回填 tool 消息 + assistant 回合头（对齐训练轨迹：tool 结果后模型续写确认话术）
                        var fb: [llama_token] = [Qwen3SpecialToken.imStart]
                        fb += try model.tokenize("tool\n" + content, addSpecial: false)
                        fb.append(Qwen3SpecialToken.imEnd)
                        fb += try model.tokenize("\n", addSpecial: false)
                        fb.append(Qwen3SpecialToken.imStart)
                        fb += try model.tokenize("assistant\n", addSpecial: false)
                        if thinkTags {
                            fb += try thinkBlockTokens(model: model)
                        }
                        try ctx.decode(tokens: fb)
                        accumulated = ""  // 新一轮检测窗口清零
                    }
                }
                token = sampler.sample(ctx)
            }

            let genSeconds = Self.seconds(since: genStart)
            let stats = TokenEvent.Stats(
                tokensPerSecond: Double(generated) / max(genSeconds, 0.001),
                peakMemoryMB: Self.peakRSSMB(),
                promptTokensPerSecond: ppTs
            )
            cont.yield(.stats(stats))
            cont.finish()
        } catch {
            cont.finish(throwing: error)
        }
    }

    /// 桥接工具循环：ToolLoop.process 是 async，但本方法运行在 generation 串行队列上，
    /// 直接 await 会让队列闭包提前返回（后续 C 调用可能撞上 unload 释放的野指针）。
    /// 用信号量把队列线程钉到工具执行完成——工具执行（含确认弹窗等待）期间队列本就无事可做，
    /// 阻塞可接受；unload 的 queue.sync 会自然等在这里，不会抢跑释放。
    private static func awaitToolLoop(
        accumulated: String, tools: [LocalTool], round: Int, validationFailures: Int
    ) -> ToolLoop.TurnOutcome {
        let sem = DispatchSemaphore(value: 0)
        var outcome: ToolLoop.TurnOutcome = .noToolCall
        Task {
            // timeout 传 nil：写操作确认等待的时长由用户决定，引擎不替用户设限
            let o = await ToolLoop.process(
                accumulated: accumulated, tools: tools,
                round: round, validationFailures: validationFailures,
                timeout: nil)
            outcome = o
            sem.signal()
        }
        sem.wait()
        return outcome
    }

    // Qwen3 聊天格式按 token ID 直接拼接（不依赖 GGUF 的字符串→特殊 token 映射）。
    // 原因：训练机自转 GGUF 缺 tokenizer.ggml.added_tokens（旧 gguf-py 只读 tokenizer_config.json），
    // "<|im_end|>" 会被退化成 6 个字面 subword token；而词表本身完整、特殊 token ID 固定，
    // 按 ID 拼接与正确模板分词结果逐 token 等价（特殊 token 在 BPE 中不参与合并，段间无跨边界 merge）
    // 返回 (tokens, systemCount)：systemCount = 首条 system 消息的 token 数（无 system 时为 0），
    // 供 KV 溢出截断时保住工具定义触发文本
    private func chatTokens(model: ModelHandle, messages: [Message]) throws -> (tokens: [llama_token], systemCount: Int) {
        var tokens: [llama_token] = []
        var systemCount = 0
        for (i, m) in messages.enumerated() {
            tokens.append(Qwen3SpecialToken.imStart)
            tokens += try model.tokenize(m.role, addSpecial: false)
            tokens += try model.tokenize("\n" + m.content, addSpecial: false)
            tokens.append(Qwen3SpecialToken.imEnd)
            tokens += try model.tokenize("\n", addSpecial: false)
            if i == 0 && m.role == "system" { systemCount = tokens.count }
        }
        tokens.append(Qwen3SpecialToken.imStart)
        tokens += try model.tokenize("assistant\n", addSpecial: false)
        if thinkTags {
            tokens += try thinkBlockTokens(model: model)
        }
        return (tokens, systemCount)
    }

    // 空思考块（/no_think 项）：SFT3 起训练模板 enable_thinking=false 在每个 assistant 回合头后
    // 注入官方同款空块 <think>\n\n</think>\n\n，模型据此直接作答不思考；
    // SFT2/官方原版训练时无此块 → thinkTags 默认关，避免分布偏移
    private func thinkBlockTokens(model: ModelHandle) throws -> [llama_token] {
        var t: [llama_token] = [Qwen3SpecialToken.think]
        t += try model.tokenize("\n\n", addSpecial: false)
        t.append(Qwen3SpecialToken.thinkEnd)
        t += try model.tokenize("\n\n", addSpecial: false)
        return t
    }

    // Qwen3 词表钉死的特殊 token ID（v3/v3.5 同词表；M3 支持多模型时按 arch 查表）
    private enum Qwen3SpecialToken {
        static let imStart: llama_token = 151644
        static let imEnd: llama_token = 151645
        static let think: llama_token = 151667
        static let thinkEnd: llama_token = 151668
    }

    private static func seconds(since start: DispatchTime) -> Double {
        Double(DispatchTime.now().uptimeNanoseconds - start.uptimeNanoseconds) / 1_000_000_000
    }

    // 峰值常驻内存（与训练侧 /usr/bin/time -l 的 peak RSS 同语义）
    private static func peakRSSMB() -> Int {
        var info = mach_task_basic_info()
        var count = mach_msg_type_number_t(MemoryLayout<mach_task_basic_info>.size / MemoryLayout<natural_t>.size)
        let kr = withUnsafeMutablePointer(to: &info) {
            $0.withMemoryRebound(to: integer_t.self, capacity: Int(count)) {
                task_info(mach_task_self_, task_flavor_t(MACH_TASK_BASIC_INFO), $0, &count)
            }
        }
        guard kr == KERN_SUCCESS else { return 0 }
        return Int(info.resident_size_max) / (1024 * 1024)
    }
}

public enum EngineError: Error, CustomStringConvertible {
    case notLoaded

    public var description: String {
        switch self {
        case .notLoaded: return "模型未加载：先调用 load(_:) 再 generate"
        }
    }
}
