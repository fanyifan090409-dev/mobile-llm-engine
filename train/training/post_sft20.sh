#!/usr/bin/env bash
# SFT20 训练后处理：HF checkpoint → F16 GGUF → Q5_K_M / Q4_K_M，量化后删除 F16 中间件
set -u
cd /home/ubuntu/llm-mobile
CONV=/home/ubuntu/Miniconda3/envs/train/bin/python
CVT=tools/llama_convert/convert_hf_to_gguf.py
QUANT=tools/llama_cpp_src/build/bin/llama-quantize
OUT=tools/llama_convert/sft20_gguf
LOG=logs/sft20_convert.log
mkdir -p "$OUT"
: > "$LOG"

run() {
  echo "=== $* ===" >> "$LOG"
  "$@" >> "$LOG" 2>&1 || { echo "FAILED: $*" >> "$LOG"; exit 1; }
}

for pair in "qwen3-1.7b-sft20-20261106:qwen3-1.7b-sft20" "qwen3-0.6b-sft20-20261106:qwen3-0.6b-sft20"; do
  dir=${pair%%:*}
  name=${pair##*:}
  F16=$OUT/${name}-F16.gguf
  [ -s "$F16" ] || run $CONV $CVT checkpoints/$dir/final --outfile "$F16" --outtype f16
  for q in Q5_K_M Q4_K_M; do
    [ -s "$OUT/${name}-${q}.gguf" ] || run $QUANT "$F16" "$OUT/${name}-${q}.gguf" $q
  done
  rm -f "$F16"
  echo "MODEL_DONE $name" >> "$LOG"
done
echo POST_DONE >> "$LOG"
