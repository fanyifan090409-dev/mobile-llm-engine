import Foundation

// CAS 一期验收（docs/plans/数学CAS工具接入.md 第四节）：
// 对 train/eval/math_eval.json 的纯计算子集逐题跑工具路径，报告通过率与 P95 耗时。
// 子集口径由 train/eval/gen_calc_acceptance.py 生成，逐题期望值来自官方答案。
enum CalcSelfTest {
    static func run() -> Bool {
        do {
            let file = try loadFile()
            let engine = MathEvalEngine()
            let loadStart = DispatchTime.now()
            _ = try engine.run(op: "eval", expr: "1+1")
            let loadMilliseconds = elapsed(since: loadStart)

            var passed = 0
            var timings: [Double] = []
            var categories: [String: (ok: Int, total: Int)] = [:]
            var failures: [String] = []

            var routerPassed = 0
            for item in routerCases {
                let routed = CalcRouter.route(item.input)
                if routed.op == item.op && routed.expr == item.expr
                    && routed.variable == item.variable
                    && routed.lower == item.lower && routed.upper == item.upper
                    && routed.statOp == item.statOp && routed.data == item.data {
                    routerPassed += 1
                } else {
                    failures.append("router: \(item.input)\n  实际：\(routed.describe)\n  期望：op=\(item.op) expr=\(item.expr)")
                    print("FAIL router [\(item.input)] -> \(routed.describe)")
                }
            }

            for testCase in file.cases {
                var previous = ""
                var result = ""
                var failureText: String?
                for step in testCase.steps {
                    let expr = (step.usePrevious == true) ? previous : (step.expr ?? "")
                    let started = DispatchTime.now()
                    do {
                        let output = try engine.run(
                            op: step.op,
                            expr: expr,
                            variable: step.variable ?? "x",
                            lower: step.lower ?? "",
                            upper: step.upper ?? "",
                            statOp: step.statOp ?? "",
                            data: step.data ?? "")
                        timings.append(elapsed(since: started))
                        previous = output.result
                        result = step.pick.map { pick($0, from: output.result) } ?? output.result
                    } catch {
                        timings.append(elapsed(since: started))
                        failureText = (error as? LocalizedError)?.errorDescription ?? "\(error)"
                        break
                    }
                }

                let ok = failureText == nil && compare(testCase, actual: result, engine: engine)
                var stats = categories[testCase.category] ?? (0, 0)
                stats.total += 1
                if ok {
                    passed += 1
                    stats.ok += 1
                    print("PASS \(testCase.id) [\(testCase.category)] \(testCase.topic) = \(result)")
                } else {
                    let actual = failureText ?? result
                    failures.append("\(testCase.id) [\(testCase.category)] \(testCase.topic)\n  题目：\(testCase.problem)\n  实际：\(actual)\n  期望：\(expectedText(testCase))")
                    print("FAIL \(testCase.id) [\(testCase.category)] \(testCase.topic) -> \(actual)")
                }
                categories[testCase.category] = stats
            }

            let total = file.cases.count
            let sorted = timings.sorted()
            let p95Index = max(0, min(sorted.count - 1, Int((Double(sorted.count) * 0.95).rounded(.up)) - 1))
            let p95 = sorted.isEmpty ? 0 : sorted[p95Index]
            let slowest = sorted.last ?? 0

            print("\n--- CAS 一期验收 ---")
            print("router: \(routerPassed)/\(routerCases.count)")
            for (category, stats) in categories.sorted(by: { $0.key < $1.key }) {
                print("\(category): \(stats.ok)/\(stats.total)")
            }
            print(String(format: "total: %d/%d (%.1f%%) | 载入 %.0fms | P95 %.1fms | 最慢 %.1fms",
                         passed, total, total == 0 ? 0 : Double(passed) / Double(total) * 100,
                         loadMilliseconds, p95, slowest))
            if !failures.isEmpty {
                print("\n失败明细：")
                failures.forEach { print($0) }
            }
            return passed == total && routerPassed == routerCases.count
        } catch {
            print("CAS 自检无法启动：\(error)", to: &standardError)
            return false
        }
    }

