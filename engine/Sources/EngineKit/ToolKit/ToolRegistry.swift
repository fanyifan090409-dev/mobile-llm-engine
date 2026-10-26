import Foundation

/// 工具白名单注册表：应用层编译期注册（registerTool），引擎层执行前按名字查。
/// 查重拒绝——同名工具直接抛错，杜绝「后注册静默覆盖先注册」的隐性 bug。
public final class ToolRegistry: @unchecked Sendable {
    private let lock = NSLock()
    private var tools: [String: LocalTool] = [:]

    public init() {}

    /// 注册工具；重名抛错。工具名与训练契约一致（如 add_calendar_event）
    public func register(_ tool: LocalTool) throws {
        lock.lock()
        defer { lock.unlock() }
        guard tools[tool.spec.name] == nil else {
            throw ToolKitError.duplicateTool(tool.spec.name)
        }
        tools[tool.spec.name] = tool
    }

    /// 按名字查工具（无则 nil，调用侧按「幻觉工具名」处理）
    public func tool(named name: String) -> LocalTool? {
        lock.lock()
        defer { lock.unlock() }
        return tools[name]
    }

    public var allTools: [LocalTool] {
        lock.lock()
        defer { lock.unlock() }
        return Array(tools.values)
    }
}

public enum ToolKitError: Error, CustomStringConvertible {
    case duplicateTool(String)

    public var description: String {
        switch self {
        case .duplicateTool(let name): return "工具重复注册：\(name)"
        }
    }
}
