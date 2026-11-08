import Foundation
import EventKit
import UIKit
import EngineKit

// 提醒工具（iOS 壳版）：EventKit 写入本地提醒事项，确认走系统弹窗（与 CalendarTool 同款模式）。
// 参数契约与 SFT20 多模型协作合成提示词一致（set_reminder：content + remind_time）。
// 注意：usagePrompt 与 demo-cli 侧 ReminderTool 逐字一致；训练侧上线后三处同步铁律同 CalendarTool。
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

    func execute(_ arguments: [String: Any]) async throws -> ToolResult {
        let content = arguments["content"] as? String ?? ""
        let remindTime = arguments["remind_time"] as? String ?? ""
        let summary = "「\(content)」 @\(remindTime)"

        // 写操作默认每次确认（产品决策：关键操作人确认，与日历工具一致）
        guard await Self.confirmOnDevice(summary) else {
            return ToolResult(status: "error", content: "用户取消了操作，未设置提醒")
        }

        let store = EKEventStore()
        // iOS 17+ 提醒事项完整访问授权；拒绝授权抛错，走引擎失败回填路径
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

    // 引擎在 generation 队列上信号量等待确认结果；弹窗必须切回主线程（同 CalendarTool 模式）
    private static func confirmOnDevice(_ summary: String) async -> Bool {
        await withCheckedContinuation { cont in
            Task { @MainActor in
                guard let top = Self.topViewController() else {
                    cont.resume(returning: false)
                    return
                }
                let alert = UIAlertController(title: "提醒写入确认", message: summary, preferredStyle: .alert)
                alert.addAction(UIAlertAction(title: "取消", style: .cancel) { _ in cont.resume(returning: false) })
                alert.addAction(UIAlertAction(title: "确认添加", style: .default) { _ in cont.resume(returning: true) })
                top.present(alert, animated: true)
            }
        }
    }

    private static func topViewController() -> UIViewController? {
        guard let scene = UIApplication.shared.connectedScenes
            .compactMap({ $0 as? UIWindowScene })
            .first(where: { $0.activationState == .foregroundActive }),
              let root = scene.keyWindow?.rootViewController else { return nil }
        var top = root
        while let presented = top.presentedViewController { top = presented }
        return top
    }

    private static func parseTime(_ s: String) -> Date? {
        let fmt = DateFormatter()
        fmt.dateFormat = "yyyy-MM-dd HH:mm"
        fmt.locale = Locale(identifier: "en_US_POSIX")  // 固定格式解析，不随系统区域设置漂移
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
