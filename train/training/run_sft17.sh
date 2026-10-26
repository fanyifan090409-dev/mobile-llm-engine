#!/usr/bin/env bash
# SFT17（1.7B 主力线）：PT 1.7B final 基础上 2 epochs（lr 1e-5），数据=data/train_sft17/
# （assemble --profile sft17：历史池 + 补合成 17M 全量拼装，schedule 轨迹展开 + system 注入同 sft3b）。
# --no-think 空思考块模板与推理侧 EngineCore.thinkTags 对齐；--val 分层验证集记录 eval_loss。
# 不开 torch-compile：compile 会把 chunked CE 分块循环融合成完整 logits 内存墙回归 OOM（PT2 已实证）。
# SMOKE_ONLY=1 只跑冒烟：3 步验证 1.7B SFT 显存与 eval 路径（eval_steps=1 让验证路径真实跑一遍）。
set -u
cd "$(dirname "$0")/.."
export MLFLOW_TRACKING_URI=http://127.0.0.1:5000
export MLFLOW_EXPERIMENT_NAME=llm-mobile
VENV=/home/ubuntu/Miniconda3/envs/train/bin
OUT=checkpoints/qwen3-1.7b-sft17-$(date +%Y%m%d)
LOG="logs/sft17_1.7b.log"
: > "$LOG"

SMOKE_OUT="${OUT}-smoke"
"$VENV/torchrun" --nproc_per_node=2 scripts/train_sft.py \
  --model checkpoints/qwen3-1.7b-pt-20261026/final --tokenizer models/Qwen3-1.7B \
  --data data/train_sft17/train.jsonl --val data/train_sft17/val.jsonl \
  --out "$SMOKE_OUT" \
  --deepspeed scripts/ds_zero2.json --epochs 2 --max-len 2048 \
  --per-device-bs 8 --grad-accum 8 --max-steps 3 --eval-steps 1 --logging-steps 1 \
  --no-think --chunked-ce --overwrite >> "$LOG" 2>&1
RC=$?
if [ $RC -ne 0 ] || ! grep -q "'loss'" "$LOG" || ! grep -q "'eval_loss'" "$LOG"; then
  echo "SMOKE_FAILED rc=$RC 冒烟未通过（loss/eval_loss 必须都出数），停止" >> "$LOG"; exit 1
fi
echo "SMOKE_OK 冒烟通过" >> "$LOG"
[ "${SMOKE_ONLY:-0}" = "1" ] && exit 0

OW="--overwrite"
for attempt in 1 2; do
  echo "===== SFT17 尝试 $attempt $(date '+%F %T') overwrite=[$OW] =====" >> "$LOG"
  "$VENV/torchrun" --nproc_per_node=2 scripts/train_sft.py \
    --model checkpoints/qwen3-1.7b-pt-20261026/final --tokenizer models/Qwen3-1.7B \
    --data data/train_sft17/train.jsonl --val data/train_sft17/val.jsonl \
    --out "$OUT" \
    --deepspeed scripts/ds_zero2.json --epochs 2 --max-len 2048 \
    --per-device-bs 8 --grad-accum 8 --save-steps 500 --logging-steps 10 \
    --eval-steps 500 --no-think --chunked-ce $OW >> "$LOG" 2>&1
  if grep -q "TRAINING_FINISHED" "$LOG"; then
    echo "SFT17_ALL_DONE $(date '+%F %T')" >> "$LOG"
    exit 0
  fi
  # 崩溃：第二次去掉 overwrite（resume 续训）
  OW=""
done
echo "SFT17 两次尝试均失败，现场保留 $(date '+%F %T')" >> "$LOG"
exit 1
