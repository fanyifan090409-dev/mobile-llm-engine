import SwiftUI
import EngineKit
import UIKit
import PhotosUI

// ==================== 数据模型 ====================

enum ChatRole { case user, assistant }

enum StepState: Equatable { case pending, active, done, failed }

struct ProcessStep: Identifiable, Equatable {
    let id = UUID()
    var title: String
    var detail: String?
    var state: StepState
    var elapsed: Double?   // 真实事件时刻 - 发送时刻（秒），非假数据
}

struct ToolResultCard: Equatable {
    var title: String
    var start: String
    var end: String
    var location: String
    var ok: Bool
    var detail: String
}

// 多模型模式专用：展示领队派给哪个工人、子任务与执行结果
struct DispatchCard: Equatable {
    var worker: String
    var task: String
    var ok: Bool
    var detail: String
}

// 工作流可视化：节点状态全部由真实执行事件驱动
enum WorkflowNodeState: Equatable { case pending, active, done, failed }

struct WorkflowTrace: Equatable {
    var leader: WorkflowNodeState = .active
    var worker: WorkflowNodeState = .pending
    var tool: WorkflowNodeState = .pending
    var summary: WorkflowNodeState = .pending
    var usedDispatch = false
    var workerName: String?
    var toolName: String?
    var task: String?
    var resultDetail: String?
    var startedAt: Date
    var finishedAt: Date?
}

struct ChatMessage: Identifiable, Equatable {
    let id = UUID()
    let role: ChatRole
    var text: String
    var steps: [ProcessStep] = []
    var result: ToolResultCard?
    var dispatch: DispatchCard?
    var workflow: WorkflowTrace?
    var statsLine: String?
}

struct DemoPrompt {
    let label: String     // chip 上的短标签
    let text: String      // 完整 prompt（训练分布同款格式）
    let usesTools: Bool   // true=日历工具闭环演示；false=对话式能力演示（翻译等，不传工具白名单）
}

// ==================== 状态模型 ====================

@MainActor
@Observable
final class DemoModel {
    enum Phase { case loading, ready, failed(String) }

    var phase: Phase = .loading
    var messages: [ChatMessage] = []
    var running = false
    var showLog = false
    var successCount = 0     // 工具执行成功计数（触感触发源）
    var reduceMotion = false
    var contextTokens: Int = DemoModel.savedContext
    var speedTier: SpeedTier = DemoModel.savedSpeed
    var showContextPicker = false
    var showOnboarding = false
    var onboardingRunning = false
    var onboardingProgress = 0
    var benchmark: BenchmarkResult?
    var lastScore: Int = UserDefaults.standard.integer(forKey: "lastBenchmarkScore")
    var modelRevision = 0     // 模型文件增删后自增，驱动模型库列表重算

    // 模型档位：速度/权重来自 2026-11-03 iPhone 18 Pro Max 实测（docs/评测/真机跑分对比-17ProMax-vs-18ProMax-20261103.md）
    struct ModelOption: Identifiable {
        let file: String
        let shortTitle: String
        let title: String
        let detail: String
        let speed: String
        let weightGB: Double
        var id: String { file }
    }

    static let modelCatalog = [
        ModelOption(file: "qwen3-1.7b-sft17-Q4_K_M.gguf", shortTitle: "Q4_K_M", title: "Q4_K_M · 1.7B",
                    detail: "最快，日常推荐", speed: "实测 61.1 tok/s", weightGB: 1.28),
        ModelOption(file: "qwen3-1.7b-sft17-Q5_K_M.gguf", shortTitle: "Q5_K_M", title: "Q5_K_M · 1.7B",
                    detail: "质量更好，速度约慢 8%", speed: "实测 56.5 tok/s", weightGB: 1.47),
        ModelOption(file: "qwen3-1.7b-sft17-Q8_0.gguf", shortTitle: "Q8_0", title: "Q8_0 · 1.7B",
                    detail: "质量最高，速度约慢 34%", speed: "实测 40.1 tok/s", weightGB: 2.17),
        ModelOption(file: "qwen3-0.6b-sft3b-Q5_K_M.gguf", shortTitle: "0.6B·Q5", title: "Q5_K_M · 0.6B",
                    detail: "更小更快，复杂任务弱", speed: "实测 100.5 tok/s", weightGB: 0.55),
        ModelOption(file: "qwen3-0.6b-sft3b-Q4_K_M.gguf", shortTitle: "0.6B·Q4", title: "Q4_K_M · 0.6B",
                    detail: "更小更快，质量低于 1.7B", speed: "实测 119.7 tok/s", weightGB: 0.48),
        ModelOption(file: "qwen3-0.6b-sft3b-IQ4_XS.gguf", shortTitle: "0.6B·IQ4", title: "IQ4_XS · 0.6B",
                    detail: "体积最小，低内存机型优先", speed: "实测 121.1 tok/s", weightGB: 0.45),
    ]

    // 多模型协作配对：领队 SFT20（1.7B）+ 工人 SFT20c（0.6B 日期查表版）。
    // 这两个文件不进单模型档位列表——领队离开 dispatch 系统提示会直接吐工具调用。
    static let multiModelLeaderCandidates = [
        "qwen3-1.7b-sft20-Q5_K_M.gguf",
        "qwen3-1.7b-sft20-Q4_K_M.gguf",
    ]
    static let multiModelWorkerCandidates = [
        "qwen3-0.6b-sft20c-Q5_K_M.gguf",
        "qwen3-0.6b-sft20c-Q4_K_M.gguf",
    ]

    static func multiModelPair() -> (leader: URL, worker: URL)? {
        guard let leader = multiModelLeaderCandidates.compactMap({ url(forModelFile: $0) }).first,
              let worker = multiModelWorkerCandidates.compactMap({ url(forModelFile: $0) }).first else {
            return nil
        }
        return (leader, worker)
    }

    // 已装模型 = Documents/Models + App 内置的全部 .gguf；
    // 已知档位沿用实测元数据，用户导入的未知文件按体积生成条目；
    // 排序按内置推荐顺序，未知模型排最后
    static var availableModels: [ModelOption] {
        allModelURLs()
            // 双模型配对文件只走「多模型协作」入口；单模型选它会缺 dispatch 系统提示
            .filter {
                !multiModelLeaderCandidates.contains($0.lastPathComponent)
                    && !multiModelWorkerCandidates.contains($0.lastPathComponent)
            }
            .map(option(for:)).sorted {
                let a = catalogRank($0.file), b = catalogRank($1.file)
                return a == b ? $0.file < $1.file : a < b
            }
    }

    static func catalogRank(_ file: String) -> Int {
        modelCatalog.firstIndex(where: { $0.file == file }) ?? Int.max
    }

    static var modelsDirectory: URL {
        FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("Models")
    }

    private static var modelDirectories: [URL] {
        [modelsDirectory, Bundle.main.bundleURL.appendingPathComponent("Models")]
    }

    // Documents 优先于 bundle：同名文件以可写目录里的版本为准
    private static func allModelURLs() -> [URL] {
        var seen = Set<String>()
        var result: [URL] = []
        for dir in modelDirectories {
            let files = (try? FileManager.default.contentsOfDirectory(
                at: dir, includingPropertiesForKeys: [.fileSizeKey])) ?? []
            for url in files.sorted(by: { $0.lastPathComponent < $1.lastPathComponent })
            where url.pathExtension.lowercased() == "gguf" && !seen.contains(url.lastPathComponent) {
                seen.insert(url.lastPathComponent)
                result.append(url)
            }
        }
        return result
    }

    static func option(for url: URL) -> ModelOption {
        if let known = modelCatalog.first(where: { $0.file == url.lastPathComponent }) {
            return known
        }
        let bytes = (try? url.resourceValues(forKeys: [.fileSizeKey]).fileSize) ?? 0
        return ModelOption(file: url.lastPathComponent, shortTitle: shortName(for: url),
                           title: url.deletingPathExtension().lastPathComponent,
                           detail: "导入的模型", speed: "速度未实测",
                           weightGB: Double(bytes) / 1_000_000_000)
    }

    // 未知文件的短名取文件名最后一个「-」段（GGUF 命名尾段通常是量化标签）
    static func shortName(for url: URL) -> String {
        let base = url.deletingPathExtension().lastPathComponent
        return base.components(separatedBy: "-").last.flatMap { $0.isEmpty ? nil : $0 } ?? base
    }

    private var currentModelURL: URL?

    var currentModelFile: String? { currentModelURL?.lastPathComponent }

    var modelShortLabel: String {
        if multiModelActive { return "双模型" }
        guard let url = currentModelURL else { return "模型" }
        if let known = Self.modelCatalog.first(where: { $0.file == url.lastPathComponent }) {
            return known.shortTitle
        }
        return Self.shortName(for: url)
    }

    // 双模型峰值 = 领队权重 + 领队 KV + 工人权重 + 工人 2K KV + 运行时缓冲
    static func multiModelPeakGB(contextTokens: Int) -> Double {
        guard let pair = multiModelPair() else { return 0 }
        func gb(_ url: URL) -> Double {
            Double((try? url.resourceValues(forKeys: [.fileSizeKey]).fileSize) ?? 0) / 1_000_000_000
        }
        return gb(pair.leader) + gb(pair.worker)
            + Double(contextTokens) / 1024.0 * 0.11 + 2.0 / 1024.0 * 0.11 + 0.4
    }

    // MARK: 模型库（导入 / 删除 / 切换）

    struct InstalledModel: Identifiable {
        let option: ModelOption
        let url: URL
        let sizeMB: Double
        let isBundled: Bool
        let isCurrent: Bool
        var id: String { option.file }
        var isCataloged: Bool { DemoModel.modelCatalog.contains { $0.file == option.file } }
    }

    // 每次访问重新扫描目录；modelRevision 变化驱动模型库列表刷新
    func installedModels() -> [InstalledModel] {
        _ = modelRevision
        return Self.allModelURLs().map { url in
            let bytes = (try? url.resourceValues(forKeys: [.fileSizeKey]).fileSize) ?? 0
            return InstalledModel(
                option: Self.option(for: url),
                url: url,
                sizeMB: Double(bytes) / 1_000_000,
                isBundled: url.path.hasPrefix(Bundle.main.bundleURL.path),
                isCurrent: url.lastPathComponent == currentModelURL?.lastPathComponent)
        }
        .sorted {
            let a = Self.catalogRank($0.option.file), b = Self.catalogRank($1.option.file)
            return a == b ? $0.option.file < $1.option.file : a < b
        }
    }

    enum ModelLibraryError: LocalizedError {
        case duplicate(String)
        case copyFailed(String, Error)
        case builtIn
        case inUse
        case multiModelInUse

        var errorDescription: String? {
            switch self {
            case .duplicate(let name): return "「\(name)」已在模型库中，无需重复导入。"
            case .copyFailed(let name, let error): return "导入「\(name)」失败：\(error.localizedDescription)"
            case .builtIn: return "内置模型随安装包分发，不能删除。"
            case .inUse: return "正在使用的模型不能删除，请先切换到其他模型。"
            case .multiModelInUse: return "双模型协作正在使用该文件，请先关闭多模型模式。"
            }
        }
    }

    // 导入：安全作用域读取 + 后台拷贝进 Documents/Models（1–2 GB 文件不卡 UI）
    func importModel(from source: URL) async throws {
        let filename = source.lastPathComponent
        let destDir = Self.modelsDirectory
        try FileManager.default.createDirectory(at: destDir, withIntermediateDirectories: true)
        let dest = destDir.appendingPathComponent(filename)
        guard !FileManager.default.fileExists(atPath: dest.path) else {
            throw ModelLibraryError.duplicate(filename)
        }
        let accessing = source.startAccessingSecurityScopedResource()
        defer { if accessing { source.stopAccessingSecurityScopedResource() } }
        do {
            try await Task.detached(priority: .userInitiated) {
                try FileManager.default.copyItem(at: source, to: dest)
            }.value
        } catch {
            try? FileManager.default.removeItem(at: dest)
            throw ModelLibraryError.copyFailed(filename, error)
        }
        modelRevision += 1
        log.log("模型导入完成：\(filename)（\(dest.path)）")
    }

