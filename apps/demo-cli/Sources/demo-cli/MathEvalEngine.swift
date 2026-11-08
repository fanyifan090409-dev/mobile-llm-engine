import Foundation
import JavaScriptCore

// CAS 一期（docs/plans/数学CAS工具接入.md）：JavaScriptCore 加载打包进 App 的 math.js（Apache-2.0）。
// 离线运行、不加载远程 JS、不使用 eval/Function；模型只负责列式与讲解，精确计算全部走这里。
// 线程模型：JSContext 非线程安全，所有调用串行化到内部锁；计算本身是毫秒级同步任务。
final class MathEvalEngine {
    struct Output: Sendable {
        let result: String
        let latex: String
        /// true = 数值解（积分/解方程/统计），UI 需标注，避免被当成精确符号解
        let numeric: Bool
        let milliseconds: Int
    }

    enum Failure: LocalizedError {
        case unavailable(String)
        case computation(String)

        var errorDescription: String? {
            switch self {
            case .unavailable(let message), .computation(let message): return message
            }
        }
    }

    static let shared = MathEvalEngine()

    /// 表达式长度上限：正常题目远低于此值；超长输入直接拒绝，避免拖死 UI 线程
    private static let maxExpressionLength = 1000
    private static let maxDataLength = 4000

    private let bundle: Bundle
    private let lock = NSLock()
    private var context: JSContext?
    private var casEval: JSValue?
    private var loadFailure: String?

    init(bundle: Bundle = .module) {
        self.bundle = bundle
    }

    func run(op: String, expr: String,
             variable: String = "x",
             lower: String = "", upper: String = "",
             statOp: String = "", data: String = "") throws -> Output {
        guard expr.count <= Self.maxExpressionLength else {
            throw Failure.computation("表达式过长（上限 \(Self.maxExpressionLength) 字符）")
        }
        guard data.count <= Self.maxDataLength else {
            throw Failure.computation("数据过长（上限 \(Self.maxDataLength) 字符）")
        }
        lock.lock()
        defer { lock.unlock() }
        let function = try load()
        guard let raw = function.call(withArguments: [op, expr, variable, lower, upper, statOp, data])?.toString(),
              let payload = try? JSONDecoder().decode(Payload.self, from: Data(raw.utf8)) else {
            throw Failure.computation(context?.exception?.toString() ?? "计算引擎返回了无法解析的结果")
        }
        guard payload.status == "ok" else {
            throw Failure.computation(payload.result)
        }
        return Output(result: payload.result,
                      latex: payload.latex ?? "",
                      numeric: payload.numeric ?? false,
                      milliseconds: payload.ms ?? 0)
    }

    /// 验收专用：按采样点数值对拍两条表达式（判分口径同 train/eval/score_math_eval.py）
    func matches(actual: String, expected: String, variable: String = "x", tol: Double = 1e-6) -> Bool {
        lock.lock()
        defer { lock.unlock() }
        guard let _ = try? load(),
              let compare = context?.objectForKeyedSubscript("__casCompare"),
              !compare.isUndefined,
              let raw = compare.call(withArguments: [actual, expected, variable, tol])?.toString(),
              let payload = try? JSONDecoder().decode(ComparePayload.self, from: Data(raw.utf8)) else {
            return false
        }
        return payload.status == "ok" && payload.result == "true"
    }

    private struct Payload: Decodable {
        let status: String
        let result: String
        let latex: String?
        let numeric: Bool?
        let ms: Int?
    }

    private struct ComparePayload: Decodable {
        let status: String
        let result: String
    }

    /// 懒加载：首次计算才读 634KB math.js，不在启动路径上
    private func load() throws -> JSValue {
        if let casEval { return casEval }
        if let loadFailure { throw Failure.unavailable(loadFailure) }
        do {
            guard let mathURL = bundle.url(forResource: "math", withExtension: "js"),
                  let bridgeURL = bundle.url(forResource: "MathEvalBridge", withExtension: "js") else {
                throw Failure.unavailable("缺少 math.js 资源（检查 Package.swift resources）")
            }
            let mathSource = try String(contentsOf: mathURL, encoding: .utf8)
            let bridgeSource = try String(contentsOf: bridgeURL, encoding: .utf8)
            guard let context = JSContext() else {
                throw Failure.unavailable("JavaScriptCore 初始化失败")
            }
            var exceptionText: String?
            context.exceptionHandler = { _, value in
                exceptionText = value?.toString() ?? "unknown"
            }
            context.evaluateScript(mathSource)
            if let exceptionText {
                throw Failure.unavailable("math.js 加载失败：\(exceptionText)")
            }
            context.evaluateScript(bridgeSource)
            if let exceptionText {
                throw Failure.unavailable("CAS 桥接脚本加载失败：\(exceptionText)")
            }
            guard let function = context.objectForKeyedSubscript("__casEval"),
                  !function.isUndefined, function.isObject else {
                throw Failure.unavailable("CAS 桥接函数未注册")
            }
            self.context = context
            self.casEval = function
            return function
        } catch {
            let message = (error as? LocalizedError)?.errorDescription ?? "\(error)"
            loadFailure = message
            throw Failure.unavailable(message)
        }
    }
}
