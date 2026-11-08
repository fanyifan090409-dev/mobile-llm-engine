import Foundation

/// 三周日期表：SFT20c 工人训练输入的固定格式，推理侧由引擎逐字追加。
/// 训练契约见 train/synthesize/add_date_table.py；周约定 ISO（周一起）。
public enum DateHint {
    private static let weekdays = ["一", "二", "三", "四", "五", "六", "日"]
    private static let weekLabels = ["本周", "下周", "下下周"]

    /// 例：`日期参考：本周周一=2026-11-02，…；下周周一=2026-11-09，…；下下周周一=2026-11-16，…。`
    public static func threeWeekTable(for date: Date = Date(), calendar: Calendar = .current) -> String {
        var cal = calendar
        cal.timeZone = calendar.timeZone
        let start = cal.startOfDay(for: date)
        // Gregorian weekday: 1=周日 … 7=周六；换算成周一起的偏移
        let weekday = cal.component(.weekday, from: start)
        let mondayOffset = (weekday + 5) % 7
        let monday = cal.date(byAdding: .day, value: -mondayOffset, to: start) ?? start

        let fmt = DateFormatter()
        fmt.calendar = cal
        fmt.timeZone = cal.timeZone
        fmt.locale = Locale(identifier: "en_US_POSIX")
        fmt.dateFormat = "yyyy-MM-dd"

        let segments: [String] = weekLabels.enumerated().map { weekIndex, label in
            let days: [String] = weekdays.enumerated().map { dayIndex, weekdayName in
                let offset = weekIndex * 7 + dayIndex
                let day = cal.date(byAdding: .day, value: offset, to: monday) ?? monday
                return "\(label)周\(weekdayName)=\(fmt.string(from: day))"
            }
            return days.joined(separator: "，")
        }
        return "日期参考：" + segments.joined(separator: "；") + "。"
    }

    /// 领队 system 注入用：`今天是2026年11月06日（星期五）。`
    public static func todayLine(for date: Date = Date(), calendar: Calendar = .current) -> String {
        let comps = calendar.dateComponents([.year, .month, .day, .weekday], from: date)
        let names = ["日", "一", "二", "三", "四", "五", "六"]
        let weekday = names[max(0, min(6, (comps.weekday ?? 1) - 1))]
        return String(format: "今天是%04d年%02d月%02d日（星期%@）。",
                      comps.year ?? 0, comps.month ?? 0, comps.day ?? 0, weekday)
    }
}
