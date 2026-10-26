#!/usr/bin/env python3
"""SFT 数据拼装：六类合成 jsonl → 过滤 + 按计划占比降采样 → train.jsonl / val.jsonl。

输入：data/sft/*.jsonl（合成产物，123,104 条，QC 已过）
输出：data/train/train.jsonl + val.jsonl + report.txt

规则：
  1. message 类过滤选项式样本（assistant 内容含「选项/以下几种/供你选择/###/**」或以「这里」开头）
     ——与「帮我写一条消息」意图不符，会让模型学会多选项模板（2026-10-24 已与用户确认）；
  2. 按 est tokens（字符数/1.6，中英混合粗估）降采样：目标占比 翻译25/记录25/日程20/消息15/摘要10/其他5；
     message 现量不足 15% 目标 → 全保留，接受偏差；
  3. 每类分层抽 2% 进 val.jsonl（schedule 保留完整工具调用轨迹）；
  4. 全局 shuffle，seed 固定可复现。

不修改任何原始 jsonl 文件；回滚 = 删除 data/train/ 重跑。

用法：python3 assemble_train.py --srcdir data/sft --outdir data/train
"""
import argparse
import json
import os
import random

# 各类 est tokens 上限（按计划占比 25/25/20/15/10/5 × ~12M 总量）
CAPS = {"translate": 3_000_000, "record_tidy": 3_000_000, "schedule": 2_400_000,
        "message": 1_800_000, "summarize": 1_200_000, "misc": 600_000}
MSG_BAD_PATTERNS = ["选项", "以下几种", "供你选择", "###", "**"]
VAL_RATIO = 0.02
SEED = 20261024


def est_tokens(msgs):
    return sum(len(str(m.get("content") or "")) for m in msgs) / 1.6


def is_bad_message(msgs):
    last = [m for m in msgs if m.get("role") == "assistant"]
    if not last:
        return True
    content = str(last[-1].get("content") or "")
    if content.startswith("这里"):
        return True
    return any(p in content for p in MSG_BAD_PATTERNS)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--srcdir", default="data/sft")
    ap.add_argument("--outdir", default="data/train")
    args = ap.parse_args()

    rng = random.Random(SEED)
    os.makedirs(args.outdir, exist_ok=True)

    report_lines = []
    train_all, val_all = [], []

    for cat in CAPS:
        path = os.path.join(args.srcdir, f"{cat}.jsonl")
        if not os.path.exists(path):
            report_lines.append(f"{cat}: 文件缺失，跳过")
            continue
        recs, orig_n = [], 0
        with open(path, encoding="utf-8") as f:
            for line in f:
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                orig_n += 1
                msgs = rec.get("messages") or []
                if cat == "message" and is_bad_message(msgs):
                    continue
                recs.append(rec)

        rng.shuffle(recs)
        kept, kept_toks = [], 0.0
        for rec in recs:
            t = est_tokens(rec["messages"])
            if kept_toks + t > CAPS[cat]:
                continue
            kept.append(rec)
            kept_toks += t

        n_val = max(1, int(len(kept) * VAL_RATIO))
        val = kept[:n_val]
        train = kept[n_val:]
        train_all.extend(train)
        val_all.extend(val)

        share = kept_toks / max(sum(est_tokens(r["messages"]) for r in recs), 1)
        dropped = orig_n - len(recs)
        filt_note = f"，过滤 {dropped} 条" if dropped else ""
        report_lines.append(
            f"{cat}: 原始 {orig_n} 条{filt_note} → 保留 {len(kept)} 条 / est {kept_toks/1e6:.2f}M tokens"
            f"（上限 {CAPS[cat]/1e6:.1f}M，采样比例 {share:.0%}）；val {n_val} 条")

    rng.shuffle(train_all)
    rng.shuffle(val_all)

    with open(os.path.join(args.outdir, "train.jsonl"), "w", encoding="utf-8") as f:
        for rec in train_all:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    with open(os.path.join(args.outdir, "val.jsonl"), "w", encoding="utf-8") as f:
        for rec in val_all:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    total_toks = sum(est_tokens(r["messages"]) for r in train_all)
    report_lines.append(f"合计: train {len(train_all)} 条 / est {total_toks/1e6:.2f}M tokens; "
                        f"val {len(val_all)} 条")
    report = "\n".join(report_lines)
    with open(os.path.join(args.outdir, "report.txt"), "w", encoding="utf-8") as f:
        f.write(report + "\n")
    print(report)


if __name__ == "__main__":
    main()
