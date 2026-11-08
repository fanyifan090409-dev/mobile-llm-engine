#!/usr/bin/env bash
# 从训练机拉取 SFT19 量化 GGUF（先 Q5_K_M 后 Q4_K_M），支持断点续传
set -u
ROOT=/Users/fanyifan/Documents/Qoder/2026-10-23/90ee63b2
SRC=/home/ubuntu/llm-mobile/tools/llama_convert/sft19_gguf
DEST=$ROOT/train/gguf/qwen3-1.7b-sft19-20261104
mkdir -p "$DEST"
for f in qwen3-1.7b-sft19-Q5_K_M.gguf qwen3-1.7b-sft19-Q4_K_M.gguf; do
  if [ -s "$DEST/$f" ]; then
    echo "已存在，跳过 $f"
    continue
  fi
  echo "--- 拉取 $f $(date '+%F %T') ---"
  rsync -a --partial-dir=.rsync-partial -e ssh "trainer:$SRC/$f" "$DEST/$f" || { echo "FATAL: 拉取 $f 失败"; exit 1; }
  ls -lh "$DEST/$f"
done
echo "PULL_ALL_DONE $(date '+%F %T')"
