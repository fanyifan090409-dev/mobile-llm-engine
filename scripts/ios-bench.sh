#!/usr/bin/env bash
# iOS 真机跑分编排：钉档 → 清日志（哨兵校验）→ 触发 → 启动 → 轮询 → 归档
# 用法: bash scripts/ios-bench.sh <档位或完整 .gguf 文件名> [冷却秒数]
#   例: bash scripts/ios-bench.sh Q4_K_M 300
#       bash scripts/ios-bench.sh qwen3-0.6b-sft3b-Q5_K_M.gguf 300
# 前置: EngineShell 已安装；模型已在 App 容器 Documents/Models 或 App 内置 Models
# 证据: /tmp/iosbench/engine-shell-<档位>.log；结束自动清空 bench.run 与 quant.txt 回到默认档
set -uo pipefail

DEV=${DEVICECTL:-/Applications/Xcode.app/Contents/Developer/usr/bin/devicectl}
UDID=${IOS_UDID:-00008150-001504390C69401C}
BUNDLE=${IOS_BUNDLE:-com.enginekit.ios-shell}
ARG=${1:?需要档位参数（Q4_K_M / Q5_K_M / Q8_0 或完整 .gguf 文件名）}
COOLDOWN=${2:-0}
OUT=${IOS_BENCH_OUT:-/tmp/iosbench}
STAMP=$(date +%s)
mkdir -p "$OUT"

if [[ "$ARG" == *.gguf ]]; then
  MODEL_FILE="$ARG"
  LABEL="${ARG%.gguf}"
else
  MODEL_FILE="qwen3-1.7b-sft17-$ARG.gguf"
  LABEL="$ARG"
fi

copy_to() {
  "$DEV" device copy to --device "$UDID" --domain-type appDataContainer \
    --domain-identifier "$BUNDLE" --source "$1" --destination "$2"
}
pull() {
  rm -f "$2"
  "$DEV" device copy from --device "$UDID" --domain-type appDataContainer \
    --domain-identifier "$BUNDLE" --source "$1" --destination "$2"
}
# 任何退出路径都清掉触发与钉档，避免下次启动误重跑、演示回默认档
cleanup() {
  printf '\n' > "$OUT/bench.run"
  copy_to "$OUT/bench.run" Documents/bench.run >/dev/null 2>&1 || true
  printf '\n' > "$OUT/quant.txt"
  copy_to "$OUT/quant.txt" Documents/quant.txt >/dev/null 2>&1 || true
}
trap cleanup EXIT

if [ "$COOLDOWN" -gt 0 ]; then echo "冷却 $COOLDOWN 秒..."; sleep "$COOLDOWN"; fi

PID=$("$DEV" device info processes --device "$UDID" 2>/dev/null \
  | awk '/EngineShell.app/ && $1 ~ /^[0-9]+$/ {print $1; exit}')
if [ -n "${PID:-}" ]; then
  "$DEV" device process signal --device "$UDID" --pid "$PID" --signal SIGKILL >/dev/null 2>&1 || true
  echo "已终止旧实例 PID=$PID"
  sleep 2
fi

printf '%s' "$MODEL_FILE" > "$OUT/quant.txt"
copy_to "$OUT/quant.txt" Documents/quant.txt >/dev/null
pull Documents/quant.txt "$OUT/quant.check.$STAMP"
grep -q "$MODEL_FILE" "$OUT/quant.check.$STAMP" || { echo "❌ 档位钉选失败"; exit 1; }

# 空文件会被 devicectl 判为「未修改」而跳过，清日志必须写非空哨兵并回读校验
printf 'CLEARED-BY-IOS-BENCH\n' > "$OUT/clear.log"
copy_to "$OUT/clear.log" Documents/engine-shell.log >/dev/null
pull Documents/engine-shell.log "$OUT/clear.check.$STAMP"
head -1 "$OUT/clear.check.$STAMP" | grep -q "CLEARED-BY-IOS-BENCH" || { echo "❌ 日志清空失败"; exit 1; }

printf 'go' > "$OUT/bench.run"
copy_to "$OUT/bench.run" Documents/bench.run >/dev/null
pull Documents/bench.run "$OUT/bench.check.$STAMP"
grep -q "go" "$OUT/bench.check.$STAMP" || { echo "❌ 跑分触发失败"; exit 1; }

echo "启动 $LABEL 跑分..."
"$DEV" device process launch --device "$UDID" "$BUNDLE" 2>&1 | tail -1

for i in $(seq 1 50); do
  sleep 30
  pull Documents/engine-shell.log "$OUT/latest-$STAMP.log"
  if grep -q "BENCH-DONE" "$OUT/latest-$STAMP.log"; then
    if ! grep -q "$MODEL_FILE" "$OUT/latest-$STAMP.log"; then
      echo "❌ 实际加载模型与钉选档位不符："
      grep "模型路径" "$OUT/latest-$STAMP.log" | tail -1
      exit 1
    fi
    cp "$OUT/latest-$STAMP.log" "$OUT/engine-shell-$LABEL.log"
    echo "===== $LABEL 结果（第 $i 次轮询）====="
    grep -E "统计：|BENCH|模型路径|设备：" "$OUT/engine-shell-$LABEL.log"
    exit 0
  fi
done
echo "❌ 超时：$LABEL 跑分 25 分钟未完成"
grep -E "统计：|BENCH|失败|错误" "$OUT/latest-$STAMP.log" 2>/dev/null | tail -10
exit 1