    func deleteModel(_ installed: InstalledModel) throws {
        guard !installed.isBundled else { throw ModelLibraryError.builtIn }
        guard !installed.isCurrent else { throw ModelLibraryError.inUse }
        if multiModelActive && (Self.multiModelLeaderCandidates.contains(installed.option.file)
                                || Self.multiModelWorkerCandidates.contains(installed.option.file)) {
            throw ModelLibraryError.multiModelInUse
        }
        try FileManager.default.removeItem(at: installed.url)
        modelRevision += 1
        log.log("模型删除：\(installed.option.file)")
    }

    func useModel(_ installed: InstalledModel) async {
        guard !installed.isCurrent else { return }
        await switchModel(to: installed.option)
    }

    // 上下文档位：KV 缓存按 112KB/token 估算（1.7B：28 层 × 8 KV 头 × 128 维 × 2 字节 × f16）
    struct ContextOption: Identifiable {
        let tokens: Int
        let title: String
        let detail: String
        let cost: String
        var id: Int { tokens }
    }

    static let contextOptions = [
        ContextOption(tokens: 4096, title: "4K", detail: "日常对话，推荐",
                      cost: "KV 约 0.44 GB"),
        ContextOption(tokens: 8192, title: "8K", detail: "长文档、多轮追问",
                      cost: "KV 约 0.88 GB"),
        ContextOption(tokens: 16384, title: "16K", detail: "超长文本，8GB 机型慎选",
                      cost: "KV 约 1.75 GB"),
        ContextOption(tokens: 32768, title: "32K", detail: "仅 12GB 机型，可能被系统终止",
                      cost: "KV 约 3.5 GB"),
    ]

    private static var savedContext: Int {
        // 键名带 window 前缀：避免与命令行调试参数（-contextTokens）混用后被 cfprefsd 落盘污染
        let v = UserDefaults.standard.integer(forKey: "contextWindowTokens")
        return contextOptions.contains(where: { $0.tokens == v }) ? v : 4096
    }

    private static var savedSpeed: SpeedTier {
        let raw = UserDefaults.standard.object(forKey: "speedTier") as? Int ?? SpeedTier.balanced.rawValue
        return SpeedTier(rawValue: raw) ?? .balanced
    }

    static func speedTitle(_ tier: SpeedTier) -> String {
        switch tier {
        case .powerSaver: return "节能"
        case .balanced: return "均衡"
        case .performance: return "高性能"
        case .turbo: return "极速"
        }
    }

    // 训练分布同款 prompt（synthesize_sft build_schedule 逐字格式；「今天是…」锚点由 send 运行时前置）：
    // 活动/时间短语/地点均取自合成期词表（eval_toolcall.py 同源分布）；
    // 翻译演示用训练池句式（Q4_K_M 冒烟实测可用，泛化窄于日历——SFT19/20 数据补宽）
    static let demoPrompts = [
        DemoPrompt(label: "家长会 · 明天下午三点 · 学校",
                   text: "帮我在手机日历里加一个事件：家长会，时间明天下午三点，地点学校，时长约一小时。",
                   usesTools: true),
        DemoPrompt(label: "健身私教课 · 周五晚上七点 · 健身房",
                   text: "帮我在手机日历里加一个事件：健身私教课，时间周五晚上七点，地点健身房，时长约一小时。",
                   usesTools: true),
        DemoPrompt(label: "翻译 · 中译英",
                   text: "翻译成英文：快递到哪了",
                   usesTools: false),
        DemoPrompt(label: "翻译 · 英译中",
                   text: "翻译成中文：Please turn on the air conditioner.",
                   usesTools: false),
        DemoPrompt(label: "总结 · 三句话",
                   text: "用三句话总结下面这段话：本地推理把模型放在手机里，数据不出设备，断网也能用。缺点是模型小，复杂推理有限。",
                   usesTools: false),
        DemoPrompt(label: "问答 · 雅思写作",
                   text: "用三句话说明雅思写作 Task 2 的评分标准。",
                   usesTools: false),
    ]

    private let engine = EngineCore()
    private var history: [Message] = []   // 多轮对话历史：引擎每轮清 KV，完整历史靠这里重发
    private let log = AppLog.shared

    // 多模型协作：enabled 是用户开关，active 是本次进程真正跑着的模式
    // （harness/bench 强制单模型，避免自动回归口径被实验模式污染）
    private(set) var multiModelEnabled = UserDefaults.standard.bool(forKey: "multiModelEnabled")
    private(set) var multiModelActive = false
    private(set) var multiModelBusy = false
    private(set) var workflowVisualizationEnabled =
        (UserDefaults.standard.object(forKey: "workflowVisualizationEnabled") as? Bool) ?? true
    private var dispatcher: WorkerDispatcher?
    private var dispatchToolRegistered = false
    private var activeWorkflowIndex: Int?

    // 手动输入意图路由：只有明确要写日历/提醒的句子才注入工具定义。
    // 训练分布里「非日历请求 + 工具 system」从未共现，任意输入都塞工具会诱发误调用
    nonisolated static func looksLikeCalendarRequest(_ text: String) -> Bool {
        // 翻译/解释类优先判非工具：句中可能夹带「开会」「行程」等词，但意图不是写日历
        if text.contains("翻译") || text.contains("译成") || text.contains("英文") || text.contains("中文") {
            return false
        }
        let cues = ["日历", "日程", "会议", "开会", "预约", "安排", "行程", "事件",
                    "提醒", "面试", "就诊", "聚会", "约会", "接机", "上课", "课程"]
        return cues.contains { text.contains($0) }
    }

    // 训练 user 格式：「今天是2026年11月3日（周二）。帮我…」（synthesize_sft build_schedule 同款锚点）。
    // 推理必须前置真实日期，模型才能把「明天/周五」换算成正确日期；缺锚点会让事件落到错误日子
    nonisolated static func todayAnchor(now: Date = Date()) -> String {
        let c = Calendar.current.dateComponents([.year, .month, .day, .weekday], from: now)
        let weekday = ["日", "一", "二", "三", "四", "五", "六"][((c.weekday ?? 1) - 1) % 7]
        return "今天是\(c.year ?? 0)年\(c.month ?? 0)月\(c.day ?? 0)日（周\(weekday)）。"
    }

    // 工具轮 user 内容：日期锚点 + 相对日期/时间显式提示 + 用户原文。
    // 1.7B 日期算术弱（周五→周四、晚上八点→18:00 实测），提示串只进模型上下文，气泡仍显示原文
    nonisolated static func toolContent(_ text: String) -> String {
        todayAnchor() + TimeHints.describe(text) + text
    }

    // 启动时判定是否跑回归套件（Documents/harness.run 内容为 go）
    static var harnessRequested: Bool {
        let docs = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
        return flagIsGo(docs.appendingPathComponent("harness.run"))
    }

    // 自动跑分固定 4K，用户切档不影响跑分矩阵的可比性
    static var benchRequested: Bool {
        let docs = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
        return flagIsGo(docs.appendingPathComponent("bench.run"))
    }

    static func flagIsGo(_ url: URL) -> Bool {
        guard let text = try? String(contentsOf: url, encoding: .utf8) else { return false }
        return text.trimmingCharacters(in: .whitespacesAndNewlines) == "go"
    }

    func loadModel() async {
        // llama.cpp 内部日志（load 时打印 EOG token 列表等）转发进壳日志——真机排障唯一通道
        CLLaMABackend.logHook = { line in
            DispatchQueue.main.async { AppLog.shared.log("llama: \(line)") }
        }
        do {
            // harness 模式跳过日历确认弹窗（自动回归）；演示模式保持每次人工确认
            try engine.registerTool(CalendarTool(autoConfirm: Self.harnessRequested))
            try engine.registerTool(ReminderTool())
            // math_eval 只注册进 registry，不主动进提示词：每轮请求按白名单决定是否启用（见 runGeneration）
            if !Self.harnessRequested && !Self.benchRequested {
                try engine.registerTool(MathEvalTool(engine: MathEvalEngine(resourceDirectory: "Math")))
            }
        } catch { log.log("工具注册失败：\(error)") }
        log.log("开始装载模型…")

        // 自动回归/跑分强制单模型，保证口径可比；用户开关状态保留，下次正常启动恢复
        let automatic = Self.harnessRequested || Self.benchRequested
        let pair = Self.multiModelPair()
        if multiModelEnabled && pair == nil {
            multiModelEnabled = false
            UserDefaults.standard.set(false, forKey: "multiModelEnabled")
            log.log("多模型开关已开但配对模型缺失，回退单模型")
        }
        var useMulti = multiModelEnabled && pair != nil && !automatic
        if useMulti, let pair {
            if prepareDispatcher(pair) {
                log.log("多模型模式：领队 \(pair.leader.lastPathComponent)，工人 \(pair.worker.lastPathComponent)")
            } else {
                useMulti = false
            }
        }

        let url = useMulti ? pair?.leader : Self.findModel()
        guard let url else {
            phase = .failed("未找到模型文件（Documents/Models 或 bundle 内嵌均无）")
            log.log("未找到模型文件（Documents/Models 或 bundle 内嵌均无）")
            return
        }
        currentModelURL = url
        log.log("模型路径：\(url.path)")
        // 自动模式固定 4K（保证回归/跑分数据可比）；演示模式用用户选的档位
        let ctx = automatic ? 4096 : contextTokens
        log.log("上下文档位：\(ctx) tokens")
        // thinkTags: true——SFT17 用 --no-think 训练（模板 enable_thinking=false，每回合头注入空思考块），
        // 推理侧必须同款注入；缺失时模型会把 system 提示当正文续写（真机复读根因，2026-11-03 实测）
        let spec = ModelSpec(fileURL: url, quant: Self.quantLabel(url), context: ctx, thinkTags: true)
        do {
            try await engine.load(spec)
            multiModelActive = useMulti
            phase = .ready
            log.log("模型加载完成（\(useMulti ? "双模型" : "单模型")）")
            log.log("设备：\(UIDevice.current.name)（\(Self.deviceModelIdentifier())，iOS \(UIDevice.current.systemVersion)）")
            // 自动执行开关（空文件=演示模式，推送内容后重启 App 生效）：
            // harness.run=go 跑场景回归套件（优先）；bench.run=go 跑短文跑分
            let docs = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
            if Self.flagIsGo(docs.appendingPathComponent("harness.run")) {
                log.log("检测到 harness.run=go：进入场景回归模式")
                Task { await self.runHarness() }
            } else if Self.flagIsGo(docs.appendingPathComponent("bench.run")) {
                log.log("检测到 bench.run=go：进入自动跑分模式")
                Task { await self.runBench() }
            } else if !UserDefaults.standard.bool(forKey: "benchmarkDone") {
                log.log("首次启动：自动跑分并给出推荐配置")
                Task { await self.runOnboardingBenchmark() }
            }
        } catch {
            phase = .failed("模型加载失败")
            log.log("模型加载失败：\(error)")
        }
    }

    // MARK: 多模型协作

    enum MultiModelSwitchError: LocalizedError {
        case modelsMissing
        case dispatchToolUnavailable
        case noFallbackModel
        var errorDescription: String? {
            switch self {
            case .modelsMissing: return "缺少 SFT20 领队或 SFT20c 工人模型"
            case .dispatchToolUnavailable: return "派单工具注册失败"
            case .noFallbackModel: return "没有可回退的单模型文件"
            }
        }
    }

