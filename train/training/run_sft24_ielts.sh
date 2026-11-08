#!/usr/bin/env bash
# SFT24 雅思 Task 1 读图专项：从 SFT19 final 训 2 epochs。
# 数据 data/train_sft24_ielts/（798 新读图 + 600 旧雅思 + 700 学术回放）。
set -u
cd "$(dirname "$0")/.."
export MLFLOW_TRACKING_URI=http://127.0.0.1:5000
export MLFLOW_EXPERIMENT_NAME=llm-mobile
VENV=/home/ubuntu/Miniconda3/envs/train/bin
OUT=checkpoints/qwen3-1.7b-sft24-$(date +%Y%m%d)
LOG="logs/sft24_ielts.log"
: > "$LOG"

SMOKE_OUT="${OUT}-smoke"
"$VENV/torchrun" --nproc_per_node=2 scripts/train_sft.py \
  --model checkpoints/qwen3-1.7b-sft19-20261104/final --tokenizer models/Qwen3-1.7B \
  --data data/train_sft24_ielts/train.jsonl --val data/train_sft24_ielts/val.jsonl \
  --out "$SMOKE_OUT" \
  --deepspeed scripts/ds_zero2.json --epochs 2 --max-len 2048 \
  --per-device-bs 8 --grad-accum 8 --max-steps 3 --eval-steps 1 --logging-steps 1 \
  --no-think --chunked-ce --save-only-model --overwrite >> "$LOG" 2>&1
RC=$?
if [ $RC -ne 0 ] || ! grep -q "'loss'" "$LOG" || ! grep -q "'eval_loss'" "$LOG"; then
  echo "SMOKE_FAILED rc=$RC 冒烟未通过（loss/eval_loss 必须都出数），停止" >> "$LOG"; exit 1
fi
echo "SMOKE_OK 冒烟通过" >> "$LOG"
: > "$LOG"
[ "${SMOKE_ONLY:-0}" = "1" ] && exit 0

OW="--overwrite"
for attempt in 1 2; do
  echo "===== SFT24-IELTS 尝试 $attempt $(date '+%F %T') overwrite=[$OW] =====" >> "$LOG"
  "$VENV/torchrun" --nproc_per_node=2 scripts/train_sft.py \
    --model checkpoints/qwen3-1.7b-sft19-20261104/final --tokenizer models/Qwen3-1.7B \
    --data data/train_sft24_ielts/train.jsonl --val data/train_sft24_ielts/val.jsonl \
    --out "$OUT" \
    --deepspeed scripts/ds_zero2.json --epochs 2 --max-len 2048 \
    --per-device-bs 8 --grad-accum 8 --save-steps 1000 --logging-steps 5 \
    --eval-steps 10 --no-think --chunked-ce --save-only-model $OW >> "$LOG" 2>&1
  if grep -q "TRAINING_FINISHED" "$LOG"; then
    echo "SFT24_IELTS_ALL_DONE $(date '+%F %T')" >> "$LOG"
    exit 0
  fi
  OW=""
done
echo "SFT24 两次尝试均失败，现场保留 $(date '+%F %T')" >> "$LOG"
exit 1
