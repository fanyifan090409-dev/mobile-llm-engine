import Foundation
import EventKit
import EngineKit

// 日历工具（apps 层）：EventKit 写入本地日历，参数契约与训练数据逐字节对齐。
// 确认逻辑由构造注入的闭包决定（CLI 用 readLine；iOS 版换成系统弹窗），
// 完全信任模式（trustAlways）跳过确认——开启入口必须打印强提醒（见 main.swift --trust-tools）。
final class CalendarTool: LocalTool {
    let spec = ToolSpec(
        name: "add_calendar_event",
        description: "向用户日历添加事件",
        parameters: [
            ToolParameterSpec(name: "title", type: "string", description: "事件名称", required: true),
            ToolParameterSpec(name: "start_time", type: "string", description: "开始时间，格式 YYYY-MM-DD HH:mm", required: true,
                              pattern: #"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$"#),
            ToolParameterSpec(name: "end_time", type: "string", description: "结束时间，格式 YYYY-MM-DD HH:mm", required: true,
                              pattern: #"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$"#),
            ToolParameterSpec(name: "location", type: "string", description: "地点", required: false),
            ToolParameterSpec(name: "note", type: "string", description: "备注", required: false),
        ])

    private let confirm: @Sendable (String) async -> Bool
    private let trustAlways: Bool

    init(confirm: @escaping @Sendable (String) async -> Bool, trustAlways: Bool = false) {
        self.confirm = confirm
        self.trustAlways = trustAlways
    }

    func execute(_ arguments: [String: Any]) async throws -> ToolResult {
        let title = arguments["title"] as? String ?? ""
        let start = arguments["start_time"] as? String ?? ""
        let end = arguments["end_time"] as? String ?? ""
        let location = arguments["location"] as? String ?? ""
        let note = arguments["note"] as? String ?? ""
        let summary = "「\(title)」 \(start) ~ \(end)\(location.isEmpty ? "" : " @\(location)")"

        if !trustAlways {
            guard await confirm(summary) else {
                return ToolResult(status: "error", content: "用户取消了操作，未写入日历")
            }
        }

        let store = EKEventStore()
        // macOS 14+/iOS 17+ 完整访问授权；拒绝授权抛错，走引擎失败回填路径
        guard try await store.requestFullAccessToEvents() else {
            throw CalendarToolError.accessDenied
        }
        guard let calendar = store.defaultCalendarForNewEvents else {
            throw CalendarToolError.noDefaultCalendar
        }
        guard let startDate = Self.parseTime(start), let endDate = Self.parseTime(end) else {
            throw CalendarToolError.badTime
        }

        let event = EKEvent(eventStore: store)
        event.title = title
        event.startDate = startDate
        event.endDate = endDate
        event.location = location.isEmpty ? nil : location
        event.notes = note.isEmpty ? nil : note
        event.calendar = calendar
        try store.save(event, span: .thisEvent)
        return ToolResult(status: "ok", content: event.eventIdentifier ?? "evt_local")
    }

    private static func parseTime(_ s: String) -> Date? {
        let fmt = DateFormatter()
        fmt.dateFormat = "yyyy-MM-dd HH:mm"
        fmt.locale = Locale(identifier: "en_US_POSIX")  // 固定格式解析，不随系统区域设置漂移
        return fmt.date(from: s)
    }
}

enum CalendarToolError: Error, CustomStringConvertible {
    case accessDenied
    case noDefaultCalendar
    case badTime

    var description: String {
        switch self {
        case .accessDenied: return "日历访问被拒绝"
        case .noDefaultCalendar: return "系统没有可用的默认日历"
        case .badTime: return "时间格式不正确"
        }
    }
}
