#!/usr/bin/env python3
"""质检合成 SFT 数据：类别分布 / 长度分布 / 重复率 / 工具调用解析率 + 抽样人工检查。

用法：python3 qc_sft.py --dir data/sft --samples 5
"""
import argparse
import glob
import hashlib
import json
import os
import random
from collections import Counter

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="data/sft")
    ap.add_argument("--samples", type=int, default=5)
    args = ap.parse_args()

    files = sorted(glob.glob(os.path.join(args.dir, "*.jsonl")))
    if not files:
        print("没有找到 jsonl 文件")
        return
    total = 0
    hashes = set()
    cat_counts = Counter()
    len_counter = Counter()
    sched_ok = sched_total = 0
    all_recs = []
    for fn in files:
        cat = os.path.basename(fn).replace(".jsonl", "")
        with open(fn, encoding="utf-8") as f:
            for line in f:
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                total += 1
                cat_counts[cat] += 1
                h = rec.get("hash") or hashlib.sha256(line.encode()).hexdigest()
                hashes.add(h)
                msgs = rec.get("messages") or []
                text = "".join(str(m.get("content") or "") for m in msgs)
                len_counter[min(len(text) // 200, 15)] += 1
                if cat == "schedule":
                    sched_total += 1
                    # 数据用 Qwen3 文本 XML 工具调用（content 内嵌 <tool_call>），非 OpenAI tool_calls 字段
                    if any(m.get("role") == "assistant" and m.get("content")
                           and "<tool_call>" in str(m.get("content")) for m in msgs):
                        sched_ok += 1
                all_recs.append(rec)

    print(f"总样本 {total} | 唯一 hash {len(hashes)} | 重复率 {(1 - len(hashes)/max(total,1)):.1%}")
    for c, n in cat_counts.most_common():
        print(f"  {c}: {n}")
    print("长度分布(每200字一档):", dict(sorted(len_counter.items())))
    if sched_total:
        print(f"schedule 工具调用解析率: {sched_ok}/{sched_total} = {sched_ok/sched_total:.1%}")

    rng = random.Random(42)
    n_pick = min(args.samples * len(files), total)
    for rec in rng.sample(all_recs, n_pick):
        print("-" * 60)
        for m in rec["messages"]:
            c = m.get("content")
            if c:
                print(f"[{m['role']}] {str(c)[:180]}")
            elif m.get("tool_calls"):
                print(f"[{m['role']}] tool_call: {str(m['tool_calls'])[:180]}")

if __name__ == "__main__":
    main()
