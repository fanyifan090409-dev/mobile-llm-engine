import Testing
import Foundation
@testable import EngineKit

private func hintCalendar() -> Calendar {
    var cal = Calendar(identifier: .gregorian)
    cal.timeZone = TimeZone(identifier: "Asia/Shanghai")!
    return cal
}

private func hintDate(_ year: Int, _ month: Int, _ day: Int) -> Date {
    hintCalendar().date(from: DateComponents(year: year, month: month, day: day))!
}

@Suite("DateHint 三周日期表")
struct DateHintTests {

    @Test("周五基准：本周一 11-02 / 下周一 11-09 / 下下周日 11-22")
    func fridayTable() {
        let table = DateHint.threeWeekTable(for: hintDate(2026, 11, 6), calendar: hintCalendar())
        #expect(table.hasPrefix("日期参考：本周周一=2026-11-02，"))
        #expect(table.contains("本周周五=2026-11-06"))
        #expect(table.contains("下周周一=2026-11-09"))
        #expect(table.contains("下下周周日=2026-11-22"))
        #expect(table.hasSuffix("。"))
    }

    @Test("跨年：2026-12-31 → 本周一 12-28、下周一 2027-01-04")
    func yearBoundary() {
        let table = DateHint.threeWeekTable(for: hintDate(2026, 12, 31), calendar: hintCalendar())
        #expect(table.contains("本周周一=2026-12-28"))
        #expect(table.contains("下周周一=2027-01-04"))
        #expect(table.contains("下下周周日=2027-01-17"))
    }

    @Test("闰日：2028-02-29 是周二，本周一 02-28")
    func leapDay() {
        let table = DateHint.threeWeekTable(for: hintDate(2028, 2, 29), calendar: hintCalendar())
        #expect(table.contains("本周周一=2028-02-28"))
        #expect(table.contains("本周周二=2028-02-29"))
        #expect(table.contains("下下周周日=2028-03-19"))
    }

    @Test("领队日期行：2026-11-06 是星期五")
    func todayLine() {
        let line = DateHint.todayLine(for: hintDate(2026, 11, 6), calendar: hintCalendar())
        #expect(line == "今天是2026年11月06日（星期五）。")
    }
}
