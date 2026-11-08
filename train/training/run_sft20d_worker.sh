#!/usr/bin/env bash
# SFT20d：日期边界补训（0.6B 从 SFT20c final 起，闰日/跨年/跨月/小时进位）
set -u
cd "$(dirname "$0")/.."
export MLFLOW_TRACKING_URI=http://127.0.0.1:5000
export MLFLOW_EXPERIMENT_NAME=llm-mobile
VENV=/home/ubuntu/Miniconda3/envs/train/bin
BASE=checkpoints/qwen3-0.6b-sft20c-20261106/final
DATA=data/train_sft20d_worker
OUT=checkpoints/qwen3-0.6b-sft20d-$(date +%Y%m%d)
LOG="logs/sft20d_0.6b.log"
: > "$LOG"

SMOKE_OUT="${OUT}-smoke"
"$VENV/torchrun" --nproc_per_node=2 scripts/train_sft.py \
  --model "$BASE" --tokenizer models/Qwen3-0.6B \
  --data "$DATA/train.jsonl" --val "$DATA/val.jsonl" \
  --out "$SMOKE_OUT" \
  --deepspeed scripts/ds_zero2.json --epochs 3 --max-len 2048 \
  --per-device-bs 8 --grad-accum 4 --max-steps 3 --eval-steps 1 --logging-steps 1 \
  --no-think --chunked-ce --overwrite >> "$LOG" 2>&1
RC=$?
if [ $RC -ne 0 ] || ! grep -q "'loss'" "$LOG" || ! grep -q "'eval_loss'" "$LOG"; then
  echo "SMOKE_FAILED rc=$RC 冒烟未通过（loss/eval_loss 必须都出数），停止" >> "$LOG"; exit 1
fi
echo "SMOKE_OK 冒烟通过" >> "$LOG"
rm -rf "$SMOKE_OUT"
: > "$LOG"

"$VENV/torchrun" --nproc_per_node=2 scripts/train_sft.py \
  --model "$BASE" --tokenizer models/Qwen3-0.6B \
  --data "$DATA/train.jsonl" --val "$DATA/val.jsonl" \
  --out "$OUT" \
  --deepspeed scripts/ds_zero2.json --epochs 3 --max-len 2048 \
  --per-device-bs 8 --grad-accum 4 --save-steps 500 --logging-steps 10 \
  --eval-steps 100 --no-think --chunked-ce --overwrite >> "$LOG" 2>&1
if grep -q "TRAINING_FINISHED" "$LOG"; then
  echo "SFT20D_WORKER_ALL_DONE $(date '+%F %T')" >> "$LOG"
else
  echo "SFT20D 工人线失败，现场保留 $(date '+%F %T')" >> "$LOG"
  exit 1
fi