    // 首启/恢复双模型：工人引擎由 WorkerDispatcher 懒加载，四种工人共用同一份 0.6B
    @discardableResult
    private func prepareDispatcher(_ pair: (leader: URL, worker: URL)) -> Bool {
        let dispatcher: WorkerDispatcher
        if let existing = self.dispatcher {
            dispatcher = existing
        } else {
            let new = WorkerDispatcher(profiles: WorkerProfiles.sft20(
                workerModelURL: pair.worker,
                quant: Self.quantLabel(pair.worker),
                context: 2048))
            self.dispatcher = new
            dispatcher = new
        }
        guard !dispatchToolRegistered else { return true }
        // 工人工具在 executor 内现建：CalendarTool/ReminderTool 每次写操作仍走系统弹窗确认
        let executor: DispatchTool.Executor = { call in
            let args: [String: Any] = call.arguments.mapValues { $0 as Any }
            switch call.toolName {
            case "add_calendar_event":
                let result = try await CalendarTool().execute(args)
                guard result.status == "ok" else { return result }
                let title = call.arguments["title"] ?? ""
                let start = call.arguments["start_time"] ?? ""
                let end = call.arguments["end_time"] ?? ""
                let location = call.arguments["location"] ?? ""
                let place = location.isEmpty ? "" : "，地点：\(location)"
                return ToolResult(status: "ok", content: "已添加日历事件：\(title)，\(start)-\(end)\(place)")
            case "set_reminder":
                let result = try await ReminderTool().execute(args)
                guard result.status == "ok" else { return result }
                return ToolResult(status: "ok",
                                  content: "已设置提醒：\(call.arguments["content"] ?? "")，\(call.arguments["remind_time"] ?? "")")
            case "translate_text", "summarize_text":
                return ToolResult(status: "error", content: "移动端暂未接入 \(call.toolName) 执行器")
            default:
                return ToolResult(status: "error", content: "未知工人工具：\(call.toolName)")
            }
        }
        do {
            let onStage: @Sendable (DispatchStage) -> Void = { [weak self] stage in
                Task { @MainActor in self?.applyDispatchStage(stage) }
            }
            try engine.registerTool(DispatchTool(dispatcher: dispatcher, executor: executor, onStage: onStage))
            dispatchToolRegistered = true
            return true
        } catch {
            log.log("派单工具注册失败：\(error)")
            return false
        }
    }

    func setWorkflowVisualization(_ enabled: Bool) {
        workflowVisualizationEnabled = enabled
        UserDefaults.standard.set(enabled, forKey: "workflowVisualizationEnabled")
        log.log("工作流可视化：\(enabled ? "开" : "关")")
    }

    // 派单进度回调全部来自 EngineKit 真实阶段；只更新当前这条消息的工作流
    private func applyDispatchStage(_ stage: DispatchStage) {
        guard let idx = activeWorkflowIndex, messages.indices.contains(idx),
              var trace = messages[idx].workflow else { return }
        switch stage {
        case .started(let worker, let task):
            trace.usedDispatch = true
            trace.leader = .done
            trace.worker = .active
            trace.workerName = worker
            trace.task = task
        case .workerOutput(let worker, let toolName, _):
            trace.workerName = worker
            trace.worker = .done
            trace.toolName = toolName
            trace.tool = .active
        case .finished(let worker, let toolName, let status, let detail):
            trace.workerName = worker
            trace.toolName = toolName
            trace.resultDetail = detail
            if toolName.isEmpty {
                // 工人没产出工具调用（未知工人/解析失败）：工具节点不点亮
                trace.worker = status == "ok" ? trace.worker : .failed
            } else {
                trace.worker = .done
                trace.tool = status == "ok" ? .done : .failed
            }
            trace.summary = .active
        }
        messages[idx].workflow = trace
    }

    static func multiModelSystem(now: Date = Date()) -> String {
        WorkerProfiles.leaderSystemPrompt + "\n" + DateHint.todayLine(for: now)
    }

    private func requestMessages(multi: Bool) -> [Message] {
        guard multi else { return history }
        return [Message(role: "system", content: Self.multiModelSystem())] + history
    }

    func setMultiModel(_ enabled: Bool) async {
        guard case .ready = phase, !running, !multiModelBusy,
              enabled != multiModelEnabled else { return }
        guard !Self.harnessRequested && !Self.benchRequested else {
            log.log("自动回归/跑分模式不支持切换多模型")
            return
        }
        if enabled, Self.multiModelPair() == nil {
            log.log("多模型模型缺失：需要 SFT20 领队 + SFT20c 工人")
            return
        }
        let pair = enabled ? Self.multiModelPair() : nil

        let previousURL = currentModelURL
        let previousActive = multiModelActive
        let previousEnabled = multiModelEnabled
        multiModelBusy = true
        running = true
        phase = .loading
        log.log(enabled ? "开启多模型模式（重新加载领队）" : "关闭多模型模式（恢复单模型）")
        do {
            if enabled {
                guard let pair else { throw MultiModelSwitchError.modelsMissing }
                guard prepareDispatcher(pair) else { throw MultiModelSwitchError.dispatchToolUnavailable }
                try await engine.load(ModelSpec(fileURL: pair.leader, quant: Self.quantLabel(pair.leader),
                                                context: contextTokens, thinkTags: true))
                currentModelURL = pair.leader
                multiModelActive = true
                multiModelEnabled = true
            } else {
                await dispatcher?.unloadAll()
                guard let url = Self.findModel() else { throw MultiModelSwitchError.noFallbackModel }
                try await engine.load(ModelSpec(fileURL: url, quant: Self.quantLabel(url),
                                                context: contextTokens, thinkTags: true))
                currentModelURL = url
                multiModelActive = false
                multiModelEnabled = false
            }
            UserDefaults.standard.set(enabled, forKey: "multiModelEnabled")
            phase = .ready
            log.log(enabled ? "多模型模式已开启" : "已恢复单模型模式")
        } catch {
            log.log("多模型模式切换失败：\(error)，回退原模型")
            if let previousURL {
                try? await engine.load(ModelSpec(fileURL: previousURL, quant: Self.quantLabel(previousURL),
                                                 context: contextTokens, thinkTags: true))
            }
            currentModelURL = previousURL
            multiModelActive = previousActive
            multiModelEnabled = previousEnabled
            phase = .ready
        }
        running = false
        multiModelBusy = false
    }

    // 切上下文档位需要重建 KV 缓存（权重也随 load 重载，约 2 秒）；
    // 失败自动回退旧档位并重载，避免把 App 卡在无法使用的档位上
    func switchContext(to tokens: Int) async {
        guard case .ready = phase, !running, tokens != contextTokens,
              Self.contextOptions.contains(where: { $0.tokens == tokens }),
              let url = currentModelURL ?? Self.findModel() else { return }
        let previous = contextTokens
        running = true
        contextTokens = tokens
        phase = .loading
        log.log("切换上下文：\(tokens) tokens（重新加载模型）")
        do {
            try await engine.load(ModelSpec(fileURL: url, quant: Self.quantLabel(url), context: tokens, thinkTags: true))
            UserDefaults.standard.set(tokens, forKey: "contextWindowTokens")
            phase = .ready
            log.log("上下文切换完成：\(tokens) tokens，历史 \(history.count) 条保留")
        } catch {
            contextTokens = previous
            log.log("上下文切换失败：\(error)，回退 \(previous) tokens")
            try? await engine.load(ModelSpec(fileURL: url, quant: Self.quantLabel(url), context: previous, thinkTags: true))
            phase = .ready
        }
        running = false
    }

    // 切换模型档位：重新加载权重 + 当前上下文档位；失败回退原模型
    func switchModel(to option: ModelOption) async {
        guard case .ready = phase, !running, !multiModelActive,
              let url = Self.url(forModelFile: option.file),
              url != currentModelURL else { return }
        let previousURL = currentModelURL
        running = true
        phase = .loading
        log.log("切换模型：\(option.file)（重新加载）")
        do {
            try await engine.load(ModelSpec(fileURL: url, quant: Self.quantLabel(url),
                                            context: contextTokens, thinkTags: true))
            currentModelURL = url
            UserDefaults.standard.set(option.file, forKey: "modelFile")
            phase = .ready
            log.log("模型切换完成：\(option.file)，历史 \(history.count) 条保留")
        } catch {
            log.log("模型切换失败：\(error)，回退 \(previousURL?.lastPathComponent ?? "原模型")")
            if let previousURL {
                try? await engine.load(ModelSpec(fileURL: previousURL, quant: Self.quantLabel(previousURL),
                                                 context: contextTokens, thinkTags: true))
            }
            phase = .ready
        }
        running = false
    }

    private static func url(forModelFile file: String) -> URL? {
        let docs = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("Models/\(file)")
        if FileManager.default.fileExists(atPath: docs.path) { return docs }
        let bundle = Bundle.main.bundleURL.appendingPathComponent("Models/\(file)")
        return FileManager.default.fileExists(atPath: bundle.path) ? bundle : nil
    }

    // 速度档只影响下一次生成的线程数/功耗，不需要重载模型
    func setSpeedTier(_ tier: SpeedTier) {
        speedTier = tier
        UserDefaults.standard.set(tier.rawValue, forKey: "speedTier")
        log.log("速度档位：\(Self.speedTitle(tier))（下一次生成生效）")
    }

    // 首启跑分：自动执行，结果页给出推荐配置
    func startBenchmark() {
        guard case .ready = phase, !onboardingRunning else { return }
        showOnboarding = true
        Task { await runOnboardingBenchmark() }
    }

    func runOnboardingBenchmark() async {
        guard case .ready = phase, !onboardingRunning else { return }
        onboardingRunning = true
        onboardingProgress = 0
        benchmark = nil
        showOnboarding = true
        log.log("首启跑分：开始（4 轮标准短文）")
        let label = "\(modelShortLabel) · \(contextTokens / 1024)K"
        let result = await DeviceBenchmark.measure(engine: engine, modelLabel: label) { round in
            self.onboardingProgress = round
            self.log.log("首启跑分：第 \(round)/4 轮")
        }
        benchmark = result
        lastScore = result.score
        UserDefaults.standard.set(result.score, forKey: "lastBenchmarkScore")
        UserDefaults.standard.set(true, forKey: "benchmarkDone")
        onboardingRunning = false
        log.log("首启跑分完成：\(result.score) 分（\(result.stableTps) tok/s，峰值 \(result.peakMB) MB）")
    }

    func skipOnboarding() {
        showOnboarding = false
        UserDefaults.standard.set(true, forKey: "benchmarkDone")
        log.log("首启跑分：用户跳过，保留当前配置")
    }

    // 分数 → 推荐配置；模型不存在时回退到实际可用的档位
    func recommendation(for result: BenchmarkResult) -> BenchmarkRecommendation? {
        let models = Self.availableModels
        func pick(_ file: String) -> ModelOption? { models.first(where: { $0.file == file }) }
        let q5 = pick("qwen3-1.7b-sft17-Q5_K_M.gguf")
        let q4 = pick("qwen3-1.7b-sft17-Q4_K_M.gguf")
        let smallQ4 = pick("qwen3-0.6b-sft3b-Q4_K_M.gguf")
        let smallIQ = pick("qwen3-0.6b-sft3b-IQ4_XS.gguf")
        let smallQ5 = pick("qwen3-0.6b-sft3b-Q5_K_M.gguf")

        let chosen: (ModelOption?, Int, SpeedTier, String, String)
        switch BenchmarkTier.of(result.score) {
        case .strong:
            chosen = (q5 ?? q4, 8192, .balanced, "高质量",
                      "本机可流畅运行 1.7B 高质量档；8K 上下文适合长文档与多轮追问。")
        case .steady:
            chosen = (q4 ?? q5, 8192, .balanced, "均衡",
                      "1.7B 日常档配 8K 上下文，速度与内存余量较稳妥。")
        case .enough:
            chosen = (q4 ?? q5, 4096, .balanced, "稳妥",
                      "保留 1.7B 能力，但上下文收到 4K，避免内存压力。")
        case .light:
            chosen = (smallQ4 ?? smallIQ ?? smallQ5, 4096, .powerSaver, "轻量",
                      "建议 0.6B + 4K + 节能档，优先保证响应和内存余量。")
        }
        guard let picked = chosen.0 else { return nil }
        let peak = picked.weightGB + Double(chosen.1) / 1024.0 * 0.11 + 0.2
        return BenchmarkRecommendation(
            modelFile: picked.file,
            title: "\(picked.shortTitle) · \(chosen.1 / 1024)K · \(Self.speedTitle(chosen.2))",
            reason: chosen.4,
            cost: "权重 \(String(format: "%.2f", picked.weightGB)) GB · 峰值约 \(String(format: "%.1f", peak)) GB · \(picked.speed)",
            contextTokens: chosen.1,
            speed: chosen.2)
    }

