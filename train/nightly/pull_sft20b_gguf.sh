#!/usr/bin/env bash
# 从训练机拉 SFT20b 0.6B Q5/Q4 GGUF 到 Mac，大小校验后落盘
set -u
ROOT=/Users/fanyifan/Documents/Qoder/2026-10-23/90ee63b2
DEST=$ROOT/train/gguf/qwen3-0.6b-sft20b-20261106
SRC=/home/ubuntu/llm-mobile/tools/llama_convert/sft20b_gguf
mkdir -p "$DEST"
for q in Q5_K_M Q4_K_M; do
  f=qwen3-0.6b-sft20b-$q.gguf
  rsync -av --partial-dir=.rsync-partial "trainer:$SRC/$f" "$DEST/$f"
  remote=$(ssh trainer "stat -c%s $SRC/$f")
  local=$(stat -f%z "$DEST/$f")
  if [ "$remote" != "$local" ]; then
    echo "SIZE_MISMATCH $f remote=$remote local=$local"; exit 1
  fi
  echo "OK $f $local bytes"
done
echo PULL_SFT20B_DONE
