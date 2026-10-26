#!/usr/bin/env bash
# 看护：PT2 收段后自动接 SFT2 → convert f16 GGUF → 打完成标记（Mac 侧轮询取货）。
# 训练机 tmux 运行：tmux new -s sft2-watch "bash scripts/watch_sft2.sh"
set -u
cd "$(dirname "$0")/.."
PTLOG="logs/pt2_wsd.log"
SFTLOG="logs/sft2_0.6b.log"
CVT_DIR="tools/llama_convert"
DONE="$CVT_DIR/sft2_f16.done"
LOG="logs/watch_sft2.log"

log() { echo "$(date '+%F %T') $*" >> "$LOG"; }

# ---- 阶段 1：等 PT2 收段 ----
log "开始等 PT2 收段"
while true; do
  if grep -q "PT2_ALL_DONE" "$PTLOG" 2>/dev/null; then
    log "PT2 完成，启动 SFT2"
    break
  fi
  if grep -q "两次尝试均失败" "$PTLOG" 2>/dev/null; then
    log "PT2 失败！人工介入，看护退出"
    exit 1
  fi
  sleep 300
done

bash scripts/run_sft2.sh
RC=$?
if [ "$RC" != 0 ]; then
  log "SFT2 失败 RC=$RC，人工介入，看护退出"
  exit 1
fi
log "SFT2 完成"

# ---- 阶段 2：convert f16 GGUF ----
# 训练机铁律：动东西前备份 convert 目录里的旧产物清单（避免覆盖误删）
ls -la "$CVT_DIR" > "$CVT_DIR/.backup_before_sft2_$(date +%F_%H%M).txt" 2>/dev/null
cd "$CVT_DIR"
/home/ubuntu/Miniconda3/envs/train/bin/python convert_hf_to_gguf.py \
  /home/ubuntu/llm-mobile/checkpoints/qwen3-0.6b-sft2-20261026/final \
  --outfile sft2_f16.gguf --outtype f16 >> ../"$LOG" 2>&1
if [ ! -s sft2_f16.gguf ]; then
  log "convert 失败，人工介入"
  exit 1
fi
log "convert 完成 $(ls -la sft2_f16.gguf | awk '{print $5}') 字节"

# ---- 阶段 3：完成标记（Mac 轮询触发取货）----
touch "$DONE"
log "ALL_DONE 完成标记已打"
