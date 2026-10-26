#!/usr/bin/env bash
# SFT 正式训练启动器：带 torch-compile 跑，崩溃则去 compile 重试一次。
# 第二次不带 --overwrite：有 checkpoint 自动 resume，无则干净重跑。
set -u
cd "$(dirname "$0")/.."
export MLFLOW_TRACKING_URI=http://127.0.0.1:5000
export MLFLOW_EXPERIMENT_NAME=llm-mobile
VENV=/home/ubuntu/Miniconda3/envs/train/bin
LOG="logs/sft_0.6b.log"
: > "$LOG"

EXTRA="--torch-compile"
OW="--overwrite"
for attempt in 1 2; do
  echo "===== SFT 尝试 $attempt $(date '+%F %T') extra=[$EXTRA] overwrite=[$OW] =====" >> "$LOG"
  "$VENV/torchrun" --nproc_per_node=2 scripts/train_sft.py \
    --model checkpoints/qwen3-0.6b-pt-20261024/final --tokenizer models/Qwen3-0.6B \
    --data data/train/train.jsonl --out checkpoints/qwen3-0.6b-sft-20261024 \
    --deepspeed scripts/ds_zero2.json --epochs 2 --max-len 2048 \
    --per-device-bs 16 --grad-accum 4 --save-steps 500 --logging-steps 10 \
    $OW --chunked-ce $EXTRA >> "$LOG" 2>&1
  if grep -q "TRAINING_FINISHED" "$LOG"; then
    echo "SFT_ALL_DONE $(date '+%F %T')" >> "$LOG"
    exit 0
  fi
  # 崩溃：第二次去掉 torch-compile 与 overwrite（resume）
  EXTRA=""
  OW=""
done
echo "SFT 两次尝试均失败，现场保留 $(date '+%F %T')" >> "$LOG"
exit 1
