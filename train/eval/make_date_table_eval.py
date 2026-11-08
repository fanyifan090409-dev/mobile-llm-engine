#!/usr/bin/env python3
"""给日期评测集注入「本周/下周日期表」，验证 0.6B 能否靠抄表代替心算。"""
import json
import re
import sys
from datetime import date, timedelta

WEEK = "一二三四五六日"
SRC = "train/eval/date_worker_eval.json"
DST = "train/eval/date_worker_eval_table.json"


def table(today):
    monday = today - timedelta(days=today.weekday())
    parts = []
    for label, offset in (("本周", 0), ("下周", 7), ("下下周", 14)):
        seg = "，".join(
            f"{label}周{WEEK[i]}={monday + timedelta(days=offset + i):%Y-%m-%d}" for i in range(7))
        parts.append(seg)
    return "日期参考：" + "；".join(parts) + "。"


def main():
    cases = json.load(open(SRC, encoding="utf-8"))
    for c in cases:
        user = c["messages"][1]["content"]
        today = date(*map(int, re.search(r"今天是(\d{4})年(\d{2})月(\d{2})日。", user).groups()))
        c["messages"][1]["content"] = user + table(today)
    json.dump(cases, open(DST, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"wrote {DST}: {len(cases)} cases")
    print(cases[0]["messages"][1]["content"])


if __name__ == "__main__":
    main()
