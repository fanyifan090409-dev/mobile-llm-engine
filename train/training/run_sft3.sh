#!/usr/bin/env bash
# SFT3 工具遵循率专项：PT2 final 基础上 2 epochs（lr 1e-5 默认），数据=data/train_sft3b/
# （schedule 轨迹已展开：tool_call 段独立成样本进 loss，占比 ~59%）。--no-think 启用空思考块模板，
# 与推理侧 EngineCore.thinkTags 双端对齐。带 torch-compile 跑，崩溃则去 compile 重试一次。
set -u
cd "$(dirname "$0")/.."
export MLFLOW_TRACKING_URI=http://127.0.0.1:5000
export MLFLOW_EXPERIMENT_NAME=llm-mobile
VENV=/home/ubuntu/Miniconda3/envs/train/bin
LOG="logs/sft3b_0.6b.log"
: > "$LOG"

EXTRA="--torch-compile"
OW="--overwrite"
for attempt in 1 2; do
  echo "===== SFT3B 尝试 $attempt $(date '+%F %T') extra=[$EXTRA] overwrite=[$OW] =====" >> "$LOG"
  "$VENV/torchrun" --nproc_per_node=2 scripts/train_sft.py \
    --model checkpoints/qwen3-0.6b-pt2-20261025/final --tokenizer models/Qwen3-0.6B \
    --data data/train_sft3b/train.jsonl --out checkpoints/qwen3-0.6b-sft3b-20261026 \
    --deepspeed scripts/ds_zero2.json --epochs 2 --max-len 2048 \
    --per-device-bs 16 --grad-accum 4 --save-steps 500 --logging-steps 10 \
    --no-think $OW --chunked-ce $EXTRA >> "$LOG" 2>&1
  if grep -q "TRAINING_FINISHED" "$LOG"; then
    echo "SFT3B_ALL_DONE $(date '+%F %T')" >> "$LOG"
    exit 0
  fi
  # 崩溃：第二次去掉 torch-compile 与 overwrite（resume）
  EXTRA=""
  OW=""
done
echo "SFT3B 两次尝试均失败，现场保留 $(date '+%F %T')" >> "$LOG"
exit 1
