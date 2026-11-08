import Foundation

// 相对日期 / 绝对日期 / 中文时间点 → 显式值提示。
// 动因：1.7B SFT17 日期算术弱（「周五」→周四、「晚上八点」→18:00，2026-11-03 Mac/真机实测），
// 但把同一句话改写成「注意：「周五」是2026-11-06。」后输出即正确。
// 壳层因此做确定性解析，模型只负责复制槽位，不依赖心算；气泡仍展示用户原文。
enum TimeHints {

    // 返回可直接拼进 user 消息的提示串（无匹配返回空串）
    static func describe(_ text: String, now: Date = Date()) -> String {
        var hints: [String] = []
        var seen = Set<String>()

        for m in datePhrases(text, now: now) where !seen.contains(m.phrase) {
            seen.insert(m.phrase)
            let f = DateFormatter()
            f.dateFormat = "yyyy-MM-dd"
            f.locale = Locale(identifier: "en_US_POSIX")
            hints.append("注意：「\(m.phrase)」是\(f.string(from: m.day))。")
        }
        for m in timePhrases(text) where !seen.contains(m.phrase) {
            seen.insert(m.phrase)
            hints.append(String(format: "注意：「%@」指%02d:%02d。", m.phrase, m.hour, m.minute))
        }
        return hints.joined()
    }

    // 纯本地自检：不依赖模型，harness 每次启动先跑一遍。
    // 覆盖相对日期、绝对日期、跨年/跨月、周五当天口径和时间点换算。
    static func selfTest(now: Date = Date()) -> [String] {
        var failures: [String] = []
        let cal = Calendar.current
        func at(_ y: Int, _ m: Int, _ d: Int) -> Date {
            cal.date(from: DateComponents(year: y, month: m, day: d, hour: 10)) ?? now
        }
        func check(_ text: String, _ expected: String, at when: Date) {
            let actual = describe(text, now: when)
            if actual != expected {
                failures.append("「\(text)」期望 \(expected)，实际 \(actual)")
            }
        }

        let tue = at(2026, 11, 3)
        check("明天下午三点", "注意：「明天」是2026-11-04。注意：「下午三点」指15:00。", at: tue)
        check("周五晚上七点", "注意：「周五」是2026-11-06。注意：「晚上七点」指19:00。", at: tue)
        check("11月25日晚上八点", "注意：「11月25日」是2026-11-25。注意：「晚上八点」指20:00。", at: tue)
        check("下周五", "注意：「下周五」是2026-11-13。", at: tue)
        check("这周五", "注意：「这周五」是2026-11-06。", at: tue)
        check("大后天", "注意：「大后天」是2026-11-06。", at: tue)
        check("时长约一小时", "", at: tue)
        check("凌晨十二点", "注意：「凌晨十二点」指00:00。", at: tue)
        check("中午十二点", "注意：「中午十二点」指12:00。", at: tue)

        // 周五当天说「周五」：与 harness 的 nextFriday 口径一致，取下一次出现
        check("周五晚上七点", "注意：「周五」是2026-11-13。注意：「晚上七点」指19:00。",
              at: at(2026, 11, 6))

        // 没写年份：已过就顺延到明年；只写几号：本月已过就下个月
        check("1月5日", "注意：「1月5日」是2027-01-05。", at: at(2026, 12, 20))
        check("25号", "注意：「25号」是2026-12-25。", at: at(2026, 12, 20))
        check("5号", "注意：「5号」是2027-01-05。", at: at(2026, 12, 20))
        check("31号", "注意：「31号」是2026-01-31。", at: at(2026, 1, 31))
        check("2月30日", "", at: at(2026, 1, 31))
        return failures
    }

    // MARK: - 日期

    private struct DateMatch { let phrase: String; let day: Date }

