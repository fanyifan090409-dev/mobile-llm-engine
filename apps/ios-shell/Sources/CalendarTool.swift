import Foundation
import EventKit
import UIKit
import EngineKit

// 日历工具（iOS 壳版）：EventKit 写入本地日历，确认走系统弹窗（UIAlertController）。
// 参数契约与训练数据逐字节对齐（demo-cli CalendarTool 同款）；
// usagePrompt 训练/推理/拼装三处同步铁律，改任一侧必须三处同步（tech-debt #2 根因）。
final class CalendarTool: LocalTool {
    // harness 自动回归模式跳过 UI 确认；演示/正常使用默认每次人工确认（产品决策）
    private let autoConfirm: Bool
    init(autoConfirm: Bool = false) { self.autoConfirm = autoConfirm }

    // 工具定义触发文本：与训练机 SYNTH_SYS_SCHED1（synthesize_sft.py / SFT3 数据前插）逐字一致。
    static let usagePrompt = ("你是手机助手。当用户要求添加日历事件时，只输出一个工具调用块，"
        + "不要输出任何其他内容，格式：\n"
        + "<tool_call>\n{\"name\": \"add_calendar_event\", \"arguments\": "
        + "{\"title\": \"事件名称\", \"start_time\": \"YYYY-MM-DD HH:mm\", "
        + "\"end_time\": \"YYYY-MM-DD HH:mm\", \"location\": \"地点\", \"note\": \"备注\"}}\n</tool_call>")

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
        ],
        usagePrompt: usagePrompt)

    func execute(_ arguments: [String: Any]) async throws -> ToolResult {
        let title = arguments["title"] as? String ?? ""
        let start = arguments["start_time"] as? String ?? ""
        let end = arguments["end_time"] as? String ?? ""
        let location = arguments["location"] as? String ?? ""
        let note = arguments["note"] as? String ?? ""
        var summary = "「\(title)」\n\(Self.prettyTime(start)) → \(Self.prettyTime(end))"
        if !location.isEmpty { summary += "\n@\(location)" }
        // 模型日期映射可能算错：确认框直接标出「已过去」，由人拦住错误写入
        if let startDate = Self.parseTime(start), startDate < Date() {
            summary += "\n⚠️ 这个时间已经过去了，确认要添加吗？"
        }

        let store = EKEventStore()
        // 先授权再确认：首次运行的系统权限弹窗先出现，避免用户确认后被第二个弹窗打断
        guard try await store.requestFullAccessToEvents() else {
            throw CalendarToolError.accessDenied
        }
        // 写操作默认每次确认（产品决策：关键操作人确认；对应命题书「由谁确认和处理」）
        if !autoConfirm {
            guard await Self.confirmOnDevice(summary) else {
                return ToolResult(status: "error", content: "用户取消了操作，未写入日历")
            }
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
        // 保存后回读：写不进去就如实报错，杜绝「界面说成功、日历里没有」的假添加
        guard let eventID = event.eventIdentifier, store.event(withIdentifier: eventID) != nil else {
            throw CalendarToolError.saveVerifyFailed
        }
        return ToolResult(status: "ok", content: eventID)
    }

    private static func prettyTime(_ s: String) -> String {
        guard let d = parseTime(s) else { return s }
        let c = Calendar.current.dateComponents([.year, .month, .day, .hour, .minute, .weekday], from: d)
        let weekday = ["日", "一", "二", "三", "四", "五", "六"][((c.weekday ?? 1) - 1) % 7]
        return String(format: "%d年%d月%d日（周%@）%02d:%02d",
                      c.year ?? 0, c.month ?? 0, c.day ?? 0, weekday, c.hour ?? 0, c.minute ?? 0)
    }

    // 引擎在 generation 队列上信号量等待确认结果；弹窗必须切回主线程，
    // continuation 在按钮回调里跨线程 resume（CheckedContinuation 本身 Sendable）
    private static func confirmOnDevice(_ summary: String) async -> Bool {
        await withCheckedContinuation { cont in
            Task { @MainActor in
                guard let top = Self.topViewController() else {
                    cont.resume(returning: false)
                    return
                }
                let alert = UIAlertController(title: "日历写入确认", message: summary, preferredStyle: .alert)
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

enum CalendarToolError: Error, CustomStringConvertible {
    case accessDenied
    case noDefaultCalendar
    case badTime
    case saveVerifyFailed

    var description: String {
        switch self {
        case .accessDenied: return "日历访问被拒绝"
        case .noDefaultCalendar: return "系统没有可用的默认日历"
        case .badTime: return "时间格式不正确"
        case .saveVerifyFailed: return "保存后校验失败（日历中未找到该事件）"
        }
    }
}
