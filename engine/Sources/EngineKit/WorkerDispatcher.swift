import Foundation

/// 派单进度：UI 工作流可视化用，事件必须来自真实执行阶段。
public enum DispatchStage: Sendable {
    case started(worker: String, task: String)
    case workerOutput(worker: String, toolName: String, arguments: [String: String])
    case finished(worker: String, toolName: String, status: String, detail: String)
}

/// 工人一次成功调用的结果：工具名 + 字符串化参数 + 原始输出（排查用）。
public struct WorkerToolCall: Sendable {
    public let worker: String
    public let toolName: String
    public let arguments: [String: String]
    public let rawText: String

    public init(worker: String, toolName: String, arguments: [String: String], rawText: String) {
        self.worker = worker
        self.toolName = toolName
        self.arguments = arguments
        self.rawText = rawText
    }
}

public enum WorkerDispatcherError: Error, CustomStringConvertible {
    case unknownWorker(String)
    case modelFileMissing(String)
    case noToolCall(String)

    public var description: String {
        switch self {
        case .unknownWorker(let name): return "未知工人：\(name)"
        case .modelFileMissing(let path): return "工人模型不存在：\(path)"
        case .noToolCall(let output): return "工人没有输出有效工具调用：\(output.prefix(120))"
        }
    }
}

/// 进程内工人调度：每个工人一个懒加载 EngineCore，模型按路径复用。
/// 关键约束：日历/提醒工人的 user 消息末尾必须追加三周日期表（SFT20c 训练契约）。
public actor WorkerDispatcher {
    public typealias Runner = @Sendable (_ profile: WorkerProfile, _ messages: [Message]) async throws -> String

    private let profiles: [String: WorkerProfile]
    private let runner: Runner?
    // 按模型身份缓存，不按工人名：四个工人常共用同一份 0.6B，按名缓存会把权重加载四份
    private var engines: [String: EngineCore] = [:]

    public init(profiles: [WorkerProfile], runner: Runner? = nil) {
        self.profiles = Dictionary(uniqueKeysWithValues: profiles.map { ($0.name, $0) })
        self.runner = runner
    }

    static func cacheKey(for profile: WorkerProfile) -> String {
        "\(profile.modelURL.path)|\(profile.quant)|\(profile.context)"
    }

    public func dispatch(worker: String, task: String, now: Date = Date(),
                         onStage: (@Sendable (DispatchStage) -> Void)? = nil) async throws -> WorkerToolCall {
        guard let profile = profiles[worker] else {
            throw WorkerDispatcherError.unknownWorker(worker)
        }
        // 工人训练数据 user 全部以「派单：」开头；领队 task 不带前缀，这里补齐以免分布偏移
        let dispatched = task.hasPrefix("派单：") ? task : "派单：" + task
        onStage?(.started(worker: worker, task: dispatched))
        let userContent = profile.needsDateTable
            ? dispatched + DateHint.threeWeekTable(for: now)
            : dispatched
        let messages = [
            Message(role: "system", content: profile.systemPrompt),
            Message(role: "user", content: userContent),
        ]

        let output: String
        if let runner {
            output = try await runner(profile, messages)
        } else {
            output = try await runLlama(profile: profile, messages: messages)
        }

        guard let parsed = ToolCallParser.parseCall(from: output) else {
            throw WorkerDispatcherError.noToolCall(output)
        }
        let arguments = Self.stringify(parsed.arguments)
        onStage?(.workerOutput(worker: worker, toolName: parsed.name, arguments: arguments))
        return WorkerToolCall(worker: worker, toolName: parsed.name,
                              arguments: arguments, rawText: output)
    }

    public func unloadAll() {
        for engine in engines.values { engine.unload() }
        engines.removeAll()
    }

    private func runLlama(profile: WorkerProfile, messages: [Message]) async throws -> String {
        guard FileManager.default.fileExists(atPath: profile.modelURL.path) else {
            throw WorkerDispatcherError.modelFileMissing(profile.modelURL.path)
        }
        let key = Self.cacheKey(for: profile)
        let engine: EngineCore
        if let cached = engines[key] {
            engine = cached
        } else {
            let new = EngineCore()
            try await new.load(profile.modelSpec)
            engines[key] = new
            engine = new
        }
        var output = ""
        for try await event in engine.generate(GenerationRequest(
            messages: messages, maxTokens: 256, temperature: 0, speed: .balanced, tools: nil)) {
            if case .token(let piece) = event { output += piece }
        }
        return output
    }

    private static func stringify(_ args: [String: Any]) -> [String: String] {
        args.compactMapValues { value in
            if let s = value as? String { return s }
            if let n = value as? NSNumber { return n.stringValue }
            return nil
        }
    }
}
