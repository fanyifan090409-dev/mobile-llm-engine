#!/usr/bin/env bash
# Mac 基准：demo-cli 一次性模式跑四档速度矩阵（M1.5 双 Mac 基准数据源）
# 用法：bench-mac.sh <gguf路径> [quant] [context] [max-tokens]
# 口径与 llama-cli 可比：解码 tok/s、预填充 tok/s、峰值 RSS（mach resident_size_max，
# 与 /usr/bin/time -l 同语义）。每档独立进程（Metal kernel 编译在 load 阶段，不计入统计）。
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

# 环境适配（同 gate.sh）：CLT 缺测试链时临时指到完整 Xcode；构建目录挪出 iCloud 同步区
if ! xcodebuild -version >/dev/null 2>&1 && [ -d /Applications/Xcode.app ]; then
  export DEVELOPER_DIR=/Applications/Xcode.app
fi

MODEL="${1:?用法: bench-mac.sh <gguf> [quant] [context] [max-tokens]}"
QUANT="${2:-Q4_K_M}"
CTX="${3:-4096}"
MAXT="${4:-200}"
SCRATCH="$HOME/.cache/engine-build"

# 固定中文 prompt：双机（M5 Air / M5 Pro）同题可比
PROMPT="请用中文简要介绍杭州西湖的三个著名景点。"

echo "==> $(basename "$MODEL") ($QUANT, ctx $CTX, max-tokens $MAXT, temp 0.7)"
printf "%-12s | %-10s | %-10s | %s\n" "档位" "解码tok/s" "预填充tok/s" "峰值RSS MB"
printf "%-12s-+-%-10s-+-%-10s-+-%s\n" "------------" "----------" "----------" "-----------"

for tier in powerSaver balanced performance turbo; do
  out=$(swift run --scratch-path "$SCRATCH" --package-path "$ROOT/apps/demo-cli" demo-cli \
    --model "$MODEL" --quant "$QUANT" --context "$CTX" --speed "$tier" \
    --max-tokens "$MAXT" --temperature 0.7 -p "$PROMPT" 2>/dev/null) || { echo "$tier: FAIL"; continue; }
  stats=$(printf '%s' "$out" | sed -n 's/.*解码 \([0-9.]*\) tok\/s | 预填充 \([0-9.]*\) tok\/s | 峰值内存 \([0-9]*\) MB.*/\1|\2|\3/p')
  if [ -n "$stats" ]; then
    IFS='|' read -r tps pp rss <<< "$stats"
    printf "%-12s | %-10s | %-10s | %s\n" "$tier" "$tps" "$pp" "$rss"
  else
    printf "%-12s | FAIL（统计行未解析）\n" "$tier"
  fi
done
echo "BENCH_DONE"