    func applyRecommendation(_ rec: BenchmarkRecommendation) async {
        if let file = rec.modelFile, file != currentModelURL?.lastPathComponent,
           let picked = Self.availableModels.first(where: { $0.file == file }) {
            await switchModel(to: picked)
        }
        if rec.contextTokens != contextTokens, case .ready = phase {
            await switchContext(to: rec.contextTokens)
        }
        setSpeedTier(rec.speed)
        showOnboarding = false
    }

    func send(_ raw: String, usesTools: Bool = true, contextHint: String? = nil) {
        let text = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        guard case .ready = phase, !running, !text.isEmpty else { return }
        running = true
        let sendAt = Date()
        let multi = multiModelActive
        // 滑窗截断：只留最近 4 轮（8 条）。历史无限增长时每轮全量重发，
        // 真机实测十几轮后解码掉到 9.4 tok/s（tech-debt #4）
        if history.count > 8 { history.removeFirst(history.count - 8) }
        // 单模型工具轮前置日期锚点与时间提示；双模型交给领队 system 日期行，user 保持原文
        var content = multi ? text : (usesTools ? Self.toolContent(text) : text)
        if let contextHint { content = contextHint + content }
        history.append(Message(role: "user", content: content))
        log.log("开始生成：\(content)")
        messages.append(ChatMessage(role: .user, text: text))
        let mathModel = currentModelURL?.lastPathComponent.contains("sft27") == true
        let steps = multi
            ? [ProcessStep(title: "领队理解", detail: nil, state: .active, elapsed: nil),
               ProcessStep(title: "工人执行", detail: nil, state: .pending, elapsed: nil),
               ProcessStep(title: "汇总回复", detail: nil, state: .pending, elapsed: nil)]
            : [ProcessStep(title: "理解意图", detail: nil, state: .active, elapsed: nil),
               ProcessStep(title: (usesTools || mathModel) ? "调用工具" : "组织回复", detail: nil, state: .pending, elapsed: nil),
               ProcessStep(title: "执行结果", detail: nil, state: .pending, elapsed: nil)]
        let workflow: WorkflowTrace? = (multi && workflowVisualizationEnabled)
            ? WorkflowTrace(startedAt: sendAt)
            : nil
        messages.append(ChatMessage(role: .assistant, text: "", steps: steps, workflow: workflow))
        let idx = messages.count - 1
        Task { await runGeneration(idx: idx, sendAt: sendAt, usesTools: usesTools) }
    }

    // 步骤状态机由真实事件驱动：首 token → 步骤1 done；toolCall → 步骤2 done、步骤3 active；
    // 工具 executed → 步骤3 done。无工具轮次收尾时改写为两步语义（理解意图/组织回复）
    private func runGeneration(idx: Int, sendAt: Date, usesTools: Bool = true) async {
        activeWorkflowIndex = messages.indices.contains(idx) && messages[idx].workflow != nil ? idx : nil
        defer { activeWorkflowIndex = nil }
        var full = ""
        var sawToken = false
        var sawTool = false
        var toolEvent: ToolCallEvent?
        let multi = multiModelActive
        let mathModel = currentModelURL?.lastPathComponent.contains("sft27") == true
        do {
            for try await event in engine.generate(GenerationRequest(
                messages: requestMessages(multi: multi),
                maxTokens: 256, temperature: mathModel ? 0.2 : 0.7,
                speed: Self.benchRequested ? .balanced : speedTier,
                tools: multi ? ["dispatch_to_worker"] : (mathModel ? ["math_eval"] : (usesTools ? ["add_calendar_event"] : nil)))) {
                switch event {
                case .token(let t):
                    if !sawToken {
                        sawToken = true
                        stepDone(idx, 0, sendAt)
                        stepActive(idx, 1, sendAt)
                    }
                    full += t
                    messages[idx].text = full
                case .toolCall(let e):
                    sawTool = true
                    toolEvent = e
                    let statusText: String
                    switch e.status {
                    case .executed: statusText = "executed"
                    case .rejected: statusText = "rejected"
                    case .failed: statusText = "failed"
                    }
                    log.log("工具事件：\(e.toolName) 参数=\(e.arguments) 状态=\(statusText) 结果=\(e.resultText)")
                    if multi {
                        let worker = e.arguments["worker"] ?? e.toolName
                        stepDone(idx, 1, sendAt, detail: worker)
                        stepActive(idx, 2, sendAt)
                        messages[idx].dispatch = DispatchCard(
                            worker: worker,
                            task: e.arguments["task"] ?? "",
                            ok: e.status == .executed,
                            detail: e.resultText)
                        if var wf = messages[idx].workflow {
                            wf.usedDispatch = true
                            wf.leader = .done
                            wf.workerName = worker
                            if wf.worker == .active { wf.worker = .done }
                            if wf.toolName != nil {
                                wf.tool = e.status == .executed ? .done : .failed
                            }
                            wf.resultDetail = e.resultText
                            wf.summary = .active
                            messages[idx].workflow = wf
                        }
                        if e.status == .executed { successCount += 1 }
                    } else {
                        stepDone(idx, 1, sendAt, detail: "add_calendar_event · \(e.arguments["title"] ?? "")")
                        stepActive(idx, 2, sendAt)
                        messages[idx].result = Self.resultCard(e)
                        if e.status == .executed {
                            stepDone(idx, 2, sendAt, detail: "已写入系统日历")
                            successCount += 1
                        }
                    }
                case .stats(let s):
                    messages[idx].statsLine = String(format: "解码 %.1f tok/s · 峰值内存 %d MB",
                                                     s.tokensPerSecond, s.peakMemoryMB)
                    log.log(String(format: "统计：解码 %.1f tok/s | 预填充 %.1f tok/s | 峰值内存 %d MB",
                                   s.tokensPerSecond, s.promptTokensPerSecond, s.peakMemoryMB))
                }
            }
            // 流结束收尾：把真实终态钉进界面，避免步骤状态悬空
            if !sawToken {
                if sawTool {
                    stepDone(idx, 0, sendAt)
                } else {
                    stepFailed(idx, 0, sendAt, detail: "模型无输出")
                }
            }
            if !sawTool {
                messages[idx].steps[1].title = multi ? "汇总回复" : "组织回复"
                stepDone(idx, 1, sendAt)
                messages[idx].steps.remove(at: 2)
            } else if multi {
                stepDone(idx, 2, sendAt, detail: "已汇总")
            } else if messages[idx].steps[2].state != .done, let e = toolEvent {
                switch e.status {
                case .executed:
                    stepDone(idx, 2, sendAt, detail: "已写入系统日历")
                case .rejected:
                    stepFailed(idx, 2, sendAt, detail: "校验未通过")
                case .failed:
                    stepFailed(idx, 2, sendAt, detail: "未完成")
                }
            }
            if var wf = messages[idx].workflow {
                if !sawTool {
                    wf.leader = wf.leader == .failed ? .failed : .done
                    wf.summary = .done
                } else {
                    if wf.worker == .active { wf.worker = .done }
                    if wf.summary != .failed { wf.summary = .done }
                }
                wf.finishedAt = Date()
                messages[idx].workflow = wf
            }
            history.append(Message(role: "assistant", content: full))
            log.log("生成结束（\(full.count) 字符）")
            // 输出正文入日志——真机无控制台，文件是唯一证据链
            log.log("输出：\(full)")
        } catch {
            stepFailed(idx, 0, sendAt, detail: "生成出错")
            if var wf = messages[idx].workflow {
                wf.leader = .failed
                wf.summary = .failed
                if wf.worker == .active { wf.worker = .failed }
                if wf.tool == .active { wf.tool = .failed }
                wf.finishedAt = Date()
                messages[idx].workflow = wf
            }
            log.log("生成出错：\(error)")
        }
        running = false
    }

    // 无人值守跑分专用：300 字短文题（输出必触 256 token 上限），
    // 解码窗口拉满 4-5 秒，采样远稳于翻译/摘要短句；每轮前清历史防上下文累积拖慢
    static let benchPrompt = DemoPrompt(
        label: "跑分 · 短文",
        text: "写一篇300字左右的短文，介绍你理想中的一天，从早上起床写到晚上睡觉。",
        usesTools: false)

    // 无人值守跑分：短文连发 4 轮（首轮热身，后三轮取稳定数字），
    // 每轮「统计：解码 X tok/s」全量落盘 engine-shell.log；禁自动锁屏防跑分挂起
    private func runBench() async {
        UIApplication.shared.isIdleTimerDisabled = true
        log.log("BENCH-START（自动跑分）")
        let plan = Array(repeating: Self.benchPrompt, count: 4)
        var ok = 0
        for (i, p) in plan.enumerated() {
            history.removeAll()   // 每轮独立上下文，速度数字不随轮次漂移
            log.log("BENCH 轮次 \(i + 1)/\(plan.count)：\(p.label)")
            send(p.text, usesTools: p.usesTools)
            let deadline = Date().addingTimeInterval(120)
            while running && Date() < deadline {
                try? await Task.sleep(nanoseconds: 300_000_000)
            }
            if running {
                log.log("BENCH 轮次 \(i + 1) 超时（120s）")
            } else {
                ok += 1
            }
            try? await Task.sleep(nanoseconds: 1_000_000_000)
        }
        log.log("BENCH-DONE：完成 \(ok)/\(plan.count) 轮，各轮统计行见上")
        UIApplication.shared.isIdleTimerDisabled = false
    }

    // 场景回归套件：逐条独立会话跑断言，结果落盘 harness-results.jsonl，UI 收尾显示汇总
    private func runHarness() async {
        UIApplication.shared.isIdleTimerDisabled = true
        running = true
        let summary = await DemoHarness.run(engine: engine, log: log)
        messages.append(ChatMessage(role: .assistant, text: summary.displayText))
        successCount += summary.passed
        running = false
        UIApplication.shared.isIdleTimerDisabled = false
    }

    // MARK: - 私有工具

    private func stepDone(_ idx: Int, _ s: Int, _ sendAt: Date, detail: String? = nil) {
        animate {
            messages[idx].steps[s].state = .done
            if let detail { messages[idx].steps[s].detail = detail }
            messages[idx].steps[s].elapsed = Date().timeIntervalSince(sendAt)
        }
    }

    private func stepActive(_ idx: Int, _ s: Int, _ sendAt: Date) {
        animate {
            messages[idx].steps[s].state = .active
            messages[idx].steps[s].elapsed = Date().timeIntervalSince(sendAt)
        }
    }

    private func stepFailed(_ idx: Int, _ s: Int, _ sendAt: Date, detail: String? = nil) {
        animate {
            messages[idx].steps[s].state = .failed
            if let detail { messages[idx].steps[s].detail = detail }
            messages[idx].steps[s].elapsed = Date().timeIntervalSince(sendAt)
        }
    }

    // 苹果动效口径：默认临界阻尼弹簧（无回弹）；减少动效时直接落位
    private func animate(_ body: () -> Void) {
        if reduceMotion {
            body()
        } else {
            withAnimation(.spring(response: 0.35, dampingFraction: 1.0), body)
        }
    }

