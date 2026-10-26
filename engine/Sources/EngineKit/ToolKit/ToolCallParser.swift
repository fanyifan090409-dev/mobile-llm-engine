import Foundation

/// 从模型输出中提取并解析 <tool_call> 块。
/// 训练契约是 Qwen3 XML 包裹 JSON：<tool_call>\n{json}\n</tool_call>，
/// 但实测官方模型偶发形状漂移（M1.5 抽查 #4：JSON 外层多套一层 "tool_call" 键、
/// 偶发 markdown 围栏包裹），解析器按「先剥壳、后容错」两层兜底。
public enum ToolCallParser {

    /// 一次完整调用：工具名 + 原始参数字典（值保持 JSON 原始类型，校验时再收敛为字符串）
    public struct ParsedCall {
        public let name: String
        public let arguments: [String: Any]
    }

    /// 提取所有 <tool_call>…</tool_call> 块正文（按出现顺序）
    public static func extractBodies(from text: String) -> [String] {
        guard let regex = try? NSRegularExpression(
            pattern: #"<tool_call>\s*(.*?)\s*</tool_call>"#,
            options: [.dotMatchesLineSeparators]) else { return [] }
        let ns = text as NSString
        return regex.matches(in: text, range: NSRange(location: 0, length: ns.length)).compactMap {
            Range($0.range(at: 1), in: text).map { String(text[$0]) }
        }
    }

    /// 从一段模型输出里解析工具调用（T3 端到端实测暴露的真实形状漂移兜底）：
    /// 优先 XML 包裹块；没有则把尾部最后一个 {…} 平衡 JSON 当裸调用解析
    /// （官方 1.7B 无工具模板时输出裸 JSON，如 M1.5 抽查 #4）。
    public static func parseCall(from text: String) -> ParsedCall? {
        if let body = extractBodies(from: text).last, let call = parse(body) {
            return call
        }
        return parse(bareJSONTail(from: text))
    }

    /// 取文本尾部最后一个平衡的 {…} 段（从末尾 } 反向配对，避免命中嵌套内层括号）
    private static func bareJSONTail(from text: String) -> String {
        guard let lastClose = text.lastIndex(of: "}") else { return "" }
        var depth = 0
        var idx = lastClose
        while true {
            let ch = text[idx]
            if ch == "}" { depth += 1 } else if ch == "{" {
                depth -= 1
                if depth == 0 { return String(text[idx...lastClose]) }
            }
            if idx == text.startIndex { break }
            idx = text.index(before: idx)
        }
        return ""  // 括号不闭合 → 还在流式中途，等后续 token 再试
    }

    /// 解析单个块正文为 ParsedCall；解析失败返回 nil
    public static func parse(_ body: String) -> ParsedCall? {
        guard let data = stripped(body).data(using: .utf8),
              let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            return nil
        }
        let normalized = unwrap(obj)
        guard let name = normalized["name"] as? String, !name.isEmpty else { return nil }
        let arguments: [String: Any]
        if let dict = normalized["arguments"] as? [String: Any] {
            arguments = dict
        } else if let str = normalized["arguments"] as? String,
                  let d = try? JSONSerialization.jsonObject(with: Data(str.utf8)) as? [String: Any] {
            arguments = d  // 个别模型把 arguments 又序列化成一串 JSON
        } else {
            arguments = [:]
        }
        return ParsedCall(name: name, arguments: arguments)
    }

    /// 剥 markdown 围栏（```json / ``` 首尾）与首尾空白
    private static func stripped(_ body: String) -> String {
        var s = body.trimmingCharacters(in: .whitespacesAndNewlines)
        if s.hasPrefix("```") {
            if let end = s.range(of: "\n") {
                s = String(s[end.upperBound...])  // 去掉第一行 ```json 之类（upperBound 已在换行符之后）
            } else {
                s = String(s.dropFirst(3))
            }
        }
        if s.hasSuffix("```") { s = String(s.dropLast(3)) }
        return s.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    /// 形状容错：官方模型偶发输出 {"tool_call": {name, arguments}} 外层多套键，剥掉
    private static func unwrap(_ obj: [String: Any]) -> [String: Any] {
        if obj["name"] != nil || obj["arguments"] != nil { return obj }
        if let inner = obj["tool_call"] as? [String: Any] { return inner }
        return obj
    }
}
