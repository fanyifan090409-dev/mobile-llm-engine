#!/usr/bin/env bash
# PT 1.7B 续训：5B tokens = 9537 步（seq4096×bs8×2卡×accum8 = 524288 tokens/步），WSD 调度。
# 配置镜像 run_pt2_wsd.sh（同一语料 fw2b+belleb 保证 0.6B/1.7B 可比，已验证 32h 零中断的成熟路径），
# 变化点：模型 Qwen3-1.7B（Instruct 权重续训，与 0.6B 线口径一致）、bs16→bs8（1.7B 显存墙实测
# OOM，bs8×accum8 保持 tokens/步不变）、步数、checkpoint 目录、验证集（val-windows 128 +
# eval-steps 1000，eval_loss 轨迹进 MLflow 与日志尾部汇总）。
# 不开 torch-compile：compile 会把 chunked CE 分块循环融合成完整 logits 内存墙回归 OOM（PT2 已实证）。
# SMOKE_ONLY=1 只跑冒烟：合成开始前先在空闲双卡验证 1.7B 显存与 WSD 调度，不进无人值守链。
set -u
cd "$(dirname "$0")/.."
export MLFLOW_TRACKING_URI=http://127.0.0.1:5000
export MLFLOW_EXPERIMENT_NAME=llm-mobile
VENV=/home/ubuntu/Miniconda3/envs/train/bin
# expandable_segments：1.7B 显存贴边（bs8 训练步实测出现过碎片化分配警告），
# 允许分配器按需扩展段，降低 9537 步长跑中随机 OOM 的概率
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
LOG="logs/pt2_1.7b.log"
: > "$LOG"

MODEL=models/Qwen3-1.7B
OUT=checkpoints/qwen3-1.7b-pt-20261026
DATA=data/pt/fw2b.bin,data/pt/belleb.bin

# 冒烟门禁：3 步验证 1.7B 显存与 WSD 调度（torchrun 退出码 + loss/eval_loss 三闸，
# 实测教训：bs16 OOM 时 loss 已出数、仅 grep 会假阳性，必须看退出码；
# eval_steps=1 让验证路径在冒烟里真实跑一遍——首次执行的路径不进无人值守链）
SMOKE_OUT=checkpoints/qwen3-1.7b-pt-20261026-smoke
"$VENV/torchrun" --nproc_per_node=2 scripts/train_pt.py \
  --model "$MODEL" --data "$DATA" \
  --seq-len 4096 --out "$SMOKE_OUT" \
  --deepspeed scripts/ds_zero2.json \
  --lr 2e-4 --warmup-ratio 0.05 --wsd \
  --per-device-bs 8 --grad-accum 8 \
  --max-steps 3 --save-steps 100000 --logging-steps 1 \
  --val-windows 8 --eval-steps 1 \
  --chunked-ce --overwrite >> "$LOG" 2>&1
RC=$?
if [ $RC -ne 0 ] || ! grep -q "'loss'" "$LOG" || ! grep -q "'eval_loss'" "$LOG"; then
  echo "SMOKE_FAILED rc=$RC 冒烟未通过（loss/eval_loss 必须都出数），停止" >> "$LOG"; exit 1
fi
echo "SMOKE_OK 冒烟通过" >> "$LOG"
[ "${SMOKE_ONLY:-0}" = "1" ] && exit 0

OW="--overwrite"
for attempt in 1 2; do
  echo "===== PT-1.7B 尝试 $attempt $(date '+%F %T') overwrite=[$OW] =====" >> "$LOG"
  "$VENV/torchrun" --nproc_per_node=2 scripts/train_pt.py \
    --model "$MODEL" --data "$DATA" \
    --seq-len 4096 --out "$OUT" \
    --deepspeed scripts/ds_zero2.json \
    --lr 2e-4 --warmup-ratio 0.05 --wsd \
    --per-device-bs 8 --grad-accum 8 \
    --max-steps 9537 --save-steps 2000 --logging-steps 10 \
    --val-windows 128 --eval-steps 1000 \
    --chunked-ce $OW >> "$LOG" 2>&1
  if grep -q "TRAINING_FINISHED" "$LOG"; then
    echo "PT17_ALL_DONE $(date '+%F %T')" >> "$LOG"
    echo "--- eval_loss 轨迹（最后 10 条） ---" >> "$LOG"
    grep -o "'eval_loss': '[0-9.]*'" "$LOG" | tail -10 >> "$LOG"
    exit 0
  fi
  # 崩溃：第二次去掉 overwrite（resume 续训）
  OW=""
done
echo "PT-1.7B 两次尝试均失败，现场保留 $(date '+%F %T')" >> "$LOG"
exit 1
