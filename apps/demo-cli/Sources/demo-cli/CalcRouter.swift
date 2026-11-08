import Foundation

// CAS 一期的确定性路由：用户输入 → 结构化计算请求。
// 只认数学表达式与少量关键词；读不懂的题不猜——回显「我理解的表达式」让用户改（计划第四节）。
struct CalcRequest {
    var op: String
    var expr: String
    var variable = "x"
    var lower = ""
    var upper = ""
    var statOp = ""
    var data = ""

    var describe: String {
        var parts = ["op=\(op)", "expr=\(expr)"]
        if variable != "x" { parts.append("variable=\(variable)") }
        if !lower.isEmpty || !upper.isEmpty { parts.append("区间=[\(lower), \(upper)]") }
        if !statOp.isEmpty { parts.append("stat=\(statOp)") }
        if !data.isEmpty { parts.append("data=\(data)") }
        return parts.joined(separator: " ")
    }
}

enum CalcRouter {
    static func route(_ input: String) -> CalcRequest {
        let text = input.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return CalcRequest(op: "eval", expr: "") }

        if let (op, rest) = explicitPrefix(text) {
            return CalcRequest(op: op, expr: rest)
        }
        if let m = captures(#"^d/d([A-Za-z])\s*(.+)$"#, text) {
            return CalcRequest(op: "derivative", expr: m[1].trimmingCharacters(in: .whitespaces), variable: m[0])
        }
        if let m = captures(#"^(?:derivative|求导)[:：]?\s*(.+)$"#, text) {
            return CalcRequest(op: "derivative", expr: m[0].trimmingCharacters(in: .whitespaces))
        }
        if let m = captures(#"^(?:integral|integrate|积分|∫)[:：]?\s*(.+?)\s*(?:from|从)\s*(\S+?)\s*(?:to|到)\s*(\S+)$"#, text) {
            return CalcRequest(op: "integrate_def", expr: m[0].trimmingCharacters(in: .whitespaces),
                               lower: m[1], upper: m[2])
        }
        if let m = captures(#"^(?:integral|integrate|积分|∫)[:：]?\s*(.+)$"#, text) {
            return CalcRequest(op: "integrate_indef", expr: m[0].trimmingCharacters(in: .whitespaces))
        }
        if let m = captures(#"^(?:solve|解方程)[:：]?\s*(.+)$"#, text) {
            return CalcRequest(op: "solve", expr: m[0].trimmingCharacters(in: .whitespaces))
        }
        if let m = captures(#"^(?:simplify|化简)[:：]?\s*(.+)$"#, text) {
            return CalcRequest(op: "simplify", expr: m[0].trimmingCharacters(in: .whitespaces))
        }
        if let m = captures(#"^(?:eval|计算|求值)[:：]?\s*(.+)$"#, text) {
            return CalcRequest(op: "eval", expr: m[0].trimmingCharacters(in: .whitespaces))
        }
        if let (statOp, data) = statsRoute(text) {
            return CalcRequest(op: "stats", expr: "", statOp: statOp, data: data)
        }
        // 含等号的式子默认解方程；其余按纯求值
        if text.contains("=") {
            return CalcRequest(op: "solve", expr: text)
        }
        return CalcRequest(op: "eval", expr: text)
    }

    private static func explicitPrefix(_ text: String) -> (String, String)? {
        let ops = ["eval", "simplify", "derivative", "solve", "integrate_def", "integrate_indef", "stats"]
        for op in ops {
            for sep in [":", "："] {
                if text.lowercased().hasPrefix(op + sep) {
                    let rest = String(text.dropFirst(op.count + sep.count)).trimmingCharacters(in: .whitespaces)
                    return (op, rest)
                }
            }
        }
        return nil
    }

    private static func statsRoute(_ text: String) -> (String, String)? {
        let rules: [(String, String)] = [
            (#"^(?:回归|regression)[:：]?\s*(.+)$"#, "regression"),
            (#"^(?:组合数|组合|combination)[:：]?\s*(.+)$"#, "combination"),
            (#"^(?:排列数|排列|permutation)[:：]?\s*(.+)$"#, "permutation"),
            (#"^(?:二项分布|binomial)[:：]?\s*(.+)$"#, "binomial"),
            (#"^(?:样本标准差|std_sample|sample_std)[:：]?\s*(.+)$"#, "std"),
            (#"^(?:总体标准差|std_pop|population_std)[:：]?\s*(.+)$"#, "std_pop"),
            (#"^(?:样本方差|variance_sample|sample_variance)[:：]?\s*(.+)$"#, "variance"),
            (#"^(?:总体方差|方差|variance_pop|population_variance)[:：]?\s*(.+)$"#, "variance_pop"),
            (#"^(?:四分位距|iqr)[:：]?\s*(.+)$"#, "iqr"),
            (#"^(?:平均数|均值|mean)[:：]?\s*(.+)$"#, "mean"),
            (#"^(?:中位数|median)[:：]?\s*(.+)$"#, "median"),
        ]
        for (pattern, op) in rules {
            if let m = captures(pattern, text) { return (op, m[0].trimmingCharacters(in: .whitespaces)) }
        }
        return nil
    }

    private static func captures(_ pattern: String, _ text: String) -> [String]? {
        guard let regex = try? NSRegularExpression(pattern: pattern, options: [.caseInsensitive]) else { return nil }
        let range = NSRange(text.startIndex..., in: text)
        guard let match = regex.firstMatch(in: text, options: [], range: range) else { return nil }
        return (1..<match.numberOfRanges).map { index in
            guard let r = Range(match.range(at: index), in: text) else { return "" }
            return String(text[r])
        }
    }
}
