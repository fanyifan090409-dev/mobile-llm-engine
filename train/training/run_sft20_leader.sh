#!/usr/bin/env bash
# SFT20 领队线（1.7B）：SFT19 final 基础上 3 epochs；数据=data/train_sft20_leader/
# （leader 多轮已按 assistant 回合展开 + 历史池六类降采样防遗忘）。
# 其余同 run_sft19.sh。
set -u
cd "$(dirname "$0")/.."
export MLFLOW_TRACKING_URI=http://127.0.0.1:5000
export MLFLOW_EXPERIMENT_NAME=llm-mobile
VENV=/home/ubuntu/Miniconda3/envs/train/bin
OUT=checkpoints/qwen3-1.7b-sft20-$(date +%Y%m%d)
LOG="logs/sft20_1.7b.log"
: > "$LOG"

SMOKE_OUT="${OUT}-smoke"
"$VENV/torchrun" --nproc_per_node=2 scripts/train_sft.py \
  --model checkpoints/qwen3-1.7b-sft19-20261104/final --tokenizer models/Qwen3-1.7B \
  --data data/train_sft20_leader/train.jsonl --val data/train_sft20_leader/val.jsonl \
  --out "$SMOKE_OUT" \
  --deepspeed scripts/ds_zero2.json --epochs 3 --max-len 2048 \
  --per-device-bs 8 --grad-accum 8 --max-steps 3 --eval-steps 1 --logging-steps 1 \
  --no-think --chunked-ce --overwrite >> "$LOG" 2>&1
RC=$?
if [ $RC -ne 0 ] || ! grep -q "'loss'" "$LOG" || ! grep -q "'eval_loss'" "$LOG"; then
  echo "SMOKE_FAILED rc=$RC 冒烟未通过（loss/eval_loss 必须都出数），停止" >> "$LOG"; exit 1
fi
echo "SMOKE_OK 冒烟通过" >> "$LOG"
: > "$LOG"
[ "${SMOKE_ONLY:-0}" = "1" ] && exit 0

OW="--overwrite"
for attempt in 1 2; do
  echo "===== SFT20-LEADER 尝试 $attempt $(date '+%F %T') overwrite=[$OW] =====" >> "$LOG"
  "$VENV/torchrun" --nproc_per_node=2 scripts/train_sft.py \
    --model checkpoints/qwen3-1.7b-sft19-20261104/final --tokenizer models/Qwen3-1.7B \
    --data data/train_sft20_leader/train.jsonl --val data/train_sft20_leader/val.jsonl \
    --out "$OUT" \
    --deepspeed scripts/ds_zero2.json --epochs 3 --max-len 2048 \
    --per-device-bs 8 --grad-accum 8 --save-steps 500 --logging-steps 10 \
    --eval-steps 500 --no-think --chunked-ce $OW >> "$LOG" 2>&1
  if grep -q "TRAINING_FINISHED" "$LOG"; then
    echo "SFT20_LEADER_ALL_DONE $(date '+%F %T')" >> "$LOG"
    exit 0
  fi
  OW=""
done
echo "SFT20 领队线两次尝试均失败，现场保留 $(date '+%F %T')" >> "$LOG"
exit 1
