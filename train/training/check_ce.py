#!/usr/bin/env python3
"""CE 等价自检入口：单卡加载模型，比对分块 CE 与原生 CE 的 loss/梯度。

用法：CUDA_VISIBLE_DEVICES=0 python scripts/check_ce.py --model models/Qwen3-0.6B
退出码 0=等价（CE_EQUIVALENCE_OK），1=不等价/异常，供 swap_optimize.sh grep 判决。
"""
import argparse

from chunked_ce import check_equivalence


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--chunk", type=int, default=256)
    args = ap.parse_args()
    raise SystemExit(0 if check_equivalence(args.model, args.chunk) else 1)


if __name__ == "__main__":
    main()
