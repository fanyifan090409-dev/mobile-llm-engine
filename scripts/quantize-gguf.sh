#!/usr/bin/env bash
# GGUF 量化：钉版 llama-quantize 封装（官方 Q8_0 母本 → 低档量化）
# 背景：官方 Qwen3 GGUF 仓库 0.6B/1.7B 只有 Q8_0 单档，低档量化本地自转
# 用法：quantize-gguf.sh <输入gguf> <输出gguf> <量化档>（Q4_K_M / Q5_K_M / Q6_K / IQ4_XS ...）
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
IN="${1:?用法: quantize-gguf.sh <输入gguf> <输出gguf> <量化档>}"
OUT="${2:?}"
QT="${3:?}"
QTOOL="$ROOT/tools/llama.cpp/build/bin/llama-quantize"
[ -x "$QTOOL" ] || { echo "缺少 $QTOOL（先构建 tools/llama.cpp 钉版）"; exit 1; }
[ -f "$IN" ] || { echo "输入文件不存在：$IN"; exit 1; }
# 新版 llama.cpp 默认禁 requantize（防低档再量化掉质量）；Q8_0→Q4_K_M 是官方推荐路径，显式放行
"$QTOOL" --allow-requantize "$IN" "$OUT" "$QT"
echo "QUANT_DONE $OUT"