    private static func resultCard(_ e: ToolCallEvent) -> ToolResultCard {
        ToolResultCard(
            title: e.arguments["title"] ?? "—",
            start: e.arguments["start_time"] ?? "—",
            end: e.arguments["end_time"] ?? "—",
            location: e.arguments["location"] ?? "",
            ok: e.status == .executed,
            detail: e.status == .executed ? "已写入系统日历" : e.resultText)
    }

    // 模型定位：候选清单按评测成绩排序（1.7B SFT17 工具调用 90-97.5%），
    // Documents/Models（用户可换档）优先于 bundle 内嵌；
    // Documents/quant.txt 可钉选档位（真机跑分矩阵用，内容=文件名）
    private static func findModel() -> URL? {
        let docs = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
        // 演示模式优先用户选择的档位；自动模式（harness/bench）忽略，保证回归/跑分数据可比
        if !(harnessRequested || benchRequested),
           let chosen = UserDefaults.standard.string(forKey: "modelFile"),
           !chosen.isEmpty,
           let chosenURL = url(forModelFile: chosen) {
            return chosenURL
        }
        let pinURL = docs.appendingPathComponent("quant.txt")
        if FileManager.default.fileExists(atPath: pinURL.path),
           let pin = try? String(contentsOf: pinURL, encoding: .utf8) {
            let name = pin.trimmingCharacters(in: .whitespacesAndNewlines)
            // 钉档可命中 Documents/Models 或 App 内置（0.6B Q5 在 bundle 里）
            if !name.isEmpty, let pinned = url(forModelFile: name) { return pinned }
        }
        let names = [
            "qwen3-1.7b-sft17-Q4_K_M.gguf",
            "qwen3-1.7b-sft17-Q8_0.gguf",
            "qwen3-1.7b-sft17-Q5_K_M.gguf",
            "qwen3-0.6b-sft3b-Q5_K_M.gguf",
        ]
        let bases = [
            FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0],
            Bundle.main.bundleURL,
        ]
        for name in names {
            for base in bases {
                let url = base.appendingPathComponent("Models/\(name)")
                if FileManager.default.fileExists(atPath: url.path) { return url }
            }
        }
        return nil
    }

    private static func quantLabel(_ url: URL) -> String {
        // 文件名「…-Q4_K_M.gguf」→ 档位标签「Q4_K_M」
        url.deletingPathExtension().lastPathComponent.components(separatedBy: "-").last ?? "?"
    }

    // 硬件型号（如 iPhone18,2）——跑分矩阵按设备归档证据（#31）
    private static func deviceModelIdentifier() -> String {
        var info = utsname()
        uname(&info)
        return withUnsafePointer(to: &info.machine) {
            $0.withMemoryRebound(to: CChar.self, capacity: Int(_SYS_NAMELEN)) {
                String(cString: $0)
            }
        }
    }
}

// ==================== 视图 ====================

struct DemoChatView: View {
    @State private var model = DemoModel()
    @StateObject private var log = AppLog.shared
    @State private var input = ""
    @State private var sentCount = 0
    @FocusState private var focused: Bool
    @Environment(\.colorScheme) private var scheme
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var showModelLibraryFromLaunch = false
    @StateObject private var voice = VoiceService()
    @State private var showVoiceSheet = false
    @State private var showCalculator = false
    @State private var voiceDraft = ""
    @State private var voiceReplyPending = false
    @State private var showVoiceError = false
    @State private var voiceErrorText = ""
    @State private var photoItem: PhotosPickerItem?
    @State private var ocrBusy = false
    @State private var ocrError: String?
    @State private var ocrInput = false

    // 照片 OCR 会把 x² 压平成 x2：只给模型上下文加提示，聊天气泡仍显示原文
    static let ocrHint = "【图片识别】以下题目来自照片 OCR，公式已尽量还原成标准写法（如 x^2、1/3）；识别可能有误，请按数学常识核对后作答。\n"

    private var ready: Bool { if case .ready = model.phase { return true }; return false }
    private var canSend: Bool { ready && !model.running && !input.trimmingCharacters(in: .whitespaces).isEmpty }

    var body: some View {
        ZStack {
            background
            VStack(spacing: 0) {
                HStack(spacing: 8) {
                    statusPill
                    contextChip
                    rerunButton
                }
                .padding(.top, 10)
                chatList
                // 计算入口不需要模型，芯片行常驻；对话示例在模型未就绪时禁用
                chips
                if voice.isRecording { recordingBanner }
                inputBar
            }
        }
        .sensoryFeedback(.success, trigger: model.successCount)
        .sheet(isPresented: $model.showLog) { LogSheetView(log: log) }
        .sheet(isPresented: $model.showContextPicker) { ContextSheet(model: model) }
        .sheet(isPresented: $showVoiceSheet) { voiceConfirmSheet }
        .sheet(isPresented: $showCalculator) { NavigationStack { MathCalcView() } }
        .fullScreenCover(isPresented: $model.showOnboarding) { OnboardingView(model: model) }
        .fullScreenCover(isPresented: $showModelLibraryFromLaunch) {
            NavigationStack { ModelLibraryView(model: model) }
        }
        .alert("语音", isPresented: $showVoiceError) {
            Button("好", role: .cancel) {}
        } message: {
            Text(voiceErrorText)
        }
        .alert("图片识别", isPresented: Binding(
            get: { ocrError != nil },
            set: { if !$0 { ocrError = nil } }
        )) {
            Button("好", role: .cancel) {}
        } message: {
            Text(ocrError ?? "")
        }
        .onChange(of: input) { _, value in
            // 用户清空输入框视为放弃这次图片识别，避免下一条普通问题带上 OCR 提示
            if value.isEmpty { ocrInput = false }
        }
        .onChange(of: voice.notice) { _, notice in
            guard let notice else { return }
            voiceErrorText = notice
            showVoiceError = true
            voice.clearNotice()
        }
        .onChange(of: model.running) { _, running in
            guard !running, voiceReplyPending else { return }
            voiceReplyPending = false
            guard let last = model.messages.last, last.role == .assistant else { return }
            let text = last.text.trimmingCharacters(in: .whitespacesAndNewlines)
            if !text.isEmpty { voice.speak(text) }
        }
        .task {
            model.reduceMotion = reduceMotion
            // 演示/截图专用入口：不改变正常启动路径
            if ProcessInfo.processInfo.arguments.contains("-modelLibrary") {
                showModelLibraryFromLaunch = true
            }
            await model.loadModel()
        }
    }

    // MARK: 背景（浅蓝灰渐变，模拟玻璃下的环境光）

    private var background: some View {
        LinearGradient(
            colors: scheme == .light
                ? [Color(red: 0.88, green: 0.90, blue: 0.96), Color(red: 0.96, green: 0.97, blue: 0.99)]
                : [Color(red: 0.05, green: 0.05, blue: 0.08), Color(red: 0.11, green: 0.11, blue: 0.15)],
            startPoint: .top, endPoint: .bottom)
        .ignoresSafeArea()
    }

    // MARK: 状态徽章（长按 2 秒开日志——证据链保留但不出现在演示画面）

    private var statusPill: some View {
        HStack(spacing: 7) {
            Circle()
                .fill(dotColor)
                .frame(width: 8, height: 8)
                .shadow(color: dotColor.opacity(0.7), radius: 4)
            Text(statusText)
                .font(.footnote.weight(.semibold))
                .foregroundStyle(.primary)
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 7)
        .background(.ultraThinMaterial, in: Capsule())
        .overlay(Capsule().strokeBorder(.white.opacity(scheme == .dark ? 0.14 : 0.65), lineWidth: 1))
        .shadow(color: .black.opacity(0.06), radius: 10, y: 4)
        .onLongPressGesture(minimumDuration: 2) { model.showLog = true }
    }

    // 上下文档位入口：当前档位直接显示在顶部，点开选择并查看代价
    private var contextChip: some View {
        Button {
            model.showContextPicker = true
        } label: {
            HStack(spacing: 5) {
                Text("\(model.modelShortLabel) · \(model.contextTokens / 1024)K")
                    .font(.footnote.weight(.semibold))
                Image(systemName: "gearshape.fill")
                    .font(.system(size: 10, weight: .semibold))
            }
            .foregroundStyle(.secondary)
            .padding(.horizontal, 12)
            .padding(.vertical, 7)
            .background(.ultraThinMaterial, in: Capsule())
            .overlay(Capsule().strokeBorder(.white.opacity(scheme == .dark ? 0.14 : 0.65), lineWidth: 1))
            .shadow(color: .black.opacity(0.06), radius: 10, y: 4)
        }
        .buttonStyle(.plain)
        .disabled(!ready || model.running)
    }

    // 主页直达重跑：重新执行 4 轮标准负载并给出新分数/推荐
    private var rerunButton: some View {
        Button {
            model.startBenchmark()
        } label: {
            HStack(spacing: 4) {
                Image(systemName: "arrow.clockwise")
                    .font(.caption.weight(.semibold))
                Text("重跑")
                    .font(.footnote.weight(.semibold))
            }
            .foregroundStyle(.secondary)
            .padding(.horizontal, 12)
            .padding(.vertical, 7)
            .background(.ultraThinMaterial, in: Capsule())
            .overlay(Capsule().strokeBorder(.white.opacity(scheme == .dark ? 0.14 : 0.65), lineWidth: 1))
            .shadow(color: .black.opacity(0.06), radius: 10, y: 4)
        }
        .buttonStyle(.plain)
        .disabled(!ready || model.running || model.onboardingRunning)
        .accessibilityLabel("重新跑分")
    }

    private var dotColor: Color {
        switch model.phase {
        case .loading: return .orange
        case .ready: return Color(red: 0.19, green: 0.82, blue: 0.35)
        case .failed: return .red
        }
    }

    private var statusText: String {
        switch model.phase {
        case .loading: return "本地模型加载中…"
        case .ready: return model.multiModelActive ? "离线 · 双模型协作" : "离线 · 数据不出设备"
        case .failed: return "模型加载失败 · 长按查看日志"
        }
    }

    // MARK: 对话列表

