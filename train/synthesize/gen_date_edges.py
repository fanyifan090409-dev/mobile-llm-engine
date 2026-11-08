#!/usr/bin/env python3
"""SFT20d 工人日期边界补训：闰日 / 跨年 / 跨月 / 小时进位。

SFT20c 剩余 4/60 失败集中在边界（闰日、跨年、小时进位）。本生成器
专门造这些边界 + 从 SFT20c 训练集回放，保持日期表格式与工种分布。

用法：
  python3 gen_date_edges.py --replay train/synthesize/date_sft20c/train.jsonl \
      --outdir train/synthesize/date_sft20d \
      --eval-out train/eval/date_worker_edges_eval.json
"""
import argparse
import json
import os
import random
import sys
from datetime import date, datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gen_date_worker as g
from add_date_table import week_table

SCENARIOS = [
    # (今天, 日期短语, 目标日期) —— 闰日
    (date(2028, 2, 28), "明天", date(2028, 2, 29)),
    (date(2028, 2, 28), "后天", date(2028, 3, 1)),
    (date(2028, 2, 29), "今天", date(2028, 2, 29)),
    (date(2028, 2, 29), "明天", date(2028, 3, 1)),
    (date(2028, 2, 29), "后天", date(2028, 3, 2)),
    (date(2027, 2, 28), "明天", date(2027, 3, 1)),
    (date(2027, 2, 27), "后天", date(2027, 3, 1)),
    (date(2028, 3, 1), "今天", date(2028, 3, 1)),
    # 跨年 / 跨月
    (date(2026, 12, 31), "今天", date(2026, 12, 31)),
    (date(2026, 12, 31), "明天", date(2027, 1, 1)),
    (date(2026, 12, 31), "后天", date(2027, 1, 2)),
    (date(2026, 12, 31), "下周一", date(2027, 1, 4)),
    (date(2026, 12, 31), "下个月1号", date(2027, 1, 1)),
    (date(2027, 1, 1), "今天", date(2027, 1, 1)),
    (date(2027, 1, 1), "下周一", date(2027, 1, 4)),
    (date(2027, 12, 31), "明天", date(2028, 1, 1)),
    (date(2027, 12, 31), "下周一", date(2028, 1, 3)),
    (date(2027, 1, 31), "明天", date(2027, 2, 1)),
    (date(2027, 1, 31), "下个月1号", date(2027, 2, 1)),
    (date(2026, 1, 31), "明天", date(2026, 2, 1)),
    (date(2026, 11, 30), "明天", date(2026, 12, 1)),
    (date(2026, 11, 29), "下周一", date(2026, 11, 30)),
    # 小时进位：结束时间跨日（开始时间仍在目标日）
    (date(2026, 11, 8), "今天", date(2026, 11, 8)),
    (date(2026, 11, 8), "明天", date(2026, 11, 9)),
    (date(2026, 12, 31), "今天", date(2026, 12, 31)),
    (date(2028, 2, 28), "今天", date(2028, 2, 28)),
    (date(2028, 2, 29), "今天", date(2028, 2, 29)),
]

# 覆盖 22:30 之后与凌晨，专门压小时进位
EDGE_TIMES = [(7, 0), (9, 30), (15, 0), (22, 30), (23, 0), (23, 30), (23, 59), (0, 15)]
EDGE_DURATIONS = [("十五分钟", 15), ("四十五分钟", 45),
                  ("一个半小时", 90), ("两小时", 120)]


def calendar_sample(rng, base, phrase, target, hh, mm, dur_text, dur_min):
    start = datetime(target.year, target.month, target.day, hh, mm)
    end = start + timedelta(minutes=dur_min)
    title = rng.choice(g.TITLES)
    loc = rng.choice(g.LOCATIONS) if rng.random() < 0.5 else ""
    note = rng.choice(g.NOTES) if rng.random() < 0.3 else ""
    parts = [f"添加日历事件：{title}，{phrase}{g.time_text(hh, mm)}，时长{dur_text}"]
    if loc:
        parts.append(f"地点在{loc}")
    if note:
        parts.append(f"备注：{note}")
    user = "派单：" + "，".join(parts) + "。" + g.today_text(base) + week_table(base)
    args = {
        "title": title,
        "start_time": g.fmt_dt(start.date(), start.hour, start.minute),
        "end_time": g.fmt_dt(end.date(), end.hour, end.minute),
        "location": loc, "note": note,
    }
    return {"task_type": "calendar", "source": "rule-edge", "messages": [
        {"role": "system", "content": g.SYSTEM_CAL},
        {"role": "user", "content": user},
        {"role": "assistant", "content": g.wrap("add_calendar_event", args)}]}


def reminder_sample(rng, base, phrase, target, hh, mm):
    content = rng.choice(g.CONTENTS)
    user = f"派单：设置提醒：{content}，{phrase}{g.time_text(hh, mm)}。" \
           + g.today_text(base) + week_table(base)
    args = {"content": content, "remind_time": g.fmt_dt(target, hh, mm)}
    return {"task_type": "reminder", "source": "rule-edge", "messages": [
        {"role": "system", "content": g.SYSTEM_REM},
        {"role": "user", "content": user},
        {"role": "assistant", "content": g.wrap("set_reminder", args)}]}


