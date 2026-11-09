#!/usr/bin/env bash
# SFT27e CAS v5（limit）收尾：HF final -> F16 GGUF -> Q5_K_M / Q4_K_M
set -u
cd /home/ubuntu/llm-mobile
CONV=/home/ubuntu/Miniconda3/envs/train/bin/python
CVT=tools/llama_convert/convert_hf_to_gguf.py
QUANT=tools/llama_cpp_src/build/bin/llama-quantize
OUT=tools/llama_convert/sft27f_cas_gguf
LOG=logs/sft27f_cas_convert.log
mkdir -p "$OUT"
: > "$LOG"
run() { echo "=== $* ===" >> "$LOG"; "$@" >> "$LOG" 2>&1 || { echo "FAILED: $*" >> "$LOG"; exit 1; }; }
dir=$(cat logs/sft27f_cas.outdir 2>/dev/null || echo checkpoints/qwen3-1.7b-sft27f-cas-20261109)
name=qwen3-1.7b-sft27f-cas
F16=$OUT/${name}-F16.gguf
[ -s "$F16" ] || run $CONV $CVT "$dir/final" --outfile "$F16" --outtype f16
for q in Q5_K_M Q4_K_M; do
  [ -s "$OUT/${name}-${q}.gguf" ] || run $QUANT "$F16" "$OUT/${name}-${q}.gguf" $q
done
rm -f "$F16"
echo "MODEL_DONE $name" >> "$LOG"
echo POST_DONE >> "$LOG"
