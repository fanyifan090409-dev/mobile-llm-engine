import Foundation
import EventKit
import EngineKit

// 提醒工具（demo-cli 版）：EventKit 写入本地提醒事项，确认闭包由构造注入（CLI 用 readLine）。
// 参数契约与 SFT20 多模型协作合成提示词一致（set_reminder：content + remind_time）。
// usagePrompt 与 iOS 壳版 ReminderTool 逐字一致；训练侧上线后三处同步铁律同 CalendarTool。
final class ReminderTool: LocalTool {
    static let usagePrompt = ("你是手机助手。当用户要求设置提醒时，只输出一个工具调用块，"
        + "不要输出任何其他内容，格式：\n"
        + "<tool_call>\n{\"name\": \"set_reminder\", \"arguments\": "
        + "{\"content\": \"提醒内容\", \"remind_time\": \"YYYY-MM-DD HH:mm\"}}\n</tool_call>")

    let spec = ToolSpec(
        name: "set_reminder",
        description: "向用户提醒事项添加提醒",
        parameters: [
            ToolParameterSpec(name: "content", type: "string", description: "提醒内容", required: true),
            ToolParameterSpec(name: "remind_time", type: "string", description: "提醒时间，格式 YYYY-MM-DD HH:mm", required: true,
                              pattern: #"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$"#),
        ],
        usagePrompt: usagePrompt)

    private let confirm: @Sendable (String) async -> Bool
    private let trustAlways: Bool

    init(confirm: @escaping @Sendable (String) async -> Bool, trustAlways: Bool = false) {
        self.confirm = confirm
        self.trustAlways = trustAlways
    }

    func execute(_ arguments: [String: Any]) async throws -> ToolResult {
        let content = arguments["content"] as? String ?? ""
        let remindTime = arguments["remind_time"] as? String ?? ""
        let summary = "「\(content)」 @\(remindTime)"

        if !trustAlways {
            guard await confirm(summary) else {
                return ToolResult(status: "error", content: "用户取消了操作，未设置提醒")
            }
        }

        let store = EKEventStore()
        guard try await store.requestFullAccessToReminders() else {
            throw ReminderToolError.accessDenied
        }
        guard let time = Self.parseTime(remindTime) else {
            throw ReminderToolError.badTime
        }

        let reminder = EKReminder(eventStore: store)
        reminder.title = content
        let cal = Calendar.current
        var comps = cal.dateComponents([.year, .month, .day, .hour, .minute], from: time)
        comps.timeZone = cal.timeZone
        reminder.dueDateComponents = comps
        reminder.calendar = store.defaultCalendarForNewReminders()
        try store.save(reminder, commit: true)
        return ToolResult(status: "ok", content: reminder.calendarItemIdentifier)
    }

    private static func parseTime(_ s: String) -> Date? {
        let fmt = DateFormatter()
        fmt.dateFormat = "yyyy-MM-dd HH:mm"
        fmt.locale = Locale(identifier: "en_US_POSIX")
        return fmt.date(from: s)
    }
}

enum ReminderToolError: Error, CustomStringConvertible {
    case accessDenied
    case badTime

    var description: String {
        switch self {
        case .accessDenied: return "提醒事项访问被拒绝"
        case .badTime: return "时间格式不正确"
        }
    }
}
