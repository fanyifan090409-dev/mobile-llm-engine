#!/usr/bin/env bash
# PT2 WSD 续训第一段：4B tokens（新打包 fw2b+belleb），seq 4096，WSD 调度（lr 2e-4）。
# 依据：docs/学习材料/续训配方教学-为什么平台期是假的.md（MiniCPM WSD + TMLR replay）
# 不开 torch-compile：实测 compile 会把 chunked CE 分块循环融合成完整 logits
# （seq4096×bs16×152k 词表 ≈20GB），内存墙回归直接 OOM；eager 下分块真实生效。
# 梯度检查点保持默认开启：seq4096×bs16 无检查点时 28 层保存激活累计 ~45GB，
# 直接 OOM（SFT 一直默认开启，此前的 12.6GB 估算是按 seq2048 算的，作废）。
# 自愈：attempt 1 带 overwrite；崩溃则 attempt 2 不带 overwrite（resume）。
set -u
cd "$(dirname "$0")/.."
export MLFLOW_TRACKING_URI=http://127.0.0.1:5000
export MLFLOW_EXPERIMENT_NAME=llm-mobile
VENV=/home/ubuntu/Miniconda3/envs/train/bin
LOG="logs/pt2_wsd.log"
: > "$LOG"

# 冒烟门禁：正式跑前先 3 步验证 seq4096+bs16 显存与 WSD 调度（loss 必须出数）
SMOKE_OUT=checkpoints/qwen3-0.6b-pt2-20261025-smoke
"$VENV/torchrun" --nproc_per_node=2 scripts/train_pt.py \
  --model checkpoints/qwen3-0.6b-pt-20261024/final \
  --data data/pt/fw2b.bin,data/pt/belleb.bin \
  --seq-len 4096 --out "$SMOKE_OUT" \
  --deepspeed scripts/ds_zero2.json \
  --lr 2e-4 --warmup-ratio 0.05 --wsd \
  --per-device-bs 16 --grad-accum 4 \
  --max-steps 3 --save-steps 100000 --logging-steps 1 \
  --chunked-ce --overwrite >> "$LOG" 2>&1
if ! grep -q "'loss'" "$LOG"; then
  echo "SMOKE_FAILED 冒烟无 loss 输出，停止" >> "$LOG"; exit 1
fi
echo "SMOKE_OK 冒烟通过" >> "$LOG"

OW="--overwrite"
for attempt in 1 2; do
  echo "===== PT2 尝试 $attempt $(date '+%F %T') overwrite=[$OW] =====" >> "$LOG"
  "$VENV/torchrun" --nproc_per_node=2 scripts/train_pt.py \
    --model checkpoints/qwen3-0.6b-pt-20261024/final \
    --data data/pt/fw2b.bin,data/pt/belleb.bin \
    --seq-len 4096 --out checkpoints/qwen3-0.6b-pt2-20261025 \
    --deepspeed scripts/ds_zero2.json \
    --lr 2e-4 --warmup-ratio 0.05 --wsd \
    --per-device-bs 16 --grad-accum 4 \
    --max-steps 7630 --save-steps 2000 --logging-steps 10 \
    --chunked-ce $OW >> "$LOG" 2>&1
  if grep -q "TRAINING_FINISHED" "$LOG"; then
    echo "PT2_ALL_DONE $(date '+%F %T')" >> "$LOG"
    exit 0
  fi
  # 崩溃：第二次去掉 overwrite（resume 续训）
  OW=""
done
echo "PT2 两次尝试均失败，现场保留 $(date '+%F %T')" >> "$LOG"
exit 1
