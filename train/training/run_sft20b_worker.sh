#!/usr/bin/env bash
# SFT20b 工人日期补训：从 SFT20 工人 final 继续训 2 epochs。
# 数据 = 规则日期样本 4000 + SFT20 回放 800（data/train_sft20b_worker）。
# 其余沿用 SFT20：--no-think 对齐推理侧、--chunked-ce 防 OOM、冒烟门禁先行。
set -u
cd "$(dirname "$0")/.."
export MLFLOW_TRACKING_URI=http://127.0.0.1:5000
export MLFLOW_EXPERIMENT_NAME=llm-mobile
VENV=/home/ubuntu/Miniconda3/envs/train/bin
OUT=checkpoints/qwen3-0.6b-sft20b-$(date +%Y%m%d)
LOG="logs/sft20b_0.6b.log"
: > "$LOG"

SMOKE_OUT="${OUT}-smoke"
"$VENV/torchrun" --nproc_per_node=2 scripts/train_sft.py \
  --model checkpoints/qwen3-0.6b-sft20-20261106/final --tokenizer models/Qwen3-0.6B \
  --data data/train_sft20b_worker/train.jsonl --val data/train_sft20b_worker/val.jsonl \
  --out "$SMOKE_OUT" \
  --deepspeed scripts/ds_zero2.json --epochs 2 --max-len 2048 \
  --per-device-bs 16 --grad-accum 4 --max-steps 3 --eval-steps 1 --logging-steps 1 \
  --no-think --chunked-ce --overwrite >> "$LOG" 2>&1
RC=$?
if [ $RC -ne 0 ] || ! grep -q "'loss'" "$LOG" || ! grep -q "'eval_loss'" "$LOG"; then
  echo "SMOKE_FAILED rc=$RC 冒烟未通过（loss/eval_loss 必须都出数），停止" >> "$LOG"; exit 1
fi
echo "SMOKE_OK 冒烟通过" >> "$LOG"
rm -rf "$SMOKE_OUT"
# 清空日志再进正式训练：防止正式段误匹配冒烟输出
: > "$LOG"

"$VENV/torchrun" --nproc_per_node=2 scripts/train_sft.py \
  --model checkpoints/qwen3-0.6b-sft20-20261106/final --tokenizer models/Qwen3-0.6B \
  --data data/train_sft20b_worker/train.jsonl --val data/train_sft20b_worker/val.jsonl \
  --out "$OUT" \
  --deepspeed scripts/ds_zero2.json --epochs 2 --max-len 2048 \
  --per-device-bs 16 --grad-accum 4 --save-steps 500 --logging-steps 10 \
  --eval-steps 500 --no-think --chunked-ce --overwrite >> "$LOG" 2>&1
if grep -q "TRAINING_FINISHED" "$LOG"; then
  echo "SFT20B_WORKER_ALL_DONE $(date '+%F %T')" >> "$LOG"
else
  echo "SFT20B 工人线失败，现场保留 $(date '+%F %T')" >> "$LOG"
  exit 1
fi
