#!/usr/bin/env python3
"""SFT20c：给日历/提醒样本追加「本周/下周/下下周」日期表，训练 0.6B 抄表。

翻车记录：零样本直接追加表格时，SFT20b 会把整段输入复读一遍（emit 1/60），
所以表格格式必须进训练分布；translate/summary 不加表（生产也不会加）。
"""
import json
import os
import random
import re
from datetime import date, timedelta

WEEK = "一二三四五六日"
DATE_RE = re.compile(r"今天是(\d{4})年(\d{2})月(\d{2})日。")


def week_table(today):
    monday = today - timedelta(days=today.weekday())
    parts = []
    for label, offset in (("本周", 0), ("下周", 7), ("下下周", 14)):
        seg = "，".join(
            f"{label}周{WEEK[i]}={monday + timedelta(days=offset + i):%Y-%m-%d}" for i in range(7))
        parts.append(seg)
    return "日期参考：" + "；".join(parts) + "。"


def main():
    src = "train/synthesize/date_sft20b"
    dst = "train/synthesize/date_sft20c"
    os.makedirs(dst, exist_ok=True)
    counts = {"train": 0, "val": 0, "appended": 0}
    for split in ("train", "val"):
        out = []
        for line in open(os.path.join(src, f"{split}.jsonl"), encoding="utf-8"):
            r = json.loads(line)
            if r.get("task_type") in ("calendar", "reminder"):
                user = r["messages"][1]["content"]
                m = DATE_RE.search(user)
                if not m:
                    raise SystemExit(f"缺今天是: {user[:80]}")
                today = date(*map(int, m.groups()))
                r["messages"][1]["content"] = user + week_table(today)
                counts["appended"] += 1
            out.append(r)
        if split == "train":
            # 日期样本占 8 成时 SFT20b 把摘要格式带崩（2/2 失败）；translate/summary 过采样 3 倍保住格式
            extras = [r for r in out if r.get("task_type") not in ("calendar", "reminder")]
            out = out + extras * 2
            random.Random(20261106).shuffle(out)
        with open(os.path.join(dst, f"{split}.jsonl"), "w", encoding="utf-8") as f:
            for r in out:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        counts[split] = len(out)
    print(f"train {counts['train']} / val {counts['val']}，加表样本 {counts['appended']}")
    print(open(os.path.join(dst, "train.jsonl"), encoding="utf-8").readline()[:500])


if __name__ == "__main__":
    main()
