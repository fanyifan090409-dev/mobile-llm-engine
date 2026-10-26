import Foundation

/// 校验失败原因：给模型看的纠正文案（ToolLoop 回填 role="tool" 让模型改一次）
public struct ToolValidationError: Error, CustomStringConvertible {
    public let description: String
    public init(_ message: String) { self.description = message }
}

/// 工具调用入参校验：白名单内的工具还要过 schema 关（必填、类型、pattern）。
public enum ToolCallValidator {

    /// 通过 → 规范化参数（全部收敛为字符串，方便 LocalTool 实现取用）；
    /// 失败 → ToolValidationError（描述缺哪个参数/哪里不合规）
    public static func validate(spec: ToolSpec, arguments: [String: Any]) -> Result<[String: String], ToolValidationError> {
        var normalized: [String: String] = [:]
        for p in spec.parameters {
            if let raw = arguments[p.name] {
                guard let str = asString(raw), !str.isEmpty else {
                    return .failure(ToolValidationError("参数 \(p.name) 的值缺失或类型不对，请给出正确的值"))
                }
                if let pattern = p.pattern,
                   str.range(of: pattern, options: .regularExpression) == nil {
                    return .failure(ToolValidationError("参数 \(p.name) 的值 \(str) 不符合格式要求（期望 \(p.description)）"))
                }
                normalized[p.name] = str
            } else if p.required {
                return .failure(ToolValidationError("缺少必填参数 \(p.name)（\(p.description)）"))
            }
        }
        // 规格之外的额外参数照收（工具实现自行决定用不用）
        for (k, v) in arguments where normalized[k] == nil {
            if let s = asString(v) { normalized[k] = s }
        }
        return .success(normalized)
    }

    /// JSON 值 → 字符串：字符串直取；数字/布尔做文本收敛（个别模型时间字段不带引号）
    private static func asString(_ v: Any) -> String? {
        switch v {
        case let s as String: return s
        case let n as NSNumber: return n.stringValue
        default: return nil
        }
    }
}
