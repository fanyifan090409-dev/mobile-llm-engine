#!/usr/bin/env python3
"""SFT20b 工人日期补训数据生成：规则计算相对日期，混入 SFT20 回放防遗忘。

周约定与 SFT20 训练数据一致：本周 = ISO 周（周一起），下周 = 下一个 ISO 周。
输出与 cloud_sft20/worker_sft20.jsonl 同构，另出 60 题 held-out 评测集。

用法：
  python3 gen_date_worker.py --replay train/synthesize/cloud_sft20/worker_sft20.jsonl \
      --outdir train/synthesize/date_sft20b --eval-out train/eval/date_worker_eval.json
"""
import argparse
import calendar
import json
import os
import random
from collections import Counter
from datetime import date, datetime, timedelta

SYSTEM_CAL = (
    "你是手机上的日历工人，只处理日历相关派单。收到派单后只输出一个工具调用块，不要任何其他文字，格式：\n"
    "<tool_call>\n"
    '{"name": "add_calendar_event", "arguments": {"title": "事件名称", "start_time": "YYYY-MM-DD HH:mm", '
    '"end_time": "YYYY-MM-DD HH:mm", "location": "地点", "note": "备注"}}\n'
    "</tool_call>；没有的地点或备注填空字符串。日期必须换算成具体日期，不允许输出相对日期。"
)
SYSTEM_REM = (
    "你是手机上的提醒工人，只处理提醒相关派单。收到派单后只输出一个工具调用块，不要任何其他文字，格式：\n"
    "<tool_call>\n"
    '{"name": "set_reminder", "arguments": {"content": "提醒内容", "remind_time": "YYYY-MM-DD HH:mm"}}\n'
    "</tool_call>；日期必须换算成具体日期，不允许输出相对日期。"
)

WEEK_CN = "一二三四五六日"

TITLES = [
    "牙医复诊", "家长会", "健身私教课", "部门例会", "交实验报告", "取体检报告", "朋友聚餐",
    "驾照科目二", "钢琴课", "产品评审会", "班级值日", "社团活动", "口腔洗牙", "面试",
    "接机", "还书", "续费会员", "缴纳水电费", "晨跑", "游泳课", "英语角", "志愿活动",
    "小组讨论", "看电影", "看房", "理发", "体检", "买药", "瑜伽课", "编程课",
]
CONTENTS = [
    "吃药", "交报告", "给妈妈打电话", "取快递", "还信用卡", "喝水", "站起来活动",
    "预约挂号", "买牛奶", "交作业", "打卡", "喂猫", "浇花", "备份照片", "充电",
    "回邮件", "确认会议室", "下载课件", "带门禁卡", "订车票", "交班费", "量血压",
    "练听力", "背单词", "整理错题", "给老师发消息", "取准考证", "订外卖", "看牙", "续借图书",
]
LOCATIONS = [
    "口腔医院", "学校", "公司", "第一人民医院", "健身房", "星巴克国贸店", "图书馆",
    "地铁站A口", "商场三楼", "操场看台", "社区中心", "咖啡店", "游泳馆", "家里", "门诊部四楼",
]
NOTES = [
    "带成绩单", "提前十分钟到", "记得空腹", "穿校服", "带上次的检查报告", "线上会议提前测麦克风",
    "别迟到", "带身份证", "带水杯", "结束后回电话", "", "", "", "",
]

# (文本, 时, 分)；12 小时制已折算成 24 小时制
TIME_SLOTS = [
    ("凌晨一点", 1, 0), ("凌晨两点半", 2, 30), ("凌晨四点", 4, 0),
    ("早上六点半", 6, 30), ("早上七点", 7, 0), ("早上八点", 8, 0), ("早上八点半", 8, 30),
    ("上午九点", 9, 0), ("上午九点半", 9, 30), ("上午十点一刻", 10, 15),
    ("上午十一点", 11, 0), ("上午十一点半", 11, 30),
    ("中午十二点", 12, 0),
    ("下午一点", 13, 0), ("下午一点半", 13, 30), ("下午两点", 14, 0), ("下午两点半", 14, 30),
    ("下午三点", 15, 0), ("下午三点一刻", 15, 15), ("下午三点半", 15, 30),
    ("下午三点三刻", 15, 45), ("下午四点", 16, 0), ("下午四点半", 16, 30), ("下午五点", 17, 0),
    ("傍晚六点", 18, 0), ("傍晚六点半", 18, 30),
    ("晚上七点", 19, 0), ("晚上七点半", 19, 30), ("晚上八点", 20, 0), ("晚上八点半", 20, 30),
    ("晚上九点", 21, 0), ("晚上九点一刻", 21, 15), ("晚上十点", 22, 0),
]
EVENING_SLOTS = [s for s in TIME_SLOTS if s[1] >= 19]
MORNING_SLOTS = [s for s in TIME_SLOTS if 6 <= s[1] <= 9]

