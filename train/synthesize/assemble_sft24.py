#!/usr/bin/env python3
"""SFT24 雅思 Task 1 读图专项：798 条新数据 + 600 条旧雅思写作回放 + 700 条学术回放。

在训练机跑：
  python3 assemble_sft24.py --outdir data/train_sft24_ielts
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
    ap.add_argument("--outdir", default="data/train_sft24_ielts")
    args = ap.parse_args()
    outdir = os.path.join(ROOT, args.outdir)
    os.makedirs(outdir, exist_ok=True)
    rng = random.Random(20261108)

    new_rows = read_jsonl(os.path.join(ROOT, "data/train_sft24_ielts_t1/train.jsonl"))
    rng.shuffle(new_rows)

    ielts = read_jsonl(os.path.join(ROOT, "data/sft19/ielts.jsonl"))
    rng.shuffle(ielts)
    ielts = ielts[:600]

    academic = []
    for cat in ("ap_calc", "precalc", "ap_stats"):
        rows = read_jsonl(os.path.join(ROOT, f"data/sft19/{cat}.jsonl"))
        rng.shuffle(rows)
        academic += rows[:233]

    rows = new_rows + ielts + academic
    rng.shuffle(rows)
    n = max(1, len(rows) // 10)
    val, train = rows[:n], rows[n:]
    for name, data in (("train", train), ("val", val)):
        with open(os.path.join(outdir, f"{name}.jsonl"), "w", encoding="utf-8") as f:
            for r in data:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    stats = {
        "ielts_t1_new": len(new_rows),
        "ielts_replay": len(ielts),
        "academic_replay": len(academic),
        "total": len(rows),
        "train": len(train),
        "val": len(val),
    }
    with open(os.path.join(outdir, "stats.json"), "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)
    print(json.dumps(stats, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
