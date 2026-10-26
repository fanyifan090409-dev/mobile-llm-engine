#!/usr/bin/env bash
# SFT2 正式训练：PT2 final 基础上 2 epochs（lr 1e-5，与 SFT1 一致），产物=最终发布候选。
# 由 watch_sft2.sh 在 PT2 收段后自动启动。带 torch-compile 跑，崩溃则去 compile 重试一次。
set -u
cd "$(dirname "$0")/.."
export MLFLOW_TRACKING_URI=http://127.0.0.1:5000
export MLFLOW_EXPERIMENT_NAME=llm-mobile
VENV=/home/ubuntu/Miniconda3/envs/train/bin
LOG="logs/sft2_0.6b.log"
: > "$LOG"

EXTRA="--torch-compile"
OW="--overwrite"
for attempt in 1 2; do
  echo "===== SFT2 尝试 $attempt $(date '+%F %T') extra=[$EXTRA] overwrite=[$OW] =====" >> "$LOG"
  "$VENV/torchrun" --nproc_per_node=2 scripts/train_sft.py \
    --model checkpoints/qwen3-0.6b-pt2-20261025/final --tokenizer models/Qwen3-0.6B \
    --data data/train/train.jsonl --out checkpoints/qwen3-0.6b-sft2-20261026 \
    --deepspeed scripts/ds_zero2.json --epochs 2 --max-len 2048 \
    --per-device-bs 16 --grad-accum 4 --save-steps 500 --logging-steps 10 \
    $OW --chunked-ce $EXTRA >> "$LOG" 2>&1
  if grep -q "TRAINING_FINISHED" "$LOG"; then
    echo "SFT2_ALL_DONE $(date '+%F %T')" >> "$LOG"
    exit 0
  fi
  # 崩溃：第二次去掉 torch-compile 与 overwrite（resume）
  EXTRA=""
  OW=""
done
echo "SFT2 两次尝试均失败，现场保留 $(date '+%F %T')" >> "$LOG"
exit 1