    private static func datePhrases(_ text: String, now: Date) -> [DateMatch] {
        var out: [DateMatch] = []
        var cal = Calendar.current
        cal.firstWeekday = 2
        let today = cal.startOfDay(for: now)

        // 固定词（先长后短；命中后从工作副本移除，避免「后天」吃掉「大后天」）
        var work = text
        for (word, delta) in [("大后天", 3), ("后天", 2), ("明天", 1), ("明日", 1),
                              ("明晚", 1), ("今天", 0), ("今日", 0), ("今晚", 0), ("昨晚", -1)] {
            if work.contains(word), let d = cal.date(byAdding: .day, value: delta, to: today) {
                out.append(DateMatch(phrase: word, day: d))
                work = work.replacingOccurrences(of: word,
                                                 with: String(repeating: " ", count: word.count))
            }
        }

        // 周X / 星期X / 礼拜X，支持 下/下下/这/本 前缀
        let pattern = "(下下|下|这|本)?(?:周|星期|礼拜)([一二三四五六日天])"
        if let re = try? NSRegularExpression(pattern: pattern) {
            let ns = work as NSString
            let matches = re.matches(in: work, range: NSRange(location: 0, length: ns.length))
            // 本周一（周一为一周起点）
            let weekday = cal.component(.weekday, from: today)   // 周日=1 … 周六=7
            let daysFromMonday = (weekday + 5) % 7
            let monday = cal.date(byAdding: .day, value: -daysFromMonday, to: today) ?? today
            let cnIndex: [String: Int] = ["一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "日": 7, "天": 7]
            for m in matches {
                let phrase = ns.substring(with: m.range)
                let prefix = m.range(at: 1).location == NSNotFound ? "" : ns.substring(with: m.range(at: 1))
                let dayChar = ns.substring(with: m.range(at: 2))
                guard let idx = cnIndex[dayChar] else { continue }
                var target: Date?
                if prefix.hasPrefix("下下") {
                    target = cal.date(byAdding: .day, value: 14 + idx - 1, to: monday)
                } else if prefix.hasPrefix("下") {
                    target = cal.date(byAdding: .day, value: 7 + idx - 1, to: monday)
                } else {
                    target = cal.date(byAdding: .day, value: idx - 1, to: monday)
                    // 无前缀的「周五」= 下一次周五；当天说也顺延到下周，与 harness 同口径。
                    // 「这/本周五」保留本周语义，过去时间由写入确认框拦截。
                    if let d = target, d <= today, let next = cal.date(byAdding: .day, value: 7, to: d) {
                        target = next
                    }
                }
                if let d = target { out.append(DateMatch(phrase: phrase, day: d)) }
            }
            // 星期短语已消费，避免后面的「几号」再匹配到其中的数字
            for m in matches.reversed() {
                work = (work as NSString).replacingCharacters(in: m.range,
                                                               with: String(repeating: " ", count: m.range.length))
            }
        }

        out.append(contentsOf: absoluteDates(in: &work, now: now))
        return out
    }

    // 绝对日期：2026年11月25日 / 11月25日 / 25号。
    // 没写年份时用系统当前年；日期已过则顺延到下一年/下一月，避免「1月5日」在12月被排到过去。
    private static func absoluteDates(in text: inout String, now: Date) -> [DateMatch] {
        let cal = Calendar.current
        let today = cal.startOfDay(for: now)
        var out: [DateMatch] = []
        let patterns: [(String, Int)] = [
            ("(20\\d{2})\\s*年\\s*(\\d{1,2})\\s*月\\s*(\\d{1,2})\\s*[日号]", 3),
            ("(\\d{1,2})\\s*月\\s*(\\d{1,2})\\s*[日号]", 2),
            ("(\\d{1,2})\\s*[日号]", 1),
        ]

        for (pattern, kind) in patterns {
            guard let re = try? NSRegularExpression(pattern: pattern) else { continue }
            let ns = text as NSString
            let matches = re.matches(in: text, range: NSRange(location: 0, length: ns.length))
            var consumed: [NSRange] = []
            for m in matches {
                let phrase = ns.substring(with: m.range)
                // 无论日期是否合法都先消费整段，避免非法「2月30日」再被「30号」规则二次匹配
                consumed.append(m.range)
                var comps = DateComponents()
                comps.calendar = cal
                comps.timeZone = cal.timeZone
                switch kind {
                case 3:
                    comps.year = Int(ns.substring(with: m.range(at: 1)))
                    comps.month = Int(ns.substring(with: m.range(at: 2)))
                    comps.day = Int(ns.substring(with: m.range(at: 3)))
                case 2:
                    comps.year = cal.component(.year, from: today)
                    comps.month = Int(ns.substring(with: m.range(at: 1)))
                    comps.day = Int(ns.substring(with: m.range(at: 2)))
                default:
                    comps.year = cal.component(.year, from: today)
                    comps.month = cal.component(.month, from: today)
                    comps.day = Int(ns.substring(with: m.range(at: 1)))
                }
                guard var d = cal.date(from: comps) else { continue }
                let got = cal.dateComponents([.year, .month, .day], from: d)
                // Calendar 会把 2月30日 滚动到 3月，这里校验回读，非法日期直接忽略
                guard got.year == comps.year, got.month == comps.month, got.day == comps.day else { continue }

                if kind == 2, d < today, let next = cal.date(byAdding: .year, value: 1, to: d) {
                    d = next
                } else if kind == 1, d < today,
                          let nextMonth = cal.date(byAdding: .month, value: 1, to: today),
                          let nd = cal.date(from: DateComponents(
                            year: cal.component(.year, from: nextMonth),
                            month: cal.component(.month, from: nextMonth),
                            day: comps.day)) {
                    d = nd
                }
                out.append(DateMatch(phrase: phrase, day: d))
            }
            // 从后往前抹掉已识别片段，保留长度；下一轮更短的模式不会重复匹配
            for range in consumed.sorted(by: { $0.location > $1.location }) {
                text = (text as NSString).replacingCharacters(in: range,
                                                              with: String(repeating: " ", count: range.length))
            }
        }
        return out
    }

    // MARK: - 时间点

    private struct TimeMatch { let phrase: String; let hour: Int; let minute: Int }

    // 只认「…点[半|N分]」形式，避开「时长约一小时」这类非时刻表达
    private static func timePhrases(_ text: String) -> [TimeMatch] {
        let pattern = "(凌晨|早上|早晨|上午|中午|下午|傍晚|晚上|今晚|明晚)?\\s*([0-9]{1,2}|[一二三四五六七八九十两]{1,3})\\s*点(半|[0-9]{1,2}分?)?"
        guard let re = try? NSRegularExpression(pattern: pattern) else { return [] }
        let ns = text as NSString
        var out: [TimeMatch] = []
        for m in re.matches(in: text, range: NSRange(location: 0, length: ns.length)) {
            let phrase = ns.substring(with: m.range)
            let period = m.range(at: 1).location == NSNotFound ? "" : ns.substring(with: m.range(at: 1))
            let hourRaw = ns.substring(with: m.range(at: 2))
            guard var hour = number(hourRaw) else { continue }
            var minute = 0
            if m.range(at: 3).location != NSNotFound {
                let suffix = ns.substring(with: m.range(at: 3))
                if suffix == "半" {
                    minute = 30
                } else if let n = Int(suffix.replacingOccurrences(of: "分", with: "")) {
                    minute = n
                }
            }
            switch period {
            case "下午", "傍晚", "晚上", "今晚", "明晚":
                if hour < 12 { hour += 12 }
            case "中午":
                if hour < 11 { hour += 12 }
            case "凌晨":
                if hour == 12 { hour = 0 }
            default:
                break
            }
            guard (0...23).contains(hour), (0...59).contains(minute) else { continue }
            out.append(TimeMatch(phrase: phrase, hour: hour, minute: minute))
        }
        return out
    }

    // 汉字数字（只覆盖 0-99 的常见写法：八、十、十一、二十、二十三）
    private static func number(_ s: String) -> Int? {
        if let n = Int(s) { return n }
        let map: [Character: Int] = ["零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
                                     "五": 5, "六": 6, "七": 7, "八": 8, "九": 9]
        if s == "十" { return 10 }
        let chars = Array(s)
        if chars.count == 2, chars[0] == "十", let tail = map[chars[1]] { return 10 + tail }
        if chars.count == 2, let head = map[chars[0]], chars[1] == "十" { return head * 10 }
        if chars.count == 3, let head = map[chars[0]], chars[1] == "十", let tail = map[chars[2]] {
            return head * 10 + tail
        }
        if chars.count == 1, let single = map[chars[0]] { return single }
        return nil
    }
}
