#!/usr/bin/env bash
# 红灯加训：SFT final 基础上再训 2 epochs（lr 5e-6），独立目录不覆盖主 run。
# 由本机夜间总控触发（tmux sft-extra）。注意：主 SFT 用 train_sft_launch.sh，本脚本只服务加训。
set -u
cd "$(dirname "$0")/.."
export MLFLOW_TRACKING_URI=http://127.0.0.1:5000
export MLFLOW_EXPERIMENT_NAME=llm-mobile
VENV=/home/ubuntu/Miniconda3/envs/train/bin
LOG="logs/sft_extra.log"
: > "$LOG"

"$VENV/torchrun" --nproc_per_node=2 scripts/train_sft.py \
  --model checkpoints/qwen3-0.6b-sft-20261024/final --tokenizer models/Qwen3-0.6B \
  --data data/train/train.jsonl --out checkpoints/qwen3-0.6b-sft-20261024-extra \
  --deepspeed scripts/ds_zero2.json --epochs 2 --max-len 2048 \
  --per-device-bs 16 --grad-accum 4 --save-steps 500 --logging-steps 10 \
  --lr 5e-6 --overwrite --chunked-ce --torch-compile >> "$LOG" 2>&1
grep -q "TRAINING_FINISHED" "$LOG" && echo "SFT_EXTRA_DONE" >> "$LOG" && exit 0
echo "SFT_EXTRA_FAILED" >> "$LOG"
exit 1
