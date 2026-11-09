#!/usr/bin/env bash
# SFT27e CAS v5（limit）：SFT19 final + LoRA r16，3 epochs；数据=train_sft27e_cas
# v4 数据 + 数值 limit（有理式/0-0/多项式/sin(kx)/x），提示词 v7b
set -u
cd "$(dirname "$0")/.."
export MLFLOW_TRACKING_URI=http://127.0.0.1:5000
export MLFLOW_EXPERIMENT_NAME=llm-mobile
VENV=/home/ubuntu/Miniconda3/envs/train/bin
OUT=checkpoints/qwen3-1.7b-sft27e-cas-$(date +%Y%m%d)
LOG="logs/sft27e_cas.log"
: > "$LOG"

SMOKE_OUT="${OUT}-smoke"
"$VENV/torchrun" --nproc_per_node=2 scripts/train_sft.py \
  --model checkpoints/qwen3-1.7b-sft19-20261104/final --tokenizer models/Qwen3-1.7B \
  --data data/train_sft27e_cas/train.jsonl --val data/train_sft27e_cas/val.jsonl \
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
if [ "$FREE_G" -lt 10 ]; then
  echo "DISK_LOW ${FREE_G}G，停止" >> "$LOG"; exit 1
fi

OW="--overwrite"
for attempt in 1 2; do
  echo "===== SFT27E-CAS-V5-LIMIT 尝试 $attempt $(date '+%F %T') overwrite=[$OW] =====" >> "$LOG"
  "$VENV/torchrun" --nproc_per_node=2 scripts/train_sft.py \
    --model checkpoints/qwen3-1.7b-sft19-20261104/final --tokenizer models/Qwen3-1.7B \
    --data data/train_sft27e_cas/train.jsonl --val data/train_sft27e_cas/val.jsonl \
    --out "$OUT" \
    --deepspeed scripts/ds_zero2.json --epochs 3 --max-len 2048 \
    --per-device-bs 8 --grad-accum 4 --save-steps 500 --logging-steps 5 \
    --eval-steps 20 --lr 1e-4 --lora-r 16 --lora-alpha 32 --lora-dropout 0.05 \
    --no-think --chunked-ce --save-only-model $OW >> "$LOG" 2>&1
  if grep -q "TRAINING_FINISHED" "$LOG" && grep -q "LORA_MERGED" "$LOG"; then
    echo "$OUT" > logs/sft27e_cas.outdir
    echo "SFT27E_CAS_ALL_DONE $(date '+%F %T')" >> "$LOG"
    exit 0
  fi
  OW=""
done
echo "SFT27e CAS 两次尝试均失败，现场保留 $(date '+%F %T')" >> "$LOG"
exit 1