    private var chatList: some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(spacing: 14) {
                    ForEach(model.messages) { msg in
                        MessageRow(
                            message: msg, running: model.running,
                            speaking: voice.isSpeaking,
                            onSpeak: { text in
                                if voice.isSpeaking { voice.stopSpeaking() }
                                else { voice.speak(text) }
                            })
                            .id(msg.id)
                    }
                }
                .padding(.horizontal, 16)
                .padding(.vertical, 14)
            }
            .scrollIndicators(.hidden)
            .onChange(of: model.messages.count) {
                scrollToBottom(proxy)
            }
            .onChange(of: model.messages.last?.text) {
                scrollToBottom(proxy)   // 流式打字时持续跟底
            }
        }
        .overlay {
            if model.messages.isEmpty, ready {
                VStack(spacing: 8) {
                    Image(systemName: "cpu")
                        .font(.system(size: 34, weight: .light))
                        .foregroundStyle(.secondary)
                    Text("Agent 实验室")
                        .font(.title3.weight(.semibold))
                    Text("本地推理 · 工具调用 · 数据不出设备")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    Text("试试下面的示例，或直接提问")
                        .font(.caption2)
                        .foregroundStyle(.tertiary)
                }
                .allowsHitTesting(false)
            }
        }
    }

    private func scrollToBottom(_ proxy: ScrollViewProxy) {
        guard let last = model.messages.last else { return }
        withAnimation(.spring(response: 0.4, dampingFraction: 1.0)) {
            proxy.scrollTo(last.id, anchor: .bottom)
        }
    }

    // MARK: 快捷短语

    private var chips: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 8) {
                // CAS 计算入口：不需要模型，点开即算（docs/plans/数学CAS工具接入.md）
                Button {
                    showCalculator = true
                } label: {
                    Label("计算", systemImage: "function")
                        .font(.caption)
                        .padding(.horizontal, 12)
                        .padding(.vertical, 7)
                        .background(.ultraThinMaterial, in: Capsule())
                        .overlay(Capsule().strokeBorder(.white.opacity(scheme == .dark ? 0.14 : 0.55), lineWidth: 1))
                }
                .buttonStyle(.plain)
                ForEach(DemoModel.demoPrompts, id: \.text) { p in
                    Button {
                        send(p.text, usesTools: p.usesTools)
                    } label: {
                        Text(p.label)
                            .font(.caption)
                            .padding(.horizontal, 12)
                            .padding(.vertical, 7)
                            .background(.ultraThinMaterial, in: Capsule())
                            .overlay(Capsule().strokeBorder(.white.opacity(scheme == .dark ? 0.14 : 0.55), lineWidth: 1))
                    }
                    .buttonStyle(.plain)
                    .disabled(model.running || !ready)
                }
            }
            .padding(.horizontal, 16)
            .padding(.bottom, 8)
        }
    }

    // MARK: 输入栏

    private var recordingBanner: some View {
        HStack(spacing: 8) {
            Image(systemName: "waveform")
                .symbolEffect(.variableColor.iterative, isActive: true)
            Text("正在听…点麦克风结束")
            Spacer(minLength: 0)
        }
        .font(.footnote.weight(.medium))
        .foregroundStyle(.red)
        .padding(.horizontal, 16)
        .padding(.vertical, 7)
    }

    private var inputBar: some View {
        HStack(spacing: 10) {
            // 数学题常以照片形式出现：本机 Vision 识别成文字，填入输入框供用户改错后再发
            PhotosPicker(selection: $photoItem, matching: .images, photoLibrary: .shared()) {
                Group {
                    if ocrBusy {
                        ProgressView()
                    } else {
                        Image(systemName: "photo")
                            .font(.system(size: 13, weight: .semibold))
                            .foregroundStyle(Color(red: 0.04, green: 0.52, blue: 1.0))
                    }
                }
                .frame(width: 30, height: 30)
                .background(Color(red: 0.90, green: 0.94, blue: 1.0), in: Circle())
            }
            .disabled(!ready || model.running || ocrBusy)
            .accessibilityLabel("图片识别")
            .onChange(of: photoItem) { _, item in
                guard let item else { return }
                Task { await importPhoto(item) }
            }

            Button {
                handleMicTap()
            } label: {
                Image(systemName: voice.isRecording ? "stop.fill" : "mic.fill")
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundStyle(voice.isRecording ? .white : Color(red: 0.04, green: 0.52, blue: 1.0))
                    .frame(width: 30, height: 30)
                    .background(
                        voice.isRecording ? Color.red : Color(red: 0.90, green: 0.94, blue: 1.0),
                        in: Circle())
            }
            .disabled(!ready || model.running)
            .accessibilityLabel(voice.isRecording ? "停止录音" : "语音输入")

            TextField("问点什么…", text: $input, axis: .vertical)
                .lineLimit(1...4)
                .focused($focused)
                .submitLabel(.send)
                .onSubmit { send(input) }
                .disabled(!ready)
            Button {
                send(input)
            } label: {
                Image(systemName: "arrow.up")
                    .font(.system(size: 13, weight: .bold))
                    .foregroundStyle(.white)
                    .frame(width: 30, height: 30)
                    .background(canSend ? Color(red: 0.04, green: 0.52, blue: 1.0) : Color(.systemGray4), in: Circle())
            }
            .disabled(!canSend)
            .sensoryFeedback(.impact(weight: .light), trigger: sentCount)
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 9)
        .background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: 22, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 22, style: .continuous)
            .strokeBorder(.white.opacity(scheme == .dark ? 0.14 : 0.65), lineWidth: 1))
        .shadow(color: .black.opacity(0.08), radius: 14, y: 6)
        .padding(.horizontal, 16)
        .padding(.bottom, 14)
    }

    // 手动输入按意图路由（chips 显式传 true/false）；默认不挂工具，避免翻译/闲聊被误判成加日历
    private func send(_ text: String, usesTools: Bool? = nil) {
        let hint = ocrInput ? Self.ocrHint : nil
        ocrInput = false
        model.send(text, usesTools: usesTools ?? DemoModel.looksLikeCalendarRequest(text), contextHint: hint)
        input = ""
        sentCount += 1
        focused = false
    }

    // 相册选图 → 本机 OCR → 填入输入框（保留人工改错环节，符合「AI 出错怎么办」）
    // Vision 负责中文题干/普通文字，Texo 负责数学排版；两路都本机跑，图片不出设备
    private func importPhoto(_ item: PhotosPickerItem) async {
        ocrBusy = true
        defer {
            ocrBusy = false
            photoItem = nil
        }
        do {
            guard let data = try await item.loadTransferable(type: Data.self),
                  let image = UIImage(data: data) else { throw PhotoOCR.Failure.decode }
            let text = (try? await PhotoOCR.recognize(image)) ?? ""
            let formula = await Self.recognizeFormula(image)
            let merged = Self.mergePhotoResults(text: text, formula: formula)
            guard !merged.isEmpty else { throw PhotoOCR.Failure.noText }
            input = merged
            ocrInput = true
            focused = true
            log.log("图片识别完成：\(merged.prefix(220))")
        } catch {
            ocrError = (error as? LocalizedError)?.errorDescription ?? "识别失败：\(error)"
            log.log("图片识别失败：\(error)")
        }
    }

    // Texo 首次要加载 77MB ONNX，必须离开主线程；失败返回空串，让 Vision 结果兜底
    private static func recognizeFormula(_ image: UIImage) async -> String {
        await withCheckedContinuation { continuation in
            DispatchQueue.global(qos: .userInitiated).async {
                let result = (try? TexoOCR.problem(from: image))?.problem ?? ""
                continuation.resume(returning: result)
            }
        }
    }

    // 两路结果合并：有公式就把结构化题意接在文字题干后面，纯文字照片不受影响
    private static func mergePhotoResults(text: String, formula: String) -> String {
        let trimmedText = text.trimmingCharacters(in: .whitespacesAndNewlines)
        let trimmedFormula = formula.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmedFormula.isEmpty else { return trimmedText }
        guard !trimmedText.isEmpty else { return trimmedFormula }
        guard looksMathematical(trimmedFormula) else { return trimmedText }
        if trimmedText.contains(trimmedFormula) { return trimmedText }
        return trimmedText + "\n" + trimmedFormula
    }

    private static func looksMathematical(_ latex: String) -> Bool {
        guard latex.count <= 200 else { return false }
        let strong = ["\\frac", "\\sqrt", "\\int", "\\sum", "\\lim", "\\binom",
                      "\\sin", "\\cos", "\\tan", "\\log", "="]
        if strong.contains(where: { latex.contains($0) }) { return true }
        // 裸上下标只在有数字/常见变量时才算公式，防止纯文字照片被 Texo 噪声污染
        guard latex.contains("^") || latex.contains("_") else { return false }
        return latex.contains { $0.isNumber } || latex.contains("x")
            || latex.contains("y") || latex.contains("z")
    }

    private func handleMicTap() {
        if voice.isRecording {
            voice.stopRecording()
            return
        }
        focused = false
        voice.startRecording { text in
            let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !trimmed.isEmpty else {
                voiceErrorText = "没有识别到语音，请靠近麦克风再说一次"
                showVoiceError = true
                return
            }
            voiceDraft = trimmed
            showVoiceSheet = true
        }
    }

    private func sendVoiceDraft() {
        let text = voiceDraft.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty, !model.running else { return }
        showVoiceSheet = false
        voiceReplyPending = true
        send(text, usesTools: DemoModel.looksLikeCalendarRequest(text))
    }

    private var voiceConfirmSheet: some View {
        NavigationStack {
            VStack(alignment: .leading, spacing: 12) {
                Text("识别结果可修改；发送后会走现有 Agent 与工具链。")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
                TextEditor(text: $voiceDraft)
                    .font(.body)
                    .frame(minHeight: 180)
                    .padding(8)
                    .background(Color(.secondarySystemBackground), in: RoundedRectangle(cornerRadius: 12))
                Spacer(minLength: 0)
                Button {
                    sendVoiceDraft()
                } label: {
                    Text("发送给 Agent")
                        .font(.body.weight(.semibold))
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(.borderedProminent)
                .disabled(voiceDraft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            }
            .padding(16)
            .navigationTitle("语音输入")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("取消") { showVoiceSheet = false }
                }
            }
        }
        .presentationDetents([.medium, .large])
    }
}

// ==================== 运行设置（模型档位 + 上下文档位） ====================

struct ContextSheet: View {
    @Bindable var model: DemoModel
    @Environment(\.dismiss) private var dismiss
    @State private var pendingLarge: DemoModel.ContextOption?

