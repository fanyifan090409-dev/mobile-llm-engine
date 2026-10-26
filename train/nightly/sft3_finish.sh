#!/usr/bin/env bash
# SFT3B 收尾链：等训练完成 → 训练机 convert f16 → rsync 回 Mac → Q5_K_M 量化 → 遵循率评测
# 用法：bash train/nightly/sft3_finish.sh   （后台跑，训练约 20 分钟 + 后续约 20 分钟）
set -u
ROOT=/Users/fanyifan/Documents/Qoder/2026-10-23/90ee63b2
GGUF=$ROOT/train/gguf/qwen3-0.6b-sft3b-20261026
LOGD=$ROOT/train/nightly/logs
BIN=$ROOT/tools/llama.cpp/build/bin
SSH="ssh trainer"
REMOTE=/home/ubuntu/llm-mobile
VENVPY=$ROOT/train/nightly/venv/bin/python
DEMO=$ROOT/apps/demo-cli/.build/release/demo-cli
mkdir -p "$GGUF" "$LOGD"
TS=$(date +%Y%m%d_%H%M%S)
LOG=$LOGD/sft3_finish_$TS.log
exec >> "$LOG" 2>&1
echo "===== SFT3B 收尾链启动 $TS ====="

# ---------- 1. 等训练完成 ----------
for i in $(seq 1 90); do
  if $SSH "grep -q 'TRAINING_FINISHED' $REMOTE/logs/sft3b_0.6b.log 2>/dev/null"; then
    echo "SFT3B 训练完成（第 $i 次轮询）"; break
  fi
  if $SSH "grep -q '两次尝试均失败' $REMOTE/logs/sft3b_0.6b.log 2>/dev/null"; then
    echo "FATAL: SFT3B 两次尝试均失败，停止"; exit 1
  fi
  [ "$i" = 90 ] && { echo "FATAL: 90 分钟内 SFT3B 未完成，停止"; exit 1; }
  sleep 60
done

# ---------- 2. 训练机 convert f16 ----------
CKPT=$REMOTE/checkpoints/qwen3-0.6b-sft3b-20261026/final
$SSH "test -d $CKPT" || { echo "FATAL: checkpoint 目录不存在 $CKPT"; exit 1; }
if ! $SSH "test -f $REMOTE/tools/llama_convert/sft3b_f16.gguf"; then
  $SSH "cd $REMOTE/tools/llama_convert && /home/ubuntu/Miniconda3/envs/train/bin/python convert_hf_to_gguf.py $CKPT --outfile sft3b_f16.gguf --outtype f16" \
    || { echo "FATAL: convert 失败"; exit 1; }
fi
echo "convert f16 完成"

# ---------- 3. rsync f16 回 Mac ----------
rsync -a --partial -e ssh "trainer:$REMOTE/tools/llama_convert/sft3b_f16.gguf" "$GGUF/qwen3-0.6b-sft3b-F16.gguf"
ls -la "$GGUF/qwen3-0.6b-sft3b-F16.gguf" || { echo "FATAL: f16 拉取失败"; exit 1; }

# ---------- 4. Q5_K_M 量化 ----------
"$BIN/llama-quantize" "$GGUF/qwen3-0.6b-sft3b-F16.gguf" "$GGUF/qwen3-0.6b-sft3b-Q5_K_M.gguf" Q5_K_M \
  && ls -la "$GGUF/qwen3-0.6b-sft3b-Q5_K_M.gguf" || { echo "FATAL: Q5_K_M 量化失败"; exit 1; }

# ---------- 5. 遵循率评测（40 题：30 训练分布 + 10 泛化）----------
$VENVPY $ROOT/train/nightly/eval_toolcall.py \
  --model "$GGUF/qwen3-0.6b-sft3b-Q5_K_M.gguf" --demo "$DEMO" \
  --tag sft3b_q5km --prompts all --think-tags
echo "SFT3_FINISH_ALL_DONE $(date '+%F %T')"
