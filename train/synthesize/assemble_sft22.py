#!/usr/bin/env python3
"""SFT22 合并数据：数学纠错 2,013 + 学术回放 1,000 + 派单回放 1,500 + 反问回放 600。

在训练机跑（读 data/ 下的既有数据）：
  python3 assemble_sft22.py --outdir data/train_sft22
"""
import argparse
import json
import os
import random
import re

ROOT = "/home/ubuntu/llm-mobile"
rng = random.Random(20261108)
TIME_RE = re.compile(r"今天|明天|后天|大后天|周[一二三四五六日天]|星期[一二三四五六日天]|"
                     r"下个?月|\d{1,2}\s*月\s*\d{1,2}\s*[日号]|\d{1,2}\s*[点时]|"
                     r"上午|下午|晚上|中午|早上|傍晚|月底|月初")
AMBIG_RE = re.compile(r"具体时间我发你|时间还没定|回头再说|看房|夜跑|那个会|刚才那个|"
                      r"帮我约个事|帮我安排一下$|提醒我一下")


def read_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(l) for l in f]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--outdir", default="data/train_sft22")
    args = ap.parse_args()
    outdir = os.path.join(ROOT, args.outdir)
    os.makedirs(outdir, exist_ok=True)

    math_rows = read_jsonl(os.path.join(ROOT, "data/train_sft22_math/train.jsonl"))
    rng.shuffle(math_rows)

    # 学术回放：四类各 250
    academic = []
    for cat in ("ap_calc", "precalc", "ap_stats", "ielts"):
        rows = read_jsonl(os.path.join(ROOT, f"data/sft19/{cat}.jsonl"))
        rng.shuffle(rows)
        academic += rows[:250]

    # 派单回放：单轮 1,200 + 多轮 300
    leader = read_jsonl(os.path.join(ROOT, "data/train_sft20_leader/train.jsonl"))
    def dispatch_ok(r):
        u = r["messages"][1]["content"]
        t = r.get("task_type")
        if AMBIG_RE.search(u):
            return False
        if t in ("calendar", "reminder"):
            return bool(TIME_RE.search(u))
        if t == "translate":
            return "翻译" in u
        if t == "summary":
            return any(k in u for k in ("总结", "摘要", "缩成", "概括", "压缩"))
        if t == "mixed":
            return bool(TIME_RE.search(u)) and ("翻译" in u or "总结" in u)
        return False
    pool = [r for r in leader if dispatch_ok(r)]
    rng.shuffle(pool)
    single = [{"messages": r["messages"][:3]} for r in pool if len(r["messages"]) >= 3
              and "<tool_call>" in r["messages"][2]["content"]][:1200]
    multi = [{"messages": r["messages"]} for r in pool if len(r["messages"]) >= 4][:300]

    # 反问回放 600
    clar = [r for r in read_jsonl(os.path.join(ROOT, "data/train_sft21b_leader/train.jsonl"))
            if r.get("task_type") == "clarify"]
    rng.shuffle(clar)
    clar = clar[:600]

    fix_rows = read_jsonl(os.path.join(ROOT, "data/train_sft22_math/dispatch_fix_sft22.jsonl"))
    rows = math_rows + academic + single + multi + clar + fix_rows
    rng.shuffle(rows)
    n = max(1, len(rows) // 10)
    val, train = rows[:n], rows[n:]
    for name, data in (("train", train), ("val", val)):
        with open(os.path.join(outdir, f"{name}.jsonl"), "w", encoding="utf-8") as f:
            for r in data:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    stats = {"math": len(math_rows), "academic": len(academic),
             "dispatch_single": len(single), "dispatch_multi": len(multi),
             "clarify": len(clar), "dispatch_fix": len(fix_rows), "total": len(rows),
             "train": len(train), "val": len(val)}
    with open(os.path.join(outdir, "stats.json"), "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)
    print(json.dumps(stats, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