    /// 路由回归：用户实际输入形态 → 结构化请求（含隐式乘法、中文关键词、等号兜底）
    private static let routerCases: [RouterCase] = [
        RouterCase(input: "1/3+1/6", op: "eval", expr: "1/3+1/6"),
        RouterCase(input: "d/dx x^3+2*x", op: "derivative", expr: "x^3+2*x"),
        RouterCase(input: "求导 x^2+1", op: "derivative", expr: "x^2+1"),
        RouterCase(input: "解方程 x^2-5x+6=0", op: "solve", expr: "x^2-5x+6=0"),
        RouterCase(input: "积分 x^2 从 0 到 1", op: "integrate_def", expr: "x^2", lower: "0", upper: "1"),
        RouterCase(input: "integral sin(x) from 0 to pi", op: "integrate_def", expr: "sin(x)", lower: "0", upper: "pi"),
        RouterCase(input: "化简 2x+3x", op: "simplify", expr: "2x+3x"),
        RouterCase(input: "均值: 4,8,6,10,2", op: "stats", expr: "", statOp: "mean", data: "4,8,6,10,2"),
        RouterCase(input: "样本标准差: 2,4,6,8", op: "stats", expr: "", statOp: "std", data: "2,4,6,8"),
        RouterCase(input: "总体方差: 2,4,6,8", op: "stats", expr: "", statOp: "variance_pop", data: "2,4,6,8"),
        RouterCase(input: "solve: 2*x+3=7", op: "solve", expr: "2*x+3=7"),
        RouterCase(input: "x^2-5x+6=0", op: "solve", expr: "x^2-5x+6=0"),
    ]

    private struct RouterCase {
        let input: String
        let op: String
        let expr: String
        var variable = "x"
        var lower = ""
        var upper = ""
        var statOp = ""
        var data = ""
    }

    private static func compare(_ testCase: Case, actual: String, engine: MathEvalEngine) -> Bool {
        switch testCase.kind {
        case "expr":
            return engine.matches(actual: actual, expected: testCase.expectExpr ?? "",
                                  variable: "x", tol: testCase.tol)
        case "num":
            guard let got = parseNumber(actual), let want = testCase.expectNum else { return false }
            return abs(got - want) <= testCase.tol + 1e-6 * abs(want)
        case "set":
            let values = actual.split(whereSeparator: { $0 == "," || $0 == "，" })
                .compactMap { parseNumber(String($0)) }
            guard let expected = testCase.expectSet else { return false }
            return expected.allSatisfy { item in
                guard let want = parseNumber(item) else { return false }
                return values.contains { abs($0 - want) <= testCase.tol + 1e-6 * abs(want) }
            }
        default:
            return false
        }
    }

    /// 支持 "3/2" 分数、普通小数；不认复合表达式（CAS 输出只有数值/分数/逗号根）
    private static func parseNumber(_ raw: String) -> Double? {
        let text = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        if let value = Double(text) { return value }
        let parts = text.split(separator: "/")
        if parts.count == 2, let numerator = Double(parts[0]), let denominator = Double(parts[1]), denominator != 0 {
            return numerator / denominator
        }
        return nil
    }

    private static func pick(_ field: String, from text: String) -> String {
        for part in text.split(separator: ",") {
            let pair = part.split(separator: "=", maxSplits: 1)
                .map { $0.trimmingCharacters(in: .whitespaces) }
            if pair.count == 2 && pair[0] == field { return pair[1] }
        }
        return text
    }

    private static func expectedText(_ testCase: Case) -> String {
        switch testCase.kind {
        case "expr": return testCase.expectExpr ?? ""
        case "num": return testCase.expectNum.map { "\($0)" } ?? ""
        case "set": return (testCase.expectSet ?? []).joined(separator: ", ")
        default: return "?"
        }
    }

    private static func elapsed(since start: DispatchTime) -> Double {
        Double(DispatchTime.now().uptimeNanoseconds - start.uptimeNanoseconds) / 1_000_000
    }

    private static func loadFile() throws -> AcceptanceFile {
        guard let url = Bundle.module.url(forResource: "calc_acceptance", withExtension: "json") else {
            throw MathEvalEngine.Failure.unavailable("缺少 calc_acceptance.json（检查 Package.swift resources）")
        }
        return try JSONDecoder().decode(AcceptanceFile.self, from: Data(contentsOf: url))
    }

    private struct AcceptanceFile: Decodable {
        let source: String
        let note: String?
        let excluded: [String]
        let cases: [Case]
    }

    private struct Case: Decodable {
        let id: String
        let category: String
        let topic: String
        let problem: String
        let steps: [Step]
        let kind: String
        let tol: Double
        let expectExpr: String?
        let expectNum: Double?
        let expectSet: [String]?

        private enum CodingKeys: String, CodingKey {
            case id, category, topic, problem, steps, kind, tol
            case expectExpr = "expect_expr"
            case expectNum = "expect_num"
            case expectSet = "expect_set"
        }
    }

    private struct Step: Decodable {
        let op: String
        let expr: String?
        let variable: String?
        let lower: String?
        let upper: String?
        let statOp: String?
        let data: String?
        let usePrevious: Bool?
        let pick: String?

        private enum CodingKeys: String, CodingKey {
            case op, expr, variable, lower, upper, data, pick
            case statOp = "stat_op"
            case usePrevious = "use_previous"
        }
    }
}