    var body: some View {
        NavigationStack {
            List {
                Section {
                    ForEach(DemoModel.availableModels) { opt in
                        Button {
                            selectModel(opt)
                        } label: {
                            modelRow(opt)
                        }
                        .buttonStyle(.plain)
                        .disabled(model.running || model.multiModelActive)
                    }
                } header: {
                    Text("模型档位")
                } footer: {
                    Text(model.multiModelActive
                         ? "双模型模式下模型档位锁定；先关闭「多模型协作」再切换。"
                         : "速度来自 iPhone 18 Pro Max 实测；峰值按当前 \(model.contextTokens / 1024)K 上下文估算。切档后模型重新加载，对话历史保留。")
                }

                multiModelSection

                Section {
                    ForEach(SpeedTier.allCases, id: \.rawValue) { tier in
                        Button {
                            model.setSpeedTier(tier)
                        } label: {
                            speedRow(tier)
                        }
                        .buttonStyle(.plain)
                        .disabled(model.running)
                    }
                } header: {
                    Text("速度档位")
                } footer: {
                    Text("实测解码速度四档几乎无差（内存带宽瓶颈），主要影响首 token 速度与功耗；下一次生成生效，无需重载。")
                }

                Section {
                    ForEach(DemoModel.contextOptions) { opt in
                        Button {
                            // 16K/32K 在 8GB 机型上可能被系统终止，二次确认
                            if opt.tokens >= 16384 {
                                pendingLarge = opt
                            } else {
                                select(opt)
                            }
                        } label: {
                            row(opt)
                        }
                        .buttonStyle(.plain)
                        .disabled(model.running)
                    }
                } header: {
                    Text("上下文窗口")
                } footer: {
                    Text("上下文 = 输入 + 输出。切档后模型会重新加载（约 2 秒），对话历史保留；峰值内存见上方模型档位估算。")
                }

                Section("代价") {
                    Label("每 1K tokens 约占 110 MB 内存（KV 缓存）", systemImage: "memorychip")
                    Label("上下文越长，首 token 越慢；解码速度基本不变", systemImage: "speedometer")
                    Label("8GB 机型建议不超过 8K，16K/32K 可能被系统终止", systemImage: "exclamationmark.triangle")
                }
                .font(.footnote)

                Section("设备") {
                    HStack {
                        Text("设备分")
                        Spacer()
                        Text(model.lastScore > 0
                             ? "\(model.lastScore) · \(BenchmarkTier.of(model.lastScore).rawValue)"
                             : "未跑分")
                            .foregroundStyle(.secondary)
                    }
                    Text("分档：80–100 强 · 60–79 稳 · 40–59 够用 · 0–39 轻量")
                        .font(.caption2)
                        .foregroundStyle(.tertiary)
                    Button("重新跑分") {
                        dismiss()
                        Task {
                            try? await Task.sleep(nanoseconds: 400_000_000)
                            model.startBenchmark()
                        }
                    }
                    .disabled(model.running)
                }

                Section("更多") {
                    NavigationLink {
                        MathCalcView()
                    } label: {
                        Label("数学计算", systemImage: "function")
                    }
                    NavigationLink {
                        ModelLibraryView(model: model)
                    } label: {
                        Label("模型库", systemImage: "square.stack.3d.up")
                    }
                    NavigationLink {
                        AboutView(model: model)
                    } label: {
                        Label("关于与隐私", systemImage: "info.circle")
                    }
                }
            }
            .navigationTitle("设置")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("完成") { dismiss() }
                }
            }
            .alert("内存风险", isPresented: Binding(
                get: { pendingLarge != nil },
                set: { if !$0 { pendingLarge = nil } })) {
                Button("取消", role: .cancel) { pendingLarge = nil }
                Button("仍然切换", role: .destructive) {
                    if let opt = pendingLarge { select(opt) }
                }
            } message: {
                Text("\(pendingLarge?.title ?? "") 上下文可能因内存不足被系统终止，首次加载也更慢。")
            }
        }
        .presentationDetents([.medium, .large])
    }

    private var ready: Bool {
        if case .ready = model.phase { return true }
        return false
    }

    private var multiModelSection: some View {
        Section {
            Toggle(isOn: Binding(
                get: { model.multiModelEnabled },
                set: { on in Task { await model.setMultiModel(on) } })) {
                VStack(alignment: .leading, spacing: 3) {
                    Text("多模型协作（实验）")
                        .font(.body.weight(.medium))
                    Text("1.7B 领队 + 0.6B 工人，都在本地")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
            .disabled(!ready || model.running || model.multiModelBusy
                      || (DemoModel.multiModelPair() == nil && !model.multiModelEnabled))

            if model.multiModelBusy {
                HStack(spacing: 8) {
                    ProgressView()
                    Text("切换中，模型重新加载…")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }

            if let pair = DemoModel.multiModelPair() {
                VStack(alignment: .leading, spacing: 5) {
                    Text("领队：\(pair.leader.lastPathComponent)")
                    Text("工人：\(pair.worker.lastPathComponent)")
                    Text("峰值约 \(String(format: "%.1f", DemoModel.multiModelPeakGB(contextTokens: model.contextTokens))) GB（领队 \(model.contextTokens / 1024)K + 工人 2K）")
                        .monospacedDigit()
                        .foregroundStyle(.tertiary)
                }
                .font(.caption)
            } else {
                Label("缺少 SFT20 领队或 SFT20c 工人模型，请先在模型库导入", systemImage: "exclamationmark.triangle")
                    .font(.caption)
                    .foregroundStyle(.orange)
            }

            if model.multiModelEnabled {
                Toggle(isOn: Binding(
                    get: { model.workflowVisualizationEnabled },
                    set: { model.setWorkflowVisualization($0) })) {
                    VStack(alignment: .leading, spacing: 3) {
                        Text("工作流可视化")
                            .font(.body.weight(.medium))
                        Text("显示领队 → 工人 → 工具的执行图")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }
                .disabled(model.running)
            }
        } header: {
            Text("多模型协作（实验）")
        } footer: {
            Text("开启后领队负责派单、工人负责日期换算与工具调用；写日历/提醒仍每次弹窗确认。翻译/摘要执行器暂未接入。关闭即恢复当前单模型，历史保留。")
        }
    }

    private func select(_ opt: DemoModel.ContextOption) {
        pendingLarge = nil
        dismiss()
        Task { await model.switchContext(to: opt.tokens) }
    }

    private func selectModel(_ opt: DemoModel.ModelOption) {
        dismiss()
        Task { await model.switchModel(to: opt) }
    }

    private func modelRow(_ opt: DemoModel.ModelOption) -> some View {
        HStack(spacing: 12) {
            VStack(alignment: .leading, spacing: 3) {
                Text(opt.title)
                    .font(.body.weight(.medium))
                    .foregroundStyle(.primary)
                Text(opt.detail)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                Text("\(opt.speed) · 权重 \(String(format: "%.2f", opt.weightGB)) GB · 峰值约 \(String(format: "%.1f", peakGB(opt))) GB（\(model.contextTokens / 1024)K）")
                    .font(.caption2.monospacedDigit())
                    .foregroundStyle(.tertiary)
            }
            Spacer()
            if model.currentModelFile == opt.file {
                Image(systemName: "checkmark.circle.fill")
                    .foregroundStyle(Color(red: 0.04, green: 0.52, blue: 1.0))
            }
        }
        .contentShape(Rectangle())
    }

    // 峰值 ≈ 权重 + KV（112 KB/token）+ Metal/运行时缓冲约 0.2 GB
    private func peakGB(_ opt: DemoModel.ModelOption) -> Double {
        opt.weightGB + Double(model.contextTokens) / 1024.0 * 0.11 + 0.2
    }

    private func speedRow(_ tier: SpeedTier) -> some View {
        HStack(spacing: 12) {
            VStack(alignment: .leading, spacing: 3) {
                Text(DemoModel.speedTitle(tier))
                    .font(.body.weight(.medium))
                    .foregroundStyle(.primary)
                Text(speedDetail(tier))
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            Spacer()
            if model.speedTier == tier {
                Image(systemName: "checkmark.circle.fill")
                    .foregroundStyle(Color(red: 0.04, green: 0.52, blue: 1.0))
            }
        }
        .contentShape(Rectangle())
    }

    private func speedDetail(_ tier: SpeedTier) -> String {
        switch tier {
        case .powerSaver: return "2 线程 · 最省电，首 token 最慢"
        case .balanced: return "4 线程 · 默认推荐"
        case .performance: return "8 线程 · 首 token 更快，功耗更高"
        case .turbo: return "自动线程 · 首 token 最快，功耗最高"
        }
    }

    private func row(_ opt: DemoModel.ContextOption) -> some View {
        HStack(spacing: 12) {
            VStack(alignment: .leading, spacing: 3) {
                Text("\(opt.title) 上下文")
                    .font(.body.weight(.medium))
                    .foregroundStyle(.primary)
                Text(opt.detail)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                Text(opt.cost)
                    .font(.caption2.monospacedDigit())
                    .foregroundStyle(.tertiary)
            }
            Spacer()
            if model.contextTokens == opt.tokens {
                Image(systemName: "checkmark.circle.fill")
                    .foregroundStyle(Color(red: 0.04, green: 0.52, blue: 1.0))
            }
        }
        .contentShape(Rectangle())
    }
}

// ==================== 消息行 ====================

struct MessageRow: View {
    let message: ChatMessage
    let running: Bool
    var speaking: Bool = false
    var onSpeak: ((String) -> Void)? = nil

    var body: some View {
        switch message.role {
        case .user: userBubble
        case .assistant: assistantCard
        }
    }

    // 用户气泡：系统蓝 + 右下小尾巴（iMessage 同款形状语义）
    private var userBubble: some View {
        HStack {
            Spacer(minLength: 56)
            Text(message.text)
                .font(.subheadline)
                .foregroundStyle(.white)
                .padding(.horizontal, 14)
                .padding(.vertical, 10)
                .background(
                    Color(red: 0.04, green: 0.52, blue: 1.0),
                    in: UnevenRoundedRectangle(
                        topLeadingRadius: 18, bottomLeadingRadius: 18,
                        bottomTrailingRadius: 5, topTrailingRadius: 18, style: .continuous))
                .shadow(color: .blue.opacity(0.25), radius: 10, y: 4)
        }
    }

    // 助手卡片：玻璃材质 + 流式文本 + 过程卡 + 结果卡 + 真实性能行
    private var assistantCard: some View {
        VStack(alignment: .leading, spacing: 12) {
            if message.text.isEmpty && running {
                ShimmerBar()
            } else {
                Text(message.text)
                    .font(.subheadline)
                    .foregroundStyle(.primary)
                    .lineSpacing(3)
                    .textSelection(.enabled)
            }
            if let workflow = message.workflow {
                WorkflowCard(trace: workflow)
            } else if !message.steps.isEmpty {
                ProcessCard(steps: message.steps)
            }
            if message.workflow == nil, let dispatch = message.dispatch {
                DispatchCardView(card: dispatch)
            }
            if let result = message.result {
                ResultCardView(card: result)
            }
            if let stats = message.statsLine {
                Text(stats)
                    .font(.caption2.monospacedDigit())
                    .foregroundStyle(.tertiary)
            }
            if let onSpeak, !message.text.isEmpty {
                HStack {
                    Spacer()
                    Button {
                        onSpeak(message.text)
                    } label: {
                        Image(systemName: speaking ? "speaker.slash.fill" : "speaker.wave.2")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                            .padding(6)
                            .background(.ultraThinMaterial, in: Circle())
                    }
                    .buttonStyle(.plain)
                    .accessibilityLabel(speaking ? "停止播报" : "播报回答")
                }
            }
        }
        .padding(14)
        .frame(maxWidth: .infinity, alignment: .leading)
        .glass()
    }
}

// ==================== 过程卡 ====================

struct ProcessCard: View {
    let steps: [ProcessStep]
    @Environment(\.colorScheme) private var scheme

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            Text("思考过程")
                .font(.caption.weight(.semibold))
                .foregroundStyle(.secondary)
                .padding(.bottom, 5)
            ForEach(steps) { step in
                StepRow(step: step)
            }
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        // 内嵌卡不用第二层半透明材质（苹果规则：半透明面不能叠半透明面），用弱底色区分层次
        .background(
            scheme == .dark ? Color.white.opacity(0.07) : Color.black.opacity(0.045),
            in: RoundedRectangle(cornerRadius: 14, style: .continuous))
    }
}

struct StepRow: View {
    let step: ProcessStep

    var body: some View {
        HStack(spacing: 10) {
            ZStack {
                Circle().fill(badgeColor).frame(width: 22, height: 22)
                switch step.state {
                case .done:
                    Image(systemName: "checkmark")
                        .font(.system(size: 10, weight: .bold))
                        .foregroundStyle(.white)
                case .active:
                    ProgressView()
                        .controlSize(.mini)
                        .tint(.white)
                case .failed:
                    Image(systemName: "xmark")
                        .font(.system(size: 10, weight: .bold))
                        .foregroundStyle(.white)
                case .pending:
                    Circle()
                        .strokeBorder(Color.secondary.opacity(0.45), lineWidth: 1.5)
                        .frame(width: 7, height: 7)
                }
            }
            VStack(alignment: .leading, spacing: 1) {
                Text(step.title)
                    .font(.footnote.weight(step.state == .pending ? .regular : .semibold))
                    .foregroundStyle(step.state == .pending ? .secondary : .primary)
                if let detail = step.detail {
                    Text(detail)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                }
            }
            Spacer(minLength: 8)
            if let elapsed = step.elapsed {
                Text(String(format: "%.1fs", elapsed))
                    .font(.caption.monospacedDigit())
                    .foregroundStyle(.tertiary)
            }
        }
        .padding(.vertical, 5)
    }

    private var badgeColor: Color {
        switch step.state {
        case .done: return Color(red: 0.19, green: 0.82, blue: 0.35)    // 系统绿
        case .active: return Color(red: 0.04, green: 0.52, blue: 1.0)   // 系统蓝
        case .failed: return Color(red: 1.0, green: 0.23, blue: 0.19)   // 系统红
        case .pending: return Color(.systemGray5)
        }
    }
}

// ==================== 结果卡 ====================

struct ResultCardView: View {
    let card: ToolResultCard
    @Environment(\.colorScheme) private var scheme

    var body: some View {
        VStack(alignment: .leading, spacing: 5) {
            row("事件", card.title)
            row("时间", "\(card.start) → \(card.end)")
            if !card.location.isEmpty {
                row("地点", card.location)
            }
            HStack(spacing: 6) {
                Image(systemName: card.ok ? "checkmark.circle.fill" : "xmark.circle.fill")
                    .foregroundStyle(card.ok ? Color(red: 0.19, green: 0.82, blue: 0.35) : .red)
                Text(card.detail)
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.primary)
            }
            .padding(.top, 3)
        }
        .font(.footnote)
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(
            scheme == .dark ? Color.white.opacity(0.07) : Color.black.opacity(0.045),
            in: RoundedRectangle(cornerRadius: 14, style: .continuous))
    }

    private func row(_ label: String, _ value: String) -> some View {
        HStack(alignment: .firstTextBaseline) {
            Text(label)
                .foregroundStyle(.secondary)
            Text(value)
                .foregroundStyle(.primary)
        }
    }
}

// 双模型派单卡：工人名 / 子任务 / 真实执行结果
struct DispatchCardView: View {
    let card: DispatchCard
    @Environment(\.colorScheme) private var scheme

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 6) {
                Image(systemName: "arrow.triangle.branch")
                    .foregroundStyle(Color(red: 0.04, green: 0.52, blue: 1.0))
                Text("多模型派单")
                    .font(.caption.weight(.semibold))
                Spacer()
                Text(card.worker)
                    .font(.caption2.monospaced())
                    .foregroundStyle(.secondary)
            }
            if !card.task.isEmpty {
                Text(card.task)
                    .font(.footnote)
                    .foregroundStyle(.primary)
                    .lineLimit(3)
            }
            HStack(alignment: .top, spacing: 6) {
                Image(systemName: card.ok ? "checkmark.circle.fill" : "xmark.circle.fill")
                    .foregroundStyle(card.ok ? Color(red: 0.19, green: 0.82, blue: 0.35) : .red)
                Text(card.detail)
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.primary)
                    .lineLimit(4)
            }
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(
            scheme == .dark ? Color.white.opacity(0.07) : Color.black.opacity(0.045),
            in: RoundedRectangle(cornerRadius: 14, style: .continuous))
    }
}

