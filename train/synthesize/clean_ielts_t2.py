#!/usr/bin/env python3
"""雅思 T2 清洗：熵率过滤 + 语义去重，剔除 Task 1（T1 走确定性草稿工具）。

用法（训练机）：
  python3 clean_ielts_t2.py --out data/train_sft25_t2/t2_clean.jsonl
"""
import argparse
import json
import math
import os
import re
import zlib
from collections import Counter

ROOT = "/home/ubuntu/llm-mobile"


def words(text):
    return re.findall(r"[a-z']+", text.lower())


def bigram_entropy(text):
    w = words(text)
    if len(w) < 2:
        return 0.0
    bg = Counter(zip(w, w[1:]))
    n = sum(bg.values())
    return -sum((c / n) * math.log2(c / n) for c in bg.values())


def shingles(text, k=5):
    w = words(text)
    return {" ".join(w[i:i + k]) for i in range(max(1, len(w) - k + 1))}


def jaccard(a, b):
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=os.path.join(ROOT, "data/sft19/ielts.jsonl"))
    ap.add_argument("--out", default=os.path.join(ROOT, "data/train_sft25_t2/t2_clean.jsonl"))
    ap.add_argument("--entropy-drop", type=float, default=0.15)
    ap.add_argument("--dedup-threshold", type=float, default=0.85)
    ap.add_argument("--min-words", type=int, default=200)
    args = ap.parse_args()

    rows = [json.loads(l) for l in open(args.src, encoding="utf-8")]
    t2 = []
    for r in rows:
        u = r["messages"][0]["content"]
        a = r["messages"][-1]["content"]
        if not re.search(r"Task\s*2", u):
            continue
        if len(words(a)) < args.min_words:
            continue
        t2.append(r)
    print(f"Task 2 rows: {len(t2)}")

    scored = []
    for r in t2:
        a = r["messages"][-1]["content"]
        scored.append((bigram_entropy(a), len(zlib.compress(a.encode())) / max(1, len(a)), r))
    scored.sort(key=lambda x: x[0])
    drop_n = int(len(scored) * args.entropy_drop)
    kept = [x[2] for x in scored[drop_n:]]
    print(f"entropy drop {drop_n}, kept {len(kept)}")

    # 语义去重：5-gram Jaccard；O(n²) 对 ~500 条足够
    out, sh = [], []
    for r in kept:
        s = shingles(r["messages"][-1]["content"])
        if any(jaccard(s, t) >= args.dedup_threshold for t in sh):
            continue
        out.append(r)
        sh.append(s)
    print(f"dedup kept {len(out)}")

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        for r in out:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"WROTE {len(out)} -> {args.out}")


if __name__ == "__main__":
    main()