DURATIONS = [
    ("十五分钟", 15), ("半小时", 30), ("四十五分钟", 45), ("一小时", 60),
    ("一个半小时", 90), ("两小时", 120), ("两个半小时", 150), ("三小时", 180), ("90分钟", 90),
]
DEFAULT_DURATION = 60


def next_week_date(today, wd):
    monday = today - timedelta(days=today.weekday())
    return monday + timedelta(days=7 + wd)


def this_week_date(today, wd):
    monday = today - timedelta(days=today.weekday())
    return monday + timedelta(days=wd)


def rand_today(rng):
    year = rng.choices([2026, 2027, 2028], weights=[70, 25, 5])[0]
    month = rng.randint(1, 12)
    day = rng.randint(1, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def date_expr(rng, today):
    """返回 (文本, 目标日期)。只生成今天及以后的目标，避免过去的日程。"""
    r = rng.random()
    if r < 0.24:
        wd = rng.randrange(7)
        return f"下周{WEEK_CN[wd]}", next_week_date(today, wd)
    if r < 0.34:
        wd = rng.randrange(7)
        monday = today - timedelta(days=today.weekday())
        return f"下下周{WEEK_CN[wd]}", monday + timedelta(days=14 + wd)
    if r < 0.46:
        wd = rng.randint(today.weekday(), 6)
        prefix = rng.choice(["这周", "本周"])
        return f"{prefix}{WEEK_CN[wd]}", this_week_date(today, wd)
    if r < 0.56:
        offset = rng.choices([0, 1, 2, 3], weights=[15, 45, 25, 15])[0]
        text = {0: "今天", 1: "明天", 2: "后天", 3: "大后天"}[offset]
        return text, today + timedelta(days=offset)
    if r < 0.64:
        n = rng.randint(3, 13)
        return f"{n}天后", today + timedelta(days=n)
    if r < 0.83:
        target = today + timedelta(days=rng.randint(1, 330))
        suffix = rng.choice(["日", "号"])
        return f"{target.month}月{target.day}{suffix}", target
    year = today.year + (1 if today.month == 12 else 0)
    month = 1 if today.month == 12 else today.month + 1
    day = rng.randint(1, 28)
    return f"下个月{day}号", date(year, month, day)


def combined_expr(rng, today):
    """今晚/明早/明晚：日期与时间写在同一个短语里。"""
    kind, slots, offset = rng.choice([
        ("今晚", EVENING_SLOTS, 0),
        ("明早", MORNING_SLOTS, 1),
        ("明晚", EVENING_SLOTS, 1),
    ])
    text, hh, mm = rng.choice(slots)
    return f"{kind}{clock_text(hh, mm)}", today + timedelta(days=offset), hh, mm


def fmt_dt(d, hh, mm):
    return f"{d.year:04d}-{d.month:02d}-{d.day:02d} {hh:02d}:{mm:02d}"


def today_text(d):
    return f"今天是{d.year}年{d.month:02d}月{d.day:02d}日。"


def clock_text(hh, mm):
    """24 小时制转钟点短语（不带时段前缀）。"""
    h12 = hh - 12 if hh > 12 else hh
    hour_cn = {0: "十二", 1: "一", 2: "二", 3: "三", 4: "四", 5: "五", 6: "六",
               7: "七", 8: "八", 9: "九", 10: "十", 11: "十一", 12: "十二"}[h12]
    if mm == 0:
        return f"{hour_cn}点"
    if mm == 30:
        return f"{hour_cn}点半"
    if mm == 15:
        return f"{hour_cn}点一刻"
    if mm == 45:
        return f"{hour_cn}点三刻"
    return f"{hour_cn}点{mm}分"


def time_text(hh, mm):
    """24 小时制转完整时间短语（带时段前缀）。"""
    period = "凌晨" if hh < 5 else "早上" if hh < 9 else "上午" if hh < 12 else "中午" if hh == 12 else "下午" if hh < 18 else "晚上"
    return period + clock_text(hh, mm)


def wrap(name, args):
    return "<tool_call>\n" + json.dumps({"name": name, "arguments": args}, ensure_ascii=False) + "\n</tool_call>"


def make_calendar(rng, today, force=None, fixed_time=None):
    if force is None and fixed_time is None and rng.random() < 0.18:
        dt_text, target, hh, mm = combined_expr(rng, today)
    else:
        dt_text, target = force or date_expr(rng, today)
        if fixed_time is None:
            slot_text, hh, mm = rng.choice(TIME_SLOTS)
        else:
            hh, mm = fixed_time
            slot_text = time_text(hh, mm)
        dt_text = dt_text + slot_text
    start = datetime(target.year, target.month, target.day, hh, mm)
    if rng.random() < 0.2:
        dur_text, dur_min = None, DEFAULT_DURATION
    else:
        dur_text, dur_min = rng.choice(DURATIONS)
    end = start + timedelta(minutes=dur_min)
    title = rng.choice(TITLES)
    loc = rng.choice(LOCATIONS) if rng.random() < 0.7 else ""
    note = rng.choice(NOTES) if rng.random() < 0.5 else ""

    parts = [f"添加日历事件：{title}，{dt_text}"]
    if dur_text:
        parts.append(f"时长{dur_text}")
    if loc:
        parts.append(f"地点在{loc}")
    if note:
        parts.append(f"备注：{note}")
    user = "派单：" + "，".join(parts) + "。" + today_text(today)
    args = {"title": title, "start_time": fmt_dt(start.date(), start.hour, start.minute),
            "end_time": fmt_dt(end.date(), end.hour, end.minute), "location": loc, "note": note}
    return {"task_type": "calendar", "source": "rule", "messages": [
        {"role": "system", "content": SYSTEM_CAL},
        {"role": "user", "content": user},
        {"role": "assistant", "content": wrap("add_calendar_event", args)}]}


def make_reminder(rng, today, force=None, fixed_time=None):
    if force is None and fixed_time is None and rng.random() < 0.18:
        dt_text, target, hh, mm = combined_expr(rng, today)
    else:
        dt_text, target = force or date_expr(rng, today)
        if fixed_time is None:
            slot_text, hh, mm = rng.choice(TIME_SLOTS)
        else:
            hh, mm = fixed_time
            slot_text = time_text(hh, mm)
        dt_text = dt_text + slot_text
    content = rng.choice(CONTENTS)
    user = f"派单：设置提醒：{content}，{dt_text}。" + today_text(today)
    args = {"content": content, "remind_time": fmt_dt(target, hh, mm)}
    return {"task_type": "reminder", "source": "rule", "messages": [
        {"role": "system", "content": SYSTEM_REM},
        {"role": "user", "content": user},
        {"role": "assistant", "content": wrap("set_reminder", args)}]}


def gen_samples(rng, n_cal, n_rem):
    out, seen = [], set()

    def add(sample):
        user = sample["messages"][1]["content"]
        if user in seen:
            return False
        seen.add(user)
        out.append(sample)
        return True

    cal = rem = guard = 0
    while cal < n_cal and guard < n_cal * 30:
        guard += 1
        if add(make_calendar(rng, rand_today(rng))):
            cal += 1
    guard = 0
    while rem < n_rem and guard < n_rem * 30:
        guard += 1
        if add(make_reminder(rng, rand_today(rng))):
            rem += 1
    assert len(out) == n_cal + n_rem, f"生成不足: {len(out)}"
    return out


def tool_name(sample):
    a = next(m["content"] for m in sample["messages"] if m["role"] == "assistant")
    if "add_calendar_event" in a:
        return "calendar"
    if "set_reminder" in a:
        return "reminder"
    if "translate_text" in a:
        return "translate"
    return "summary"


def load_replay(path, counts, rng):
    buckets = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            buckets.setdefault(tool_name(r), []).append(r)
    out = []
    for name, n in counts.items():
        pool = buckets.get(name, [])
        rng.shuffle(pool)
        out.extend(pool[:n])
    return out


def build_eval(rng):
    """60 题 held-out：固定基准日覆盖七个星期几，重点下周X。"""
    cases = []

    def add(cat, sample, expect):
        cases.append({"cat": cat, "task_type": sample["task_type"],
                      "messages": sample["messages"][:2], "expect": expect})

    # 1) 下周X：7 个基准日 × 各 2 个星期几
    bases = [date(2026, 11, 6), date(2026, 11, 9), date(2026, 11, 8),
             date(2026, 11, 4), date(2026, 11, 5), date(2026, 11, 7), date(2026, 11, 10)]
    for i, base in enumerate(bases):
        for wd in ((i * 2) % 7, (i * 2 + 3) % 7):
            target = next_week_date(base, wd)
            s = make_calendar(rng, base, force=(f"下周{WEEK_CN[wd]}", target)) if i % 2 == 0 \
                else make_reminder(rng, base, force=(f"下周{WEEK_CN[wd]}", target))
            add("下周X", s, s["messages"][2]["content"])

    # 1b) 下周X 跨年/跨月补充
    for base, wd in [(date(2027, 1, 1), 0), (date(2027, 1, 1), 5),
                     (date(2027, 6, 30), 2), (date(2027, 6, 30), 6),
                     (date(2027, 12, 31), 1), (date(2027, 12, 31), 4),
                     (date(2028, 2, 28), 0), (date(2028, 2, 28), 3)]:
        target = next_week_date(base, wd)
        s = make_reminder(rng, base, force=(f"下周{WEEK_CN[wd]}", target))
        add("下周X", s, s["messages"][2]["content"])

    # 2) 这周X（只取今天及以后）
    for base, wd in [(date(2026, 11, 6), 4), (date(2026, 11, 6), 5), (date(2026, 11, 6), 6),
                     (date(2026, 11, 4), 2), (date(2026, 11, 9), 0), (date(2026, 12, 31), 3),
                     (date(2027, 1, 1), 4), (date(2026, 11, 8), 6)]:
        target = this_week_date(base, wd)
        s = make_calendar(rng, base, force=(f"这周{WEEK_CN[wd]}", target))
        add("这周X", s, s["messages"][2]["content"])

    # 3) 相对：明天/后天/大后天/今晚/明早/明晚
    for base, text, offset, kind in [
        (date(2026, 11, 6), "明天", 1, "cal"), (date(2026, 11, 6), "后天", 2, "rem"),
        (date(2026, 11, 6), "大后天", 3, "cal"), (date(2026, 12, 31), "明天", 1, "cal"),
        (date(2026, 11, 6), "今晚", 0, "rem"), (date(2026, 11, 6), "明早", 1, "rem"),
        (date(2026, 11, 6), "明晚", 1, "cal"), (date(2027, 1, 1), "今晚", 0, "cal"),
    ]:
        target = base + timedelta(days=offset)
        if text in ("今晚", "明早", "明晚"):
            slots = MORNING_SLOTS if text == "明早" else EVENING_SLOTS
            _, hh, mm = rng.choice(slots)
            s = (make_calendar if kind == "cal" else make_reminder)(
                rng, base, force=("", target), fixed_time=(hh, mm))
            # force 文本为空会拼出 "点"，改用显式时间短语重建
            if kind == "cal":
                title = rng.choice(TITLES)
                user = f"派单：添加日历事件：{title}，{text}{time_text(hh, mm)}，时长一小时。" + today_text(base)
                start = datetime(target.year, target.month, target.day, hh, mm)
                end = start + timedelta(minutes=60)
                args = {"title": title, "start_time": fmt_dt(target, hh, mm),
                        "end_time": fmt_dt(end.date(), end.hour, end.minute), "location": "", "note": ""}
                s = {"task_type": "calendar", "messages": [
                    {"role": "system", "content": SYSTEM_CAL},
                    {"role": "user", "content": user},
                    {"role": "assistant", "content": wrap("add_calendar_event", args)}]}
            else:
                content = rng.choice(CONTENTS)
                user = f"派单：设置提醒：{content}，{text}{time_text(hh, mm)}。" + today_text(base)
                s = {"task_type": "reminder", "messages": [
                    {"role": "system", "content": SYSTEM_REM},
                    {"role": "user", "content": user},
                    {"role": "assistant", "content": wrap("set_reminder", {
                        "content": content, "remind_time": fmt_dt(target, hh, mm)})}]}
            add("相对", s, s["messages"][2]["content"])
        else:
            s = (make_calendar if kind == "cal" else make_reminder)(rng, base, force=(text, target))
            add("相对", s, s["messages"][2]["content"])

    # 4) 绝对日期
    for base, target, suffix in [
        (date(2026, 11, 6), date(2026, 11, 20), "日"), (date(2026, 11, 6), date(2026, 12, 3), "号"),
        (date(2026, 12, 20), date(2027, 1, 5), "日"), (date(2026, 11, 6), date(2027, 3, 1), "号"),
        (date(2027, 2, 1), date(2028, 2, 29), "日"), (date(2026, 11, 6), date(2026, 11, 8), "日"),
        (date(2026, 11, 6), date(2027, 6, 15), "号"), (date(2027, 12, 30), date(2028, 1, 2), "日"),
    ]:
        s = make_calendar(rng, base, force=(f"{target.month}月{target.day}{suffix}", target))
        add("绝对", s, s["messages"][2]["content"])

    # 5) 下个月 D 号
    for base, day in [(date(2026, 11, 6), 5), (date(2026, 12, 15), 1), (date(2027, 1, 31), 28),
                      (date(2026, 11, 6), 20), (date(2027, 6, 30), 15), (date(2026, 11, 6), 1)]:
        year = base.year + (1 if base.month == 12 else 0)
        month = 1 if base.month == 12 else base.month + 1
        target = date(year, month, day)
        s = make_reminder(rng, base, force=(f"下个月{day}号", target))
        add("下个月", s, s["messages"][2]["content"])

    # 6) 边界：月底/年底/跨午夜/闰日
    for base, text, target, hh, mm in [
        (date(2026, 11, 29), "下周一", next_week_date(date(2026, 11, 29), 0), 23, 30),
        (date(2026, 12, 30), "后天", date(2027, 1, 1), 20, 0),
        (date(2026, 12, 31), "明天", date(2027, 1, 1), 7, 0),
        (date(2028, 2, 28), "明天", date(2028, 2, 29), 9, 0),
        (date(2026, 11, 6), "这周日", this_week_date(date(2026, 11, 6), 6), 22, 30),
        (date(2026, 11, 6), "下周日", next_week_date(date(2026, 11, 6), 6), 19, 0),
        (date(2027, 1, 31), "下个月1号", date(2027, 2, 1), 8, 0),
        (date(2026, 11, 30), "明天", date(2026, 12, 1), 6, 30),
    ]:
        s = make_calendar(rng, base, force=(text, target), fixed_time=(hh, mm))
        add("边界", s, s["messages"][2]["content"])

    return cases


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--replay", default="train/synthesize/cloud_sft20/worker_sft20.jsonl")
    ap.add_argument("--outdir", default="train/synthesize/date_sft20b")
    ap.add_argument("--eval-out", default="train/eval/date_worker_eval.json")
    ap.add_argument("--seed", type=int, default=20261106)
    args = ap.parse_args()

    rng = random.Random(args.seed)
    samples = gen_samples(rng, 2400, 1600)
    replay = load_replay(args.replay, {"translate": 400, "summary": 400,
                                       "calendar": 100, "reminder": 100}, rng)
    train_seen = {s["messages"][1]["content"] for s in samples}
    replay = [r for r in replay if r["messages"][1]["content"] not in train_seen]
    all_samples = samples + replay
    rng.shuffle(all_samples)

    n_val = max(1, int(len(all_samples) * 0.02))
    val, train = all_samples[:n_val], all_samples[n_val:]

    os.makedirs(args.outdir, exist_ok=True)
    with open(os.path.join(args.outdir, "train.jsonl"), "w", encoding="utf-8") as f:
        for s in train:
            f.write(json.dumps(s, ensure_ascii=False) + "\n")
    with open(os.path.join(args.outdir, "val.jsonl"), "w", encoding="utf-8") as f:
        for s in val:
            f.write(json.dumps(s, ensure_ascii=False) + "\n")

    eval_rng = random.Random(args.seed + 1)
    eval_cases = build_eval(eval_rng)
    train_users = {s["messages"][1]["content"] for s in all_samples}
    eval_cases = [c for c in eval_cases if c["messages"][1]["content"] not in train_users]
    with open(args.eval_out, "w", encoding="utf-8") as f:
        json.dump(eval_cases, f, ensure_ascii=False, indent=1)

    cnt = Counter(tool_name(s) for s in all_samples)
    report = [
        f"日期样本 {len(samples)} + 回放 {len(replay)} = {len(all_samples)}",
        f"train {len(train)} / val {len(val)}",
        f"工具分布 {dict(cnt)}",
        f"评测集 {len(eval_cases)} 题（与训练话术查重后）",
        f"评测类别 {dict(Counter(c['cat'] for c in eval_cases))}",
    ]
    with open(os.path.join(args.outdir, "report.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(report) + "\n")
    print("\n".join(report))


if __name__ == "__main__":
    main()
