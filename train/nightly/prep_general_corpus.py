#!/usr/bin/env python3
"""从 fineweb2 cmn_Hani 原始 parquet 抽干净中文段落做通用域 PPL 语料。
过滤规则：80-600 字符、汉字占比>70%、无 URL、无连续标点刷屏、去重。
"""
import argparse
import glob
import re
from pathlib import Path

import pyarrow.parquet as pq

HAN = re.compile(r"[\u4e00-\u9fff]")


def clean(text: str):
    t = text.strip().replace("\n", " ")
    if not (80 <= len(t) <= 600):
        return None
    if "http" in t or "www." in t:
        return None
    han = len(HAN.findall(t))
    if han / len(t) < 0.70:
        return None
    if re.search(r"[，。！？、]{6,}", t):
        return None
    return t


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--shards", default="/home/ubuntu/llm-mobile/data/pt_raw/fineweb2_cmn/data/cmn_Hani/train")
    ap.add_argument("--out", required=True)
    ap.add_argument("--target-bytes", type=int, default=140000)
    args = ap.parse_args()

    files = sorted(glob.glob(str(Path(args.shards) / "*.parquet")))
    seen = set()
    picked = []
    # 前 3 个分片，每片读前 N 行，轮转抽取保证多样性
    for f in files[:3]:
        for batch in pq.ParquetFile(f).iter_batches(batch_size=2000):
            for row in batch.column("text").to_pylist():
                c = clean(row)
                if c and c[:40] not in seen:
                    seen.add(c[:40])
                    picked.append(c)
                if len(picked) >= 400:
                    break
            if len(picked) >= 400:
                break
        if len(picked) >= 400:
            break
    # 轮转打散（避免同分片聚集），截到目标字节附近
    picked = picked[::2] + picked[1::2]
    total = 0
    out = []
    for p in picked:
        total += len(p.encode("utf-8")) + 1
        out.append(p)
        if total >= args.target_bytes:
            break
    Path(args.out).write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"OK {len(out)} paragraphs {total} bytes -> {args.out}")


if __name__ == "__main__":
    main()
