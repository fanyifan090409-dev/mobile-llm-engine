#!/usr/bin/env bash
# SFT27g CAS v7（定向修复）：v5 final 续训 LoRA，lr 3e-5，1 epoch
# 数据=train_sft27g_cas：平均值/复合/二阶导/limit 646 行 + 行为回放 1,550 行
set -u
cd "$(dirname "$0")/.."
export MLFLOW_TRACKING_URI=http://127.0.0.1:5000
export MLFLOW_EXPERIMENT_NAME=llm-mobile
VENV=/home/ubuntu/Miniconda3/envs/train/bin
BASE=checkpoints/qwen3-1.7b-sft27e-cas-20261109/final
OUT=checkpoints/qwen3-1.7b-sft27g-cas-$(date +%Y%m%d)
LOG="logs/sft27g_cas.log"
: > "$LOG"

"$VENV/torchrun" --nproc_per_node=2 scripts/train_sft.py \
  --model "$BASE" --tokenizer models/Qwen3-1.7B \
  --data data/train_sft27g_cas/train.jsonl --val data/train_sft27g_cas/val.jsonl \
  --out "$OUT" \
  --deepspeed scripts/ds_zero2.json --epochs 1 --max-len 2048 \
  --per-device-bs 8 --grad-accum 4 --save-steps 500 --logging-steps 5 \
  --eval-steps 20 --lr 3e-5 --lora-r 16 --lora-alpha 32 --lora-dropout 0.05 \
  --no-think --chunked-ce --save-only-model --overwrite >> "$LOG" 2>&1
if grep -q "TRAINING_FINISHED" "$LOG" && grep -q "LORA_MERGED" "$LOG"; then
  echo "$OUT" > logs/sft27g_cas.outdir
  echo "SFT27G_CAS_ALL_DONE $(date '+%F %T')" >> "$LOG"
  exit 0
fi
echo "SFT27g CAS 失败，现场保留 $(date '+%F %T')" >> "$LOG"
exit 1
