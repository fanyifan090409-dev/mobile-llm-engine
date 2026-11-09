import Foundation

// Texo 输出 LaTeX → 直接可发给数学模型的题意。
// 目标不是完整 LaTeX 解析器，只覆盖课本常见写法（方程/分式/根式/积分/导数/极限/三角/指数）。
enum FormulaText {
    static func problem(from latex: String) -> String {
        let normalized = normalize(latex)
        guard !normalized.isEmpty else { return "" }

        if let integral = integralProblem(normalized) { return integral }
        if let derivative = derivativeProblem(normalized) { return derivative }
        if let limit = limitProblem(normalized) { return limit }
        if let sum = sumProblem(normalized) { return sum }
        if let binom = binomProblem(normalized) { return binom }

        let expression = mathJS(normalized)
        guard !expression.isEmpty else { return "" }
        if expression.contains("=") {
            return "解方程 \(expression)。"
        }
        return "计算 \(expression)。"
    }

    // MARK: - 归一化

    static func normalize(_ latex: String) -> String {
        var s = latex
        let remove = ["\\left", "\\right", "\\textstyle", "\\displaystyle", "\\scriptstyle",
                      "\\,", "\\;", "\\!", "~", "$"]
        for token in remove { s = s.replacingOccurrences(of: token, with: "") }
        // 公式里的空格无意义；先去掉再处理，避免 Texo 把 c o s 拆开
        s = s.replacingOccurrences(of: " ", with: "")
        s = s.replacingOccurrences(of: "\n", with: "")
        // Texo 会把 sin 拆成 s i n 包在 \mathsf 里；还原成带反斜杠的命令
        s = replaceCommands(s, regex: #"\\operatorname\*?\{lim\}"#, template: "\\\\lim")
        s = replaceCommands(s, regex: #"\\mathsf\{(sin|cos|tan|log|ln|exp)\}"#, template: "\\\\$1")
        s = replaceCommands(s, regex: #"\\mathsf\{([A-Za-z]+)\}"#, template: "$1")
        s = replaceCommands(s, regex: #"\\(?:mathrm|mathit|mathbf)\{([A-Za-z]+)\}"#, template: "$1")
        s = s.replacingOccurrences(of: "\\rarr", with: "\\to")
        s = s.replacingOccurrences(of: "\\rightarrow", with: "\\to")
        // 控制词粘连字母时补回定界空格：\int xdx → \intxdx → \int xdx
        // 必须用已知命令清单，\\([A-Za-z]+) 贪婪回溯会劈错位置（\intxdx → \intxd x）
        s = replaceCommands(s, regex: #"\\(int|sin|cos|tan|log|ln|lim|sum|pi|theta|infty|binom|frac|sqrt|exp)(?=[A-Za-z])"#,
                            template: "\\\\$1 ")
        // 撇号必须在剥 {} 之前：{\prime} 若先剥，^\prime 就匹配不上了
        s = s.replacingOccurrences(of: "^{\\prime}", with: "'")
        s = s.replacingOccurrences(of: "^\\prime", with: "'")
        s = s.replacingOccurrences(of: "\\prime", with: "'")
        // 只剥「包住整条命令」的 {}：^\pi / _\pi 靠花括号定界，剥掉就解析不出上下限
        s = replaceCommands(s, regex: #"(?<![\^_])\{(\\(?:[A-Za-z]+))\}"#, template: "$1")
        // i\pi / 2\pi 这类相邻标识符补乘号，避免去掉空格后连成一个变量
        s = replaceCommands(s, regex: #"([A-Za-z0-9])\\(pi|theta|alpha|beta|gamma|infty)"#, template: "$1*\\\\$2")
        s = replaceCommands(s, regex: #"([A-Za-z0-9])pi"#, template: "$1*pi")
        // Texo 对部分字体的 \log 会读成形近的 109（词表有 \log，属视觉误判）；
        // 只改式子开头的 109_{，真出现 109 下标的课本题极少
        s = replaceCommands(s, regex: #"^109_\{"#, template: "\\\\log_{")
        s = s.replacingOccurrences(of: "\\cdot", with: "*")
        s = s.replacingOccurrences(of: "\\times", with: "*")
        s = s.replacingOccurrences(of: "\\div", with: "/")
        s = s.replacingOccurrences(of: "\\pi", with: "pi")
        s = s.replacingOccurrences(of: "\\infty", with: "inf")
        return s
    }

    // MARK: - 题型

    private static func integralProblem(_ s: String) -> String? {
        guard let range = s.range(of: "\\int") else { return nil }
        var rest = String(s[range.upperBound...])
        var lower = "", upper = ""
        if let (content, end) = readGroup(rest, after: "_") {
            lower = content
            rest = String(rest[end...])
        }
        if let (content, end) = readGroup(rest, after: "^") {
            upper = content
            rest = String(rest[end...])
        }
        rest = replaceCommands(rest, regex: #"d[xX]$"#, template: "")
        let integrand = mathJS(rest)
        guard !integrand.isEmpty else { return nil }
        if !lower.isEmpty, !upper.isEmpty {
            return "求 \(integrand) 从 \(mathJS(lower)) 到 \(mathJS(upper)) 的定积分。"
        }
        return "求 \(integrand) 的不定积分。"
    }

    private static func derivativeProblem(_ s: String) -> String? {
        guard let regex = try? NSRegularExpression(
            pattern: #"\\frac\{d\}\{d([A-Za-z])\}(.+)$"#),
              let match = regex.firstMatch(in: s, range: NSRange(s.startIndex..., in: s)),
              let variableRange = Range(match.range(at: 1), in: s),
              let bodyRange = Range(match.range(at: 2), in: s) else { return nil }
        return "求 \(mathJS(String(s[bodyRange]))) 关于 \(s[variableRange]) 的导数。"
    }

    private static func limitProblem(_ s: String) -> String? {
        guard let regex = try? NSRegularExpression(
            pattern: #"\\lim_\{([A-Za-z])\\to([^{}]+)\}(.+)$"#),
              let match = regex.firstMatch(in: s, range: NSRange(s.startIndex..., in: s)),
              let variableRange = Range(match.range(at: 1), in: s),
              let pointRange = Range(match.range(at: 2), in: s),
              let bodyRange = Range(match.range(at: 3), in: s) else { return nil }
        return "求 \(mathJS(String(s[bodyRange]))) 在 \(s[variableRange])→\(mathJS(String(s[pointRange]))) 时的极限。"
    }

    private static func sumProblem(_ s: String) -> String? {
        guard let regex = try? NSRegularExpression(
            pattern: #"\\sum_\{([A-Za-z])=([^}]*)\}\^\{([^}]*)\}(.+)$"#),
              let match = regex.firstMatch(in: s, range: NSRange(s.startIndex..., in: s)),
              let variableRange = Range(match.range(at: 1), in: s),
              let startRange = Range(match.range(at: 2), in: s),
              let endRange = Range(match.range(at: 3), in: s),
              let bodyRange = Range(match.range(at: 4), in: s) else { return nil }
        return "求 \(mathJS(String(s[bodyRange]))) 从 \(s[variableRange])=\(mathJS(String(s[startRange]))) 到 \(mathJS(String(s[endRange]))) 的和。"
    }

    private static func binomProblem(_ s: String) -> String? {
        guard let regex = try? NSRegularExpression(pattern: #"\\binom\{([^{}]+)\}\{([^{}]+)\}"#),
              let match = regex.firstMatch(in: s, range: NSRange(s.startIndex..., in: s)),
              let firstRange = Range(match.range(at: 1), in: s),
              let secondRange = Range(match.range(at: 2), in: s) else { return nil }
        return "计算组合数 C(\(mathJS(String(s[firstRange]))),\(mathJS(String(s[secondRange]))))。"
    }

    // MARK: - LaTeX → math.js

    static func mathJS(_ latex: String) -> String {
        var s = latex
        // \sin^{2}x → sin(x)^(2)；Texo 常输出这种形式
        s = replaceCommands(s, regex: #"\\(sin|cos|tan)\^\{?([0-9]+)\}?([A-Za-z])"#,
                            template: "$1($3)^($2)")
        s = expandCommand(s, command: "\\frac", arity: 2) { "((\($0[0]))/(\($0[1])))" }
        s = expandCommand(s, command: "\\sqrt", arity: 1) { "sqrt(\($0[0]))" }
        // \log_{2}32 → log(32,2)
        s = replaceCommands(s, regex: #"\\log_\{([^{}]+)\}([A-Za-z0-9]+)"#, template: "log($2,$1)")
        // 只处理带花括号的上下标；裸 ^2 交给 math.js 原样解析，避免贪婪吞掉后面的项
        s = replaceCommands(s, regex: #"\^\{([^{}]+)\}"#, template: "^($1)")
        s = replaceCommands(s, regex: #"_\{([^{}]+)\}"#, template: "_$1")

        let functions = ["arcsin": "asin", "arccos": "acos", "arctan": "atan",
                         "sin": "sin", "cos": "cos", "tan": "tan",
                         "log": "log", "ln": "log", "exp": "exp"]
        for (latexName, swiftName) in functions {
            s = replaceCommands(s, regex: #"\\\#(latexName)\s*\{?([A-Za-z0-9]+)\}?"#, template: "\(swiftName)($1)")
            s = s.replacingOccurrences(of: "\\" + latexName, with: swiftName)
        }
        // Texo 把 \sin 拆成 s i n，去空格后变裸 cosx：补回函数括号
        s = replaceCommands(s, regex: #"(?<![A-Za-z])(sin|cos|tan|log|ln)([A-Za-z])"#, template: "$1($2)")
        // pi 后接字母补乘号：2\pi x → 2*pi*x（mathJS 里可能还留着定界空格）
        s = replaceCommands(s, regex: #"pi\s*(?=[A-Za-z])"#, template: "pi*")
        s = replaceCommands(s, regex: #"\\[A-Za-z]+\s*"#, template: "")
        s = s.replacingOccurrences(of: "{", with: "")
        s = s.replacingOccurrences(of: "}", with: "")
        s = replaceCommands(s, regex: #"([0-9])\s*(?=[A-Za-z(])"#, template: "$1*")
        s = replaceCommands(s, regex: #"\)(?=[A-Za-z0-9(])"#, template: ")*")
        s = replaceCommands(s, regex: #"\s+"#, template: "")
        return s
    }

    // MARK: - 工具

    private static func replaceCommands(_ input: String, regex: String, template: String) -> String {
        guard let expression = try? NSRegularExpression(pattern: regex) else { return input }
        let range = NSRange(input.startIndex..., in: input)
        return expression.stringByReplacingMatches(in: input, range: range, withTemplate: template)
    }

    // 取命令后的上下限：优先 {…}，兼容 Texo 偶发的裸单字符（_0^1）
    // 返回内容与新位置
    private static func readGroup(_ s: String, after marker: String) -> (String, String.Index)? {
        var index = s.startIndex
        while index < s.endIndex, s[index].isWhitespace { index = s.index(after: index) }
        guard index < s.endIndex, String(s[index]) == marker else { return nil }
        index = s.index(after: index)
        while index < s.endIndex, s[index].isWhitespace { index = s.index(after: index) }
        guard index < s.endIndex else { return nil }
        if s[index] != "{" {
            let next = s.index(after: index)
            return (String(s[index]), next)
        }
        var depth = 0
        var content = ""
        while index < s.endIndex {
            let ch = s[index]
            if ch == "{" {
                depth += 1
                if depth > 1 { content.append(ch) }
            } else if ch == "}" {
                depth -= 1
                if depth == 0 { return (content, s.index(after: index)) }
                content.append(ch)
            } else if depth >= 1 {
                content.append(ch)
            }
            index = s.index(after: index)
        }
        return nil
    }

    // 展开 \frac{a}{b} / \sqrt{a}（支持嵌套）
    private static func expandCommand(_ s: String, command: String, arity: Int,
                                      transform: ([String]) -> String) -> String {
        var result = s
        var guardCount = 0
        while let range = result.range(of: command), guardCount < 50 {
            guardCount += 1
            var index = range.upperBound
            var groups: [String] = []
            var ok = true
            for _ in 0..<arity {
                while index < result.endIndex, result[index].isWhitespace { index = result.index(after: index) }
                guard index < result.endIndex, result[index] == "{" else { ok = false; break }
                var depth = 0
                var content = ""
                var cursor = index
                while cursor < result.endIndex {
                    let ch = result[cursor]
                    if ch == "{" {
                        depth += 1
                        if depth > 1 { content.append(ch) }
                    } else if ch == "}" {
                        depth -= 1
                        if depth == 0 { break }
                        content.append(ch)
                    } else if depth >= 1 {
                        content.append(ch)
                    }
                    cursor = result.index(after: cursor)
                }
                if depth != 0 { ok = false; break }
                groups.append(content)
                index = result.index(after: cursor)
            }
            guard ok else { break }
            result.replaceSubrange(range.lowerBound..<index, with: transform(groups))
        }
        return result
    }
}
