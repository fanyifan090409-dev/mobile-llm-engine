#!/usr/bin/env python3
"""SFT 数据拼装：六类合成 jsonl → 过滤 + 按计划占比降采样 → train.jsonl / val.jsonl。

输入：data/sft/*.jsonl（合成产物，首轮 + 补合成 17M 累计，QC 已过）
输出：data/train/<train.jsonl + val.jsonl + report.txt>（--profile sft3 时输出 data/train_sft3/，
     sft17 时输出 data/train_sft17/）

规则：
  1. message 类过滤选项式样本（assistant 内容含「选项/以下几种/供你选择/###/**」或以「这里」开头）
     ——与「帮我写一条消息」意图不符，会让模型学会多选项模板（2026-10-24 已与用户确认）；
  2. 按 est tokens（字符数/1.6，中英混合粗估）降采样到 profile 占比上限；
  3. profile=sft3（工具遵循率专项，docs/plans/SFT3工具遵循率专项.md）：
     - schedule 轨迹前插合成期 system 触发文本（SYNTH_SYS_SCHED1，与推理侧 CalendarTool.usagePrompt 逐字一致）；
     - 占比上限：schedule 全保留（≈37%）/ translate 1.3M / record 1.0M / summarize 0.5M / misc 0.15M / message 全保留；
     - schedule 轨迹展开成多样本（tool_call 段独立成学习目标），sft17 同款展开；
  4. profile=sft17（1.7B 主力线）：历史池 + 补合成 17M 全量拼装，总预算 ~28M est tokens，
     占比贴近合成 share 25/25/20/15/10/5——translate/record 各 6.25M 降采样、
     schedule 展开后 10M 上限基本全保留（工具调用是核心任务）、其余类全保留；
  5. profile=sft18（学术能力专项，docs/plans/SFT18学术能力专项-美高数学AP雅思.md）：
     学术三类 data/sft18/{ap_calc,ap_stats,ielts}.jsonl 全保留（占 75-80%），
     历史池六类 data/sft/*.jsonl 按 CAPS_SFT18_HISTORY 降采样（占 20-25%，防遗忘）；
     默认输出 data/train_sft18/；holdout 子目录不参与拼装（验收期评测专用）；
  6. 每类分层抽 2% 进 val.jsonl（schedule 保留完整工具调用轨迹）；
  7. 全局 shuffle，seed 固定可复现。

不修改任何原始 jsonl 文件；回滚 = 删除输出目录重跑。

用法：python3 assemble_train.py --srcdir data/sft --outdir data/train [--profile sft2|sft3|sft17|sft18|sft19]
"""
import argparse
import json
import os
import random

# 各类 est tokens 上限（sft2：计划占比 25/25/20/15/10/5 × ~12M 总量）
CAPS_SFT2 = {"translate": 3_000_000, "record_tidy": 3_000_000, "schedule": 2_400_000,
             "message": 1_800_000, "summarize": 1_200_000, "misc": 600_000}
# sft3：schedule 全保留提占比（含 system 前缀 est ≈3.0M）；展开后每条轨迹多一条
# tool_call 短样本（≈+1.5M），上限 4.2M 只为不截断
CAPS_SFT3 = {"translate": 1_300_000, "record_tidy": 1_000_000, "schedule": 4_200_000,
             "message": 1_800_000, "summarize": 500_000, "misc": 150_000}
# sft17（1.7B 主力线）：历史池 + 补合成 17M 全量拼装，占比贴近合成 share 25/25/20/15/10/5；
# schedule 展开后 ≈9.6M，上限 10M 只为不截断（工具调用是核心任务，全保留）
CAPS_SFT17 = {"translate": 6_250_000, "record_tidy": 6_250_000, "schedule": 10_000_000,
              "message": 3_750_000, "summarize": 2_500_000, "misc": 1_250_000}
# sft18（学术能力专项）：学术三类（data/sft18/）全保留（预计 ≈6-7M est，占 75-80%），
# 历史池六类（data/sft/）降采样到 ≈1.8M est（占 20-25%，防灾难性遗忘）
CAPS_SFT18_HISTORY = {"translate": 500_000, "record_tidy": 450_000, "schedule": 400_000,
                      "message": 250_000, "summarize": 150_000, "misc": 50_000}
