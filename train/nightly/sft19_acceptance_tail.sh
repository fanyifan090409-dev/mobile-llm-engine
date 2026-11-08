#!/usr/bin/env bash
# SFT19 验收收尾：Q4_K_M 工具调用 40 题 + Q5_K_M AP 微积分 FRQ 12 题
set -u
ROOT=/Users/fanyifan/Documents/Qoder/2026-10-23/90ee63b2
GGUF=$ROOT/train/gguf/qwen3-1.7b-sft19-20261104
VENVPY=$ROOT/train/nightly/venv/bin/python
DEMO=$ROOT/apps/demo-cli/.build/release/demo-cli

echo "===== SFT19 验收收尾 $(date '+%F %T') ====="

echo "--- Q4_K_M 工具调用 40 题 ---"
"$VENVPY" "$ROOT/train/nightly/eval_toolcall.py" \
  --model "$GGUF/qwen3-1.7b-sft19-Q4_K_M.gguf" --demo "$DEMO" \
  --quant Q4_K_M --tag sft19_Q4_K_M --prompts all --temp 0 --think-tags \
  --outdir "$ROOT/train/nightly/work/toolcall" || { echo "FATAL: Q4 工具调用评测失败"; exit 1; }

echo "--- 备份 SFT17 FRQ 旧输出 ---"
mkdir -p "$ROOT/train/eval/private/output_sft17_baseline"
cp -n "$ROOT/train/eval/private/output"/answer-*.txt \
  "$ROOT/train/eval/private/output_sft17_baseline/" 2>/dev/null || true

echo "--- AP Calc BC FRQ 数学验收（Q5_K_M，12 题）---"
bash "$ROOT/train/eval/run_ap_frq_eval.sh" \
  "$GGUF/qwen3-1.7b-sft19-Q5_K_M.gguf" Q5_K_M || { echo "FATAL: AP FRQ 评测失败"; exit 1; }

echo "SFT19_ACCEPTANCE_ALL_DONE $(date '+%F %T')"
