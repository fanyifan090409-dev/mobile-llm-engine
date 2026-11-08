import Foundation
import EngineKit

// math_eval 工具（应用层）：模型把题意翻译成结构化表达式，CAS 负责精确计算。
// 结果走 .result 风格（{"status":"ok","result":"…"}），与 SFT20 领队工具回填一致。
// usagePrompt 是二期工具调用 SFT 的训练契约：上线训练前必须逐字对齐，不能只改这一侧。
final class MathEvalTool: LocalTool {
    static let usagePrompt = ("你是数学助手。遇到需要精确计算时，第一步只输出一个工具调用块，不要输出其他内容，格式：\n"
        + "<tool_call>\n{\"name\": \"math_eval\", \"arguments\": {\"op\": \"eval\", \"expr\": \"x^2+3*x\"}}\n</tool_call>\n"
        + "expr 用 math.js 语法：乘方 ^、乘法 *、函数 sin(x)/cos(x)/exp(x)/log(x)/log(x, 底数)；不要用 LaTeX 的 {}、\\frac、\\log_2。\n"
        + "op 可选 eval（求值）/ derivative（求导）/ simplify（化简）/ integrate_def（定积分）/ solve（解方程）/ stats（统计）。"
        + "solve 可写 \"x^2-5x+6=0\"；积分与解方程用 lower/upper 给区间（可写 pi/2）；"
        + "stats 用 stat_op 与 data：mean/median/variance/std/variance_pop/std_pop/iqr/sum/min/max/combination/permutation/binomial/regression/normalcdf，"
        + "data 逗号分隔，regression 用 \"x1,y1;x2,y2\"，normalcdf 用 \"mu,sigma,x\"。"
        + "收到工具结果后，如果还需要下一步计算就继续调用工具；否则用中文简要讲解，并在最后一行写【答案】。")

    let spec = ToolSpec(
        name: "math_eval",
        description: "精确计算数学表达式（求值/求导/化简/定积分/解方程/统计）；输入必须是结构化表达式，不能是自然语言",
        parameters: [
            ToolParameterSpec(name: "op", type: "string", description: "eval | derivative | simplify | integrate_def | solve | stats",
                              required: true,
                              pattern: #"^(eval|derivative|simplify|integrate_def|integrate_indef|solve|stats)$"#),
            ToolParameterSpec(name: "expr", type: "string", description: "表达式，如 x^2+3*x；stats 时可省略", required: false),
            ToolParameterSpec(name: "variable", type: "string", description: "自变量，默认 x", required: false),
            ToolParameterSpec(name: "lower", type: "string", description: "定积分下限 / 解方程区间下限，可写 pi/2", required: false),
            ToolParameterSpec(name: "upper", type: "string", description: "定积分上限 / 解方程区间上限", required: false),
            ToolParameterSpec(name: "stat_op", type: "string",
                              description: "mean | median | variance | std | variance_pop | std_pop | iqr | sum | min | max | combination | permutation | binomial | regression | normalcdf",
                              required: false),
            ToolParameterSpec(name: "data", type: "string", description: "统计数据，逗号分隔；regression 用 x1,y1;x2,y2", required: false),
        ],
        usagePrompt: usagePrompt,
        feedbackStyle: .result)

    private let engine: MathEvalEngine

    init(engine: MathEvalEngine = .shared) {
        self.engine = engine
    }

    func execute(_ arguments: [String: Any]) async throws -> ToolResult {
        let op = (arguments["op"] as? String ?? "").trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        guard !op.isEmpty else {
            return ToolResult(status: "error", content: "缺少 op 参数")
        }
        let expr = (arguments["expr"] as? String ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        if op != "stats" && expr.isEmpty {
            return ToolResult(status: "error", content: "op=\(op) 需要 expr 参数")
        }
        let statOp = (arguments["stat_op"] as? String ?? "").trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        if op == "stats" && statOp.isEmpty {
            return ToolResult(status: "error", content: "op=stats 需要 stat_op 参数（mean/median/variance/…）")
        }
        do {
            let out = try engine.run(
                op: op,
                expr: expr,
                variable: (arguments["variable"] as? String).flatMap { $0.isEmpty ? nil : $0 } ?? "x",
                lower: arguments["lower"] as? String ?? "",
                upper: arguments["upper"] as? String ?? "",
                statOp: statOp,
                data: arguments["data"] as? String ?? "")
            return ToolResult(status: "ok", content: out.numeric ? "\(out.result)（数值解）" : out.result)
        } catch {
            return ToolResult(status: "error", content: (error as? LocalizedError)?.errorDescription ?? "\(error)")
        }
    }
}