def gen_edges(rng):
    out, seen = [], set()

    def add(sample):
        user = sample["messages"][1]["content"]
        if user in seen:
            return False
        seen.add(user)
        out.append(sample)
        return True

    for base, phrase, target in SCENARIOS:
        for _ in range(3):
            for hh, mm in EDGE_TIMES:
                dur_text, dur_min = rng.choice(EDGE_DURATIONS)
                add(calendar_sample(rng, base, phrase, target, hh, mm, dur_text, dur_min))
            for hh, mm in rng.sample(EDGE_TIMES, 3):
                add(reminder_sample(rng, base, phrase, target, hh, mm))
    return out


def load_replay(path, n, rng):
    rows = [json.loads(line) for line in open(path, encoding="utf-8")]
    rng.shuffle(rows)
    return rows[:n]


def build_eval(rng):
    cases = []

    def add(cat, sample):
        cases.append({"cat": cat, "task_type": sample["task_type"],
                      "messages": sample["messages"][:2],
                      "expect": sample["messages"][2]["content"]})

    # 闰日
    add("闰日", calendar_sample(rng, date(2028, 2, 28), "明天", date(2028, 2, 29),
                                9, 0, "一小时", 60))
    add("闰日", calendar_sample(rng, date(2028, 2, 29), "明天", date(2028, 3, 1),
                                23, 30, "四十五分钟", 45))
    add("闰日", reminder_sample(rng, date(2027, 2, 28), "明天", date(2027, 3, 1), 9, 0))
    add("闰日", calendar_sample(rng, date(2028, 2, 29), "后天", date(2028, 3, 2),
                                23, 0, "两小时", 120))
    # 跨年
    add("跨年", calendar_sample(rng, date(2026, 12, 31), "明天", date(2027, 1, 1),
                                9, 0, "一小时", 60))
    add("跨年", reminder_sample(rng, date(2026, 12, 31), "下周一", date(2027, 1, 4), 10, 0))
    add("跨年", calendar_sample(rng, date(2026, 12, 31), "下个月1号", date(2027, 1, 1),
                                23, 30, "四十五分钟", 45))
    add("跨年", reminder_sample(rng, date(2027, 12, 31), "下周一", date(2028, 1, 3), 10, 0))
    # 跨月 / 小时进位
    add("跨月", calendar_sample(rng, date(2026, 1, 31), "明天", date(2026, 2, 1),
                                23, 30, "四十五分钟", 45))
    add("跨月", calendar_sample(rng, date(2026, 11, 30), "明天", date(2026, 12, 1),
                                6, 30, "一小时", 60))
    add("小时进位", calendar_sample(rng, date(2026, 11, 8), "今天", date(2026, 11, 8),
                                   23, 30, "四十五分钟", 45))
    add("小时进位", calendar_sample(rng, date(2026, 11, 8), "今天", date(2026, 11, 8),
                                   23, 0, "两小时", 120))
    add("小时进位", calendar_sample(rng, date(2026, 11, 8), "明天", date(2026, 11, 9),
                                   22, 30, "一个半小时", 90))
    add("小时进位", calendar_sample(rng, date(2026, 11, 8), "今天", date(2026, 11, 8),
                                   23, 59, "十五分钟", 15))
    add("小时进位", calendar_sample(rng, date(2028, 2, 28), "今天", date(2028, 2, 28),
                                   23, 30, "四十五分钟", 45))
    add("小时进位", calendar_sample(rng, date(2028, 2, 29), "今天", date(2028, 2, 29),
                                   23, 30, "四十五分钟", 45))
    return cases


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--replay", default="train/synthesize/date_sft20c/train.jsonl")
    ap.add_argument("--outdir", default="train/synthesize/date_sft20d")
    ap.add_argument("--eval-out", default="train/eval/date_worker_edges_eval.json")
    ap.add_argument("--seed", type=int, default=20261108)
    args = ap.parse_args()

    rng = random.Random(args.seed)
    edges = gen_edges(rng)
    replay = load_replay(args.replay, 1400, rng)
    all_samples = edges + replay
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
    cases = build_eval(eval_rng)
    train_users = {s["messages"][1]["content"] for s in all_samples}
    cases = [c for c in cases if c["messages"][1]["content"] not in train_users]
    with open(args.eval_out, "w", encoding="utf-8") as f:
        json.dump(cases, f, ensure_ascii=False, indent=1)

    from collections import Counter
    print(f"边界样本 {len(edges)} + 回放 {len(replay)} = {len(all_samples)}")
    print(f"train {len(train)} / val {len(val)}")
    print("工具分布", dict(Counter(g.tool_name(s) for s in all_samples)))
    print("边界评测", len(cases), "题", dict(Counter(c["cat"] for c in cases)))


if __name__ == "__main__":
    main()
