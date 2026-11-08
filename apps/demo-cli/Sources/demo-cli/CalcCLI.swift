import Foundation

// CLI 计算入口（CAS 一期）：不加载模型、不走网络，输入即算。
// 交互模式每行先回显「我理解的表达式」，用户可以改；这是防「读错题但算得很准」的唯一保险。
enum CalcCLI {
    static func run(_ input: String?, opts: CLIOptions) -> Int32 {
        let engine = MathEvalEngine()
        guard let input else {
            print("CAS 计算模式（输入表达式；d/dx、积分、解方程、均值等关键词可直接用；Ctrl-D 退出）")
            while true {
                print("\n计算> ", terminator: "")
                fflush(stdout)
                guard let line = readLine() else { break }
                let trimmed = line.trimmingCharacters(in: .whitespacesAndNewlines)
                if trimmed.isEmpty { continue }
                var request = CalcRouter.route(trimmed)
                applyOverrides(&request, opts)
                printCalc(request, engine: engine)
            }
            return 0
        }
        var request = CalcRouter.route(input)
        applyOverrides(&request, opts)
        return printCalc(request, engine: engine) ? 0 : 1
    }

    private static func applyOverrides(_ request: inout CalcRequest, _ opts: CLIOptions) {
        if let op = opts.calcOp, !op.isEmpty { request.op = op }
        if let variable = opts.calcVariable, !variable.isEmpty { request.variable = variable }
        if let lower = opts.calcLower { request.lower = lower }
        if let upper = opts.calcUpper { request.upper = upper }
        if let statOp = opts.calcStat, !statOp.isEmpty { request.statOp = statOp }
        if let data = opts.calcData { request.data = data }
    }

    @discardableResult
    private static func printCalc(_ request: CalcRequest, engine: MathEvalEngine) -> Bool {
        if request.op == "stats" && request.statOp.isEmpty {
            print("stats 需要 --calc-stat（mean/median/variance/std/variance_pop/std_pop/iqr/…）", to: &standardError)
            return false
        }
        if request.op != "stats" && request.expr.isEmpty {
            print("缺少计算表达式", to: &standardError)
            return false
        }
        print("[计算] \(request.describe)")
        do {
            let output = try engine.run(
                op: request.op,
                expr: request.expr,
                variable: request.variable,
                lower: request.lower,
                upper: request.upper,
                statOp: request.statOp,
                data: request.data)
            let marker = output.numeric ? "（数值解）" : ""
            print("= \(output.result)\(marker)    [\(output.milliseconds)ms]")
            if !output.latex.isEmpty { print("  LaTeX: \(output.latex)") }
            return true
        } catch {
            let message = (error as? LocalizedError)?.errorDescription ?? "\(error)"
            print("计算失败：\(message)", to: &standardError)
            return false
        }
    }
}
