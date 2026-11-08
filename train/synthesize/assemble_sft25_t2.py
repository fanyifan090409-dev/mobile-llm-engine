#!/usr/bin/env python3
"""SFT25 拼装：清洗后的雅思 T2 + 学术回放 700 + 领队行为回放 300。

用法（训练机）：
  python3 assemble_sft25_t2.py --outdir data/train_sft25_t2
"""
import argparse
import json
import os
import random

ROOT = "/home/ubuntu/llm-mobile"


def read_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(l) for l in f]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--outdir", default="data/train_sft25_t2")
    args = ap.parse_args()
    outdir = os.path.join(ROOT, args.outdir)
    os.makedirs(outdir, exist_ok=True)
    rng = random.Random(20261108)

    t2 = read_jsonl(os.path.join(ROOT, "data/train_sft25_t2/t2_clean.jsonl"))
    rng.shuffle(t2)

    academic = []
    for cat in ("ap_calc", "precalc", "ap_stats"):
        rows = read_jsonl(os.path.join(ROOT, f"data/sft19/{cat}.jsonl"))
        rng.shuffle(rows)
        academic += rows[:233]

    leader = read_jsonl(os.path.join(ROOT, "data/train_sft21b_leader/train.jsonl"))
    rng.shuffle(leader)
    leader = leader[:300]

    rows = t2 + academic + leader
    rng.shuffle(rows)
    n = max(1, len(rows) // 10)
    val, train = rows[:n], rows[n:]
    for name, data in (("train", train), ("val", val)):
        with open(os.path.join(outdir, f"{name}.jsonl"), "w", encoding="utf-8") as f:
            for r in data:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    stats = {"t2_clean": len(t2), "academic": len(academic), "leader": len(leader),
             "total": len(rows), "train": len(train), "val": len(val)}
    with open(os.path.join(outdir, "stats.json"), "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)
    print(json.dumps(stats, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
