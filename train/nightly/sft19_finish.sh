#!/usr/bin/env bash
# SFT19 收尾：等训练完成 → 训练机 convert f16 → rsync 回 Mac → GGUF 量化 → 工具调用/数学验收
# 用法：bash train/nightly/sft19_finish.sh（建议 setsid nohup 后台跑）
set -u
ROOT=/Users/fanyifan/Documents/Qoder/2026-10-23/90ee63b2
GGUF=$ROOT/train/gguf/qwen3-1.7b-sft19-20261104
LOGD=$ROOT/train/nightly/logs
BIN=$ROOT/tools/llama.cpp/build/bin
SSH="ssh trainer"
REMOTE=/home/ubuntu/llm-mobile
VENVPY=$ROOT/train/nightly/venv/bin/python
DEMO=$ROOT/apps/demo-cli/.build/release/demo-cli
TAG=sft19
mkdir -p "$GGUF" "$LOGD"
TS=$(date +%Y%m%d_%H%M%S)
LOG=$LOGD/sft19_finish_$TS.log
exec >> "$LOG" 2>&1
echo "===== SFT19 收尾链启动 $TS ====="

fail() { echo "FATAL: $*"; exit 1; }

# ---------- 0. 空间与工具自检 ----------
FREE_KB=$(df -k "$ROOT" | awk 'NR==2 {print $4}')
[ "${FREE_KB:-0}" -ge 11000000 ] || fail "本机可用空间不足 11GB（当前 $((FREE_KB/1024/1024))GB），先清理再跑"
[ -x "$BIN/llama-quantize" ] || fail "llama-quantize 未编译"
[ -x "$DEMO" ] || fail "demo-cli release 未编译"
[ -x "$VENVPY" ] || fail "评测 venv 未就绪"
echo "自检 OK，可用空间 $((FREE_KB/1024/1024))GB"

# ---------- 1. 等 SFT19 完成 ----------
for i in $(seq 1 420); do
  if $SSH "grep -q 'SFT19_ALL_DONE' $REMOTE/logs/sft19_1.7b.log 2>/dev/null"; then
    echo "SFT19 训练完成（第 $i 次轮询）"; break
  fi
  if $SSH "grep -q '两次尝试均失败' $REMOTE/logs/sft19_1.7b.log 2>/dev/null"; then
    fail "SFT19 两次尝试均失败"
  fi
  [ "$i" = 420 ] && fail "7 小时内 SFT19 未完成"
  sleep 60
done

CKPT=$REMOTE/checkpoints/qwen3-1.7b-sft19-20261104/final
$SSH "test -d $CKPT" || fail "checkpoint 目录不存在 $CKPT"
$SSH "test -f $CKPT/config.json" || fail "checkpoint 不完整（缺 config.json）"

# ---------- 2. 训练机 convert f16 ----------
REMOTE_F16=$REMOTE/tools/llama_convert/sft19_f16.gguf
if $SSH "test -s $REMOTE_F16"; then
  echo "远端 f16 已存在，跳过 convert"
else
  echo "开始 convert f16（训练机 CPU）"
  $SSH "cd $REMOTE/tools/llama_convert && /home/ubuntu/Miniconda3/envs/train/bin/python convert_hf_to_gguf.py $CKPT --outfile sft19_f16.gguf --outtype f16" \
    || fail "convert 失败"
fi
$SSH "ls -lh $REMOTE_F16" || fail "远端 f16 不存在"
echo "convert f16 完成"

# ---------- 3. rsync f16 回 Mac ----------
LOCAL_F16=$GGUF/qwen3-1.7b-sft19-F16.gguf
if [ -s "$LOCAL_F16" ]; then
  echo "本机 f16 已存在，跳过 rsync"
else
  rsync -a --partial -e ssh "trainer:$REMOTE_F16" "$LOCAL_F16" || fail "rsync f16 失败"
fi
[ -s "$LOCAL_F16" ] || fail "f16 拉取失败"
ls -lh "$LOCAL_F16"

# ---------- 4. GGUF 量化（设备主档 + 对照档） ----------
# 本机装 OpenHands 后只剩 ~13GB；先做三档设备/对照够用的量化，Q6_K/emb8 后续按需补
for type in Q8_0 Q5_K_M Q4_K_M; do
  out=$GGUF/qwen3-1.7b-sft19-$type.gguf
  if [ -s "$out" ]; then
    echo "量化已存在，跳过 $type"
    continue
  fi
  echo "--- 量化 $type ---"
  "$BIN/llama-quantize" "$LOCAL_F16" "$out" "$type" || fail "量化 $type 失败"
  ls -lh "$out"
done

# 量化产物齐全后再删 f16 中间文件，腾出约 4GB
rm -f "$LOCAL_F16"
echo "中间 f16 已删除"

# ---------- 5. 工具调用验收（Q5_K_M 与 Q4_K_M 各 40 题） ----------
for q in Q5_K_M Q4_K_M; do
  model=$GGUF/qwen3-1.7b-sft19-$q.gguf
  [ -s "$model" ] || fail "缺少 $q 量化文件"
  echo "--- 工具调用评测 $q ---"
  "$VENVPY" "$ROOT/train/nightly/eval_toolcall.py" \
    --model "$model" --demo "$DEMO" --quant "$q" --tag "${TAG}_${q}" \
    --prompts all --temp 0 --think-tags \
    --outdir "$ROOT/train/nightly/work/toolcall" || fail "工具调用评测 $q 失败"
done

# ---------- 6. AP Calc BC FRQ 数学验收（Q5_K_M，12 题） ----------
# 先备份 SFT17 旧输出，避免 run_ap_frq_eval.sh 覆盖基线
mkdir -p "$ROOT/train/eval/private/output_sft17_baseline"
cp -n "$ROOT/train/eval/private/output"/answer-*.txt \
  "$ROOT/train/eval/private/output_sft17_baseline/" 2>/dev/null || true
echo "--- AP Calc BC FRQ 评测 Q5_K_M ---"
bash "$ROOT/train/eval/run_ap_frq_eval.sh" \
  "$GGUF/qwen3-1.7b-sft19-Q5_K_M.gguf" Q5_K_M || fail "AP FRQ 评测失败"

echo "SFT19_FINISH_ALL_DONE $(date '+%F %T')"
echo "量化目录：$GGUF"
echo "工具评测：$ROOT/train/nightly/work/toolcall/${TAG}_Q5_K_M、${TAG}_Q4_K_M"
echo "数学输出：$ROOT/train/eval/private/output"