# sft19（数学强化专项）：历史池同 sft18 降采样（20% 防遗忘）；学术四类 + 真题转化池全保留
CAPS_SFT19_HISTORY = CAPS_SFT18_HISTORY
# sft20（多模型协作）：leader/worker 新数据全保留，历史池降采样防遗忘（占新数据约 30-50%）
CAPS_SFT20_LEADER_HISTORY = {"translate": 250_000, "record_tidy": 220_000, "schedule": 220_000,
                             "message": 130_000, "summarize": 70_000, "misc": 30_000}
CAPS_SFT20_WORKER_HISTORY = {"translate": 200_000, "schedule": 250_000, "summarize": 120_000}
PROFILES = {"sft2": CAPS_SFT2, "sft3": CAPS_SFT3, "sft17": CAPS_SFT17,
            "sft18": CAPS_SFT18_HISTORY, "sft19": CAPS_SFT19_HISTORY,
            "sft20_leader": CAPS_SFT20_LEADER_HISTORY,
            "sft20_worker": CAPS_SFT20_WORKER_HISTORY}
MSG_BAD_PATTERNS = ["选项", "以下几种", "供你选择", "###", "**"]
VAL_RATIO = 0.02
SEED = 20261024

# 合成期工具定义触发文本（与 synthesize_sft.py SYNTH_SYS_SCHED1 及
# apps/demo-cli CalendarTool.usagePrompt 逐字一致；改任一侧必须三处同步）
SYNTH_SYS_SCHED1 = ("你是手机助手。当用户要求添加日历事件时，只输出一个工具调用块，"
                    "不要输出任何其他内容，格式：\n"
                    "<tool_call>\n{\"name\": \"add_calendar_event\", \"arguments\": "
                    "{\"title\": \"事件名称\", \"start_time\": \"YYYY-MM-DD HH:mm\", "
                    "\"end_time\": \"YYYY-MM-DD HH:mm\", \"location\": \"地点\", \"note\": \"备注\"}}\n</tool_call>")


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
    ap.add_argument("--academic-srcdir", default="data/sft18",
                    help="sft18/sft19 profile 的学术合成源目录")
    ap.add_argument("--frq-srcdir", default="frq_converted",
                    help="sft19 profile 的真题转化池目录（train.jsonl）")
    ap.add_argument("--sft20-srcdir", default="data/cloud_sft20",
                    help="sft20 profile 的领队/工人样本目录（leader_sft20.jsonl / worker_sft20.jsonl）")
    ap.add_argument("--exclude", default="",
                    help="verify_math.py 输出的 violations.jsonl，按 hash 过滤数学错误样本")
    ap.add_argument("--outdir", default="data/train")
    ap.add_argument("--profile", default="sft2", choices=list(PROFILES))
    args = ap.parse_args()

    caps = PROFILES[args.profile]
    rng = random.Random(SEED)
    # 数学验证违规样本（verify_math.py 输出）：按 hash 过滤，错误答案不进训练池
    exclude = set()
    if args.exclude and os.path.exists(args.exclude):
        with open(args.exclude, encoding="utf-8") as f:
            for line in f:
                try:
                    h = json.loads(line).get("hash")
                    if h:
                        exclude.add(h)
                except Exception:
                    continue
    n_excluded = 0
    # sft18/sft19 默认输出目录（学术+历史池双源拼装）
    if args.profile in ("sft18", "sft19", "sft20_leader", "sft20_worker") and args.outdir == "data/train":
        args.outdir = "data/train_" + args.profile
    os.makedirs(args.outdir, exist_ok=True)

    report_lines = [f"profile={args.profile}"]
    train_all, val_all = [], []

    # (源目录, 类别, est tokens 上限；None=全保留, 文件名；None={cat}.jsonl)
    if args.profile == "sft18":
        groups = [(args.academic_srcdir, c, None, None) for c in ("ap_calc", "ap_stats", "ielts")]
        groups += [(args.srcdir, c, caps[c], None) for c in caps]
    elif args.profile == "sft19":
        groups = [(args.academic_srcdir, c, None, None)
                  for c in ("ap_calc", "precalc", "ap_stats", "ielts")]
        # 真题转化池：文件名 train.jsonl，类别名 ap_calc_frq（holdout 不在池内）
        groups += [(args.frq_srcdir, "ap_calc_frq", None, "train.jsonl")]
        groups += [(args.srcdir, c, caps[c], None) for c in caps]
    elif args.profile == "sft20_leader":
        groups = [(args.sft20_srcdir, "leader", None, "leader_sft20.jsonl")]
        groups += [(args.srcdir, c, caps[c], None) for c in caps]
    elif args.profile == "sft20_worker":
        groups = [(args.sft20_srcdir, "worker", None, "worker_sft20.jsonl")]
        groups += [(args.srcdir, c, caps[c], None) for c in caps]
    else:
        groups = [(args.srcdir, c, caps[c], None) for c in caps]

    for src_dir, cat, cap, fname in groups:
        path = os.path.join(src_dir, fname or f"{cat}.jsonl")
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
                if exclude and rec.get("hash") in exclude:
                    n_excluded += 1
                    continue
                if cat == "message" and is_bad_message(msgs):
                    continue
                # sft3/sft17/sft18/sft19：schedule 轨迹前插工具定义 system 触发文本（推理侧同款注入）
                if args.profile in ("sft3", "sft17", "sft18", "sft19") and cat == "schedule":
                    msgs = [{"role": "system", "content": SYNTH_SYS_SCHED1}] + msgs
                    # 轨迹展开：SFTDataset 只对最后一条 assistant 算 loss，不展开则
                    # tool_call 段永远被掩码在 prompt 里、模型只学口头确认（SFT3 首轮 0% 发射的根因）。
                    # 每条 assistant 切一个前缀样本：tool_call 段独立成为学习目标
                    for idx in range(len(msgs)):
                        if msgs[idx]["role"] == "assistant":
                            recs.append(dict(rec, messages=msgs[:idx + 1]))
                    continue
                # sft20 多轮：逐 assistant 回合展开（否则只有最后一轮汇总算 loss，派单动作本身学不到）
                if args.profile in ("sft20_leader", "sft20_worker") and cat in ("leader", "worker"):
                    for idx in range(len(msgs)):
                        if msgs[idx]["role"] == "assistant":
                            recs.append(dict(rec, messages=msgs[:idx + 1]))
                    continue
                recs.append(rec)

        rng.shuffle(recs)
        kept, kept_toks = [], 0.0
        for rec in recs:
            t = est_tokens(rec["messages"])
            if cap and kept_toks + t > cap:
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
        cap_note = f"（上限 {cap/1e6:.1f}M，采样比例 {share:.0%}）" if cap else "（全保留）"
        report_lines.append(
            f"{cat}: 原始 {orig_n} 条{filt_note} → 保留 {len(kept)} 条 / est {kept_toks/1e6:.2f}M tokens"
            f"{cap_note}；val {n_val} 条")

    rng.shuffle(train_all)
    rng.shuffle(val_all)

    with open(os.path.join(args.outdir, "train.jsonl"), "w", encoding="utf-8") as f:
        for rec in train_all:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    with open(os.path.join(args.outdir, "val.jsonl"), "w", encoding="utf-8") as f:
        for rec in val_all:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    total_toks = sum(est_tokens(r["messages"]) for r in train_all)
    if n_excluded:
        report_lines.append(f"数学验证违规过滤: {n_excluded} 条（--exclude {args.exclude}）")
    report_lines.append(f"合计: train {len(train_all)} 条 / est {total_toks/1e6:.2f}M tokens; "
                        f"val {len(val_all)} 条")
    report = "\n".join(report_lines)
    with open(os.path.join(args.outdir, "report.txt"), "w", encoding="utf-8") as f:
        f.write(report + "\n")
    print(report)


if __name__ == "__main__":
    main()
