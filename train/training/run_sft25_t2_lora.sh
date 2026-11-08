#!/usr/bin/env bash
# SFT25 雅思 T2：SFT19 final + LoRA r16，1 epoch；数据=T2 清洗 541→熵率/去重 + 学术 700 + 领队 300
set -u
cd "$(dirname "$0")/.."
export MLFLOW_TRACKING_URI=http://127.0.0.1:5000
export MLFLOW_EXPERIMENT_NAME=llm-mobile
VENV=/home/ubuntu/Miniconda3/envs/train/bin
OUT=checkpoints/qwen3-1.7b-sft25-t2-$(date +%Y%m%d)
LOG="logs/sft25_t2.log"
: > "$LOG"

SMOKE_OUT="${OUT}-smoke"
"$VENV/torchrun" --nproc_per_node=2 scripts/train_sft.py \
  --model checkpoints/qwen3-1.7b-sft19-20261104/final --tokenizer models/Qwen3-1.7B \
  --data data/train_sft25_t2/train.jsonl --val data/train_sft25_t2/val.jsonl \
  --out "$SMOKE_OUT" \
  --deepspeed scripts/ds_zero2.json --epochs 1 --max-len 2048 \
  --per-device-bs 8 --grad-accum 8 --max-steps 3 --eval-steps 1 --logging-steps 1 \
  --lr 2e-4 --lora-r 16 --lora-alpha 32 --lora-dropout 0.05 \
  --no-think --chunked-ce --save-only-model --overwrite >> "$LOG" 2>&1
RC=$?
if [ $RC -ne 0 ] || ! grep -q "LORA_APPLIED" "$LOG" || ! grep -q "'loss'" "$LOG" || ! grep -q "'eval_loss'" "$LOG"; then
  echo "SMOKE_FAILED rc=$RC 冒烟未通过（LoRA/loss/eval_loss 必须都出数），停止" >> "$LOG"; exit 1
fi
echo "SMOKE_OK 冒烟通过" >> "$LOG"
: > "$LOG"
[ "${SMOKE_ONLY:-0}" = "1" ] && exit 0

OW="--overwrite"
for attempt in 1 2; do
  echo "===== SFT25-T2-LORA 尝试 $attempt $(date '+%F %T') overwrite=[$OW] =====" >> "$LOG"
  "$VENV/torchrun" --nproc_per_node=2 scripts/train_sft.py \
    --model checkpoints/qwen3-1.7b-sft19-20261104/final --tokenizer models/Qwen3-1.7B \
    --data data/train_sft25_t2/train.jsonl --val data/train_sft25_t2/val.jsonl \
    --out "$OUT" \
    --deepspeed scripts/ds_zero2.json --epochs 1 --max-len 2048 \
    --per-device-bs 8 --grad-accum 8 --save-steps 1000 --logging-steps 5 \
    --eval-steps 20 --lr 2e-4 --lora-r 16 --lora-alpha 32 --lora-dropout 0.05 \
    --no-think --chunked-ce --save-only-model $OW >> "$LOG" 2>&1
  if grep -q "TRAINING_FINISHED" "$LOG" && grep -q "LORA_MERGED" "$LOG"; then
    echo "SFT25_T2_ALL_DONE $(date '+%F %T')" >> "$LOG"
    exit 0
  fi
  OW=""
done
echo "SFT25 T2 两次尝试均失败，现场保留 $(date '+%F %T')" >> "$LOG"
exit 1
