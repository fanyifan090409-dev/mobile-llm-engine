#!/usr/bin/env bash
# SFT26 FRQ：SFT25 final + LoRA r16，2 epoch；数据=真实 FRQ 128 + SFT25 回放 1314
set -u
cd "$(dirname "$0")/.."
export MLFLOW_TRACKING_URI=http://127.0.0.1:5000
export MLFLOW_EXPERIMENT_NAME=llm-mobile
VENV=/home/ubuntu/Miniconda3/envs/train/bin
OUT=checkpoints/qwen3-1.7b-sft26-frq-$(date +%Y%m%d)
LOG="logs/sft26_frq.log"
: > "$LOG"

SMOKE_OUT="${OUT}-smoke"
"$VENV/torchrun" --nproc_per_node=2 scripts/train_sft.py \
  --model checkpoints/qwen3-1.7b-sft25-t2-20261108/final --tokenizer models/Qwen3-1.7B \
  --data data/train_sft26_frq/train.jsonl --val data/train_sft26_frq/val.jsonl \
  --out "$SMOKE_OUT" \
  --deepspeed scripts/ds_zero2.json --epochs 1 --max-len 2048 \
  --per-device-bs 4 --grad-accum 4 --max-steps 3 --eval-steps 1 --logging-steps 1 \
  --lr 1e-4 --lora-r 16 --lora-alpha 32 --lora-dropout 0.05 \
  --no-think --chunked-ce --save-only-model --overwrite >> "$LOG" 2>&1
RC=$?
if [ $RC -ne 0 ] || ! grep -q "LORA_APPLIED" "$LOG" || ! grep -q "'loss'" "$LOG" || ! grep -q "'eval_loss'" "$LOG"; then
  echo "SMOKE_FAILED rc=$RC 冒烟未通过（LoRA/loss/eval_loss 必须都出数），停止" >> "$LOG"; exit 1
fi
echo "SMOKE_OK 冒烟通过" >> "$LOG"
rm -rf "$SMOKE_OUT"
: > "$LOG"
[ "${SMOKE_ONLY:-0}" = "1" ] && exit 0

FREE_G=$(df -Pk . | awk 'NR==2 {print int($4/1024/1024)}')
if [ "$FREE_G" -lt 8 ]; then
  echo "DISK_LOW ${FREE_G}G，停止" >> "$LOG"; exit 1
fi

OW="--overwrite"
for attempt in 1 2; do
  echo "===== SFT26-FRQ-LORA 尝试 $attempt $(date '+%F %T') overwrite=[$OW] =====" >> "$LOG"
  "$VENV/torchrun" --nproc_per_node=2 scripts/train_sft.py \
    --model checkpoints/qwen3-1.7b-sft25-t2-20261108/final --tokenizer models/Qwen3-1.7B \
    --data data/train_sft26_frq/train.jsonl --val data/train_sft26_frq/val.jsonl \
    --out "$OUT" \
    --deepspeed scripts/ds_zero2.json --epochs 2 --max-len 2048 \
    --per-device-bs 4 --grad-accum 4 --save-steps 1000 --logging-steps 5 \
    --eval-steps 15 --lr 1e-4 --lora-r 16 --lora-alpha 32 --lora-dropout 0.05 \
    --no-think --chunked-ce --save-only-model $OW >> "$LOG" 2>&1
  if grep -q "TRAINING_FINISHED" "$LOG" && grep -q "LORA_MERGED" "$LOG"; then
    echo "$OUT" > logs/sft26_frq.outdir
    echo "SFT26_FRQ_ALL_DONE $(date '+%F %T')" >> "$LOG"
    exit 0
  fi
  OW=""
done
echo "SFT26 FRQ 两次尝试均失败，现场保留 $(date '+%F %T')" >> "$LOG"
exit 1