// ==================== 工作流可视化 ====================

// 一张卡里画完整执行图：领队 → 工人 → 工具 → 汇总。
// 状态由 DispatchStage 真实事件驱动，不预演、不补假动画
struct WorkflowCard: View {
    let trace: WorkflowTrace
    @Environment(\.colorScheme) private var scheme

    private var failed: Bool {
        [trace.leader, trace.worker, trace.tool, trace.summary].contains(.failed)
    }

    private var running: Bool { trace.finishedAt == nil }

    private var workerTitle: String {
        switch trace.workerName {
        case "calendar_worker": return "日历工人"
        case "reminder_worker": return "提醒工人"
        case "translate_worker": return "翻译工人"
        case "summary_worker": return "摘要工人"
        default:
            return trace.workerName?.replacingOccurrences(of: "_worker", with: "") ?? "工人"
        }
    }

    private var toolTitle: String {
        switch trace.toolName {
        case "add_calendar_event": return "日历"
        case "set_reminder": return "提醒事项"
        case "translate_text": return "翻译"
        case "summarize_text": return "摘要"
        default: return trace.toolName ?? "工具"
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 11) {
            HStack(spacing: 7) {
                Image(systemName: "arrow.triangle.branch")
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundStyle(Color(red: 0.04, green: 0.52, blue: 1.0))
                Text("Agent 工作流")
                    .font(.caption.weight(.semibold))
                Spacer()
                statusPill
            }

            if trace.usedDispatch {
                HStack(alignment: .top, spacing: 0) {
                    WorkflowNodeView(icon: "brain.head.profile", title: "领队", subtitle: "1.7B", state: trace.leader)
                    WorkflowConnector(state: trace.worker)
                    WorkflowNodeView(icon: "person.2.fill", title: workerTitle, subtitle: "0.6B", state: trace.worker)
                    WorkflowConnector(state: trace.tool)
                    WorkflowNodeView(icon: "wrench.and.screwdriver.fill", title: toolTitle, subtitle: "工具", state: trace.tool)
                    WorkflowConnector(state: trace.summary)
                    WorkflowNodeView(icon: "text.bubble.fill", title: "汇总", subtitle: "领队", state: trace.summary)
                }
                .frame(maxWidth: .infinity)
                .padding(.top, 2)

                if let task = trace.task, !task.isEmpty {
                    detailRow(label: "派单", text: task, tint: nil)
                }
                if let result = trace.resultDetail, !result.isEmpty {
                    let tint: Color? = trace.tool == .done
                        ? Color(red: 0.12, green: 0.62, blue: 0.27)
                        : (trace.tool == .failed ? .red : nil)
                    detailRow(label: "结果", text: result, tint: tint)
                }
            } else {
                HStack(alignment: .top, spacing: 0) {
                    WorkflowNodeView(icon: "brain.head.profile", title: "领队", subtitle: "1.7B", state: trace.leader)
                    WorkflowConnector(state: trace.summary)
                    WorkflowNodeView(icon: "text.bubble.fill", title: "回复", subtitle: "直接回答", state: trace.summary)
                }
                .frame(maxWidth: .infinity)
                .padding(.top, 2)
            }

            HStack(spacing: 6) {
                if let finishedAt = trace.finishedAt {
                    Text(String(format: "总耗时 %.1f s", finishedAt.timeIntervalSince(trace.startedAt)))
                } else {
                    Text("正在运行…")
                }
                Spacer()
                Image(systemName: "lock.fill")
                    .font(.system(size: 7.5))
                Text("本地 · 离线 · 双模型")
            }
            .font(.system(size: 9.5, weight: .medium))
            .foregroundStyle(.tertiary)
        }
        .padding(13)
        .background(
            scheme == .dark ? Color.white.opacity(0.06) : Color.white.opacity(0.72),
            in: RoundedRectangle(cornerRadius: 16, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 16, style: .continuous)
                .strokeBorder(scheme == .dark ? Color.white.opacity(0.10) : Color.white.opacity(0.92), lineWidth: 1))
        .shadow(color: .black.opacity(scheme == .dark ? 0.18 : 0.05), radius: 12, y: 5)
    }

    private var statusPill: some View {
        let tint: Color = failed ? .red : (running ? Color(red: 0.04, green: 0.52, blue: 1.0)
                                                  : Color(red: 0.12, green: 0.62, blue: 0.27))
        return HStack(spacing: 4) {
            Circle().fill(tint).frame(width: 5, height: 5)
            Text(failed ? "失败" : (running ? "运行中" : "已完成"))
        }
        .font(.system(size: 9.5, weight: .semibold))
        .foregroundStyle(tint)
        .padding(.horizontal, 7)
        .padding(.vertical, 3)
        .background(tint.opacity(0.12), in: Capsule())
    }

    private func detailRow(label: String, text: String, tint: Color?) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 7) {
            Text(label)
                .font(.system(size: 9.5, weight: .semibold))
                .foregroundStyle(.secondary)
                .frame(width: 24, alignment: .leading)
            Text(text)
                .font(.system(size: 10.5))
                .foregroundStyle(tint ?? .primary)
                .lineLimit(2)
                .frame(maxWidth: .infinity, alignment: .leading)
        }
        .padding(.horizontal, 9)
        .padding(.vertical, 7)
        .background(Color.primary.opacity(0.035), in: RoundedRectangle(cornerRadius: 9, style: .continuous))
    }
}

private struct WorkflowNodeView: View {
    let icon: String
    let title: String
    let subtitle: String
    let state: WorkflowNodeState
    @Environment(\.colorScheme) private var scheme
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var pulse = false

    private var tint: Color {
        switch state {
        case .pending: return Color(.systemGray3)
        case .active: return Color(red: 0.04, green: 0.52, blue: 1.0)
        case .done: return Color(red: 0.12, green: 0.62, blue: 0.27)
        case .failed: return .red
        }
    }

    var body: some View {
        VStack(spacing: 4) {
            ZStack {
                Circle()
                    .fill(tint.opacity(state == .pending ? 0.12 : 0.16))
                    .frame(width: 38, height: 38)
                if state == .active && !reduceMotion {
                    Circle()
                        .stroke(tint.opacity(0.45), lineWidth: 1.5)
                        .frame(width: 39, height: 39)
                        .scaleEffect(pulse ? 1.24 : 0.92)
                        .opacity(pulse ? 0 : 0.95)
                        .animation(.easeOut(duration: 1.15).repeatForever(autoreverses: false), value: pulse)
                }
                Circle().fill(tint).frame(width: 29, height: 29)
                Image(systemName: icon)
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundStyle(.white)
                if state == .done || state == .failed {
                    ZStack {
                        Circle()
                            .fill(scheme == .dark ? Color(.systemBackground) : .white)
                            .frame(width: 15, height: 15)
                        Image(systemName: state == .done ? "checkmark" : "xmark")
                            .font(.system(size: 8, weight: .black))
                            .foregroundStyle(tint)
                    }
                    .offset(x: 12, y: 12)
                }
            }
            Text(title)
                .font(.system(size: 9.5, weight: .semibold))
                .lineLimit(1)
            Text(subtitle)
                .font(.system(size: 8))
                .foregroundStyle(.secondary)
                .lineLimit(1)
        }
        .frame(width: 56)
        .onAppear { pulse = true }
    }
}

private struct WorkflowConnector: View {
    let state: WorkflowNodeState

    private var color: Color {
        switch state {
        case .pending: return Color(.systemGray4)
        case .active: return Color(red: 0.04, green: 0.52, blue: 1.0).opacity(0.65)
        case .done: return Color(red: 0.12, green: 0.62, blue: 0.27).opacity(0.65)
        case .failed: return Color.red.opacity(0.55)
        }
    }

    var body: some View {
        HStack(spacing: 0) {
            Rectangle().fill(color).frame(width: 8, height: 1.5)
            Image(systemName: "chevron.right")
                .font(.system(size: 7, weight: .bold))
                .foregroundStyle(color)
        }
        .frame(width: 15)
        .padding(.top, 18)
    }
}

// ==================== 玻璃材质 ====================

// 玻璃 = ultraThinMaterial 底 + 白色渐变覆盖（模拟受光）+ 顶部亮边 + 浅投影。
// 部署目标 iOS 17，不用 glassEffect（26+），此组合在 17/18/26 上观感一致
private struct Glass: ViewModifier {
    @Environment(\.colorScheme) private var scheme

    func body(content: Content) -> some View {
        let light = scheme == .light
        content
            .background {
                RoundedRectangle(cornerRadius: 20, style: .continuous)
                    .fill(.ultraThinMaterial)
                RoundedRectangle(cornerRadius: 20, style: .continuous)
                    .fill(LinearGradient(
                        colors: light ? [.white.opacity(0.42), .white.opacity(0.08)] : [.white.opacity(0.10), .white.opacity(0.03)],
                        startPoint: .top, endPoint: .bottom))
                RoundedRectangle(cornerRadius: 20, style: .continuous)
                    .strokeBorder(LinearGradient(
                        colors: light ? [.white.opacity(0.85), .white.opacity(0.15)] : [.white.opacity(0.22), .white.opacity(0.05)],
                        startPoint: .top, endPoint: .bottom), lineWidth: 1)
            }
            .shadow(color: .black.opacity(light ? 0.07 : 0.28), radius: 16, y: 8)
    }
}

extension View {
    func glass() -> some View { modifier(Glass()) }
}

// ==================== 打字闪烁条 ====================

struct ShimmerBar: View {
    @State private var animate = false

    var body: some View {
        GeometryReader { geo in
            RoundedRectangle(cornerRadius: 6)
                .fill(Color(.systemGray5))
                .frame(width: geo.size.width * 0.7, height: 12)
                .overlay {
                    RoundedRectangle(cornerRadius: 6)
                        .fill(LinearGradient(
                            colors: [.clear, .white.opacity(0.8), .clear],
                            startPoint: .leading, endPoint: .trailing))
                        .frame(width: geo.size.width * 0.4)
                        .offset(x: animate ? geo.size.width * 0.7 : -geo.size.width * 0.4)
                }
                .clipped()
        }
        .frame(height: 12)
        .onAppear {
            withAnimation(.linear(duration: 1.4).repeatForever(autoreverses: false)) { animate = true }
        }
    }
}

// ==================== 日志面板（长按状态徽章打开） ====================

struct LogSheetView: View {
    @ObservedObject var log: AppLog
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            ScrollView {
                Text(log.lines.joined(separator: "\n"))
                    .font(.footnote.monospaced())
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding()
                    .textSelection(.enabled)
            }
            .navigationTitle("运行日志")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                Button("关闭") { dismiss() }
            }
        }
    }
}
