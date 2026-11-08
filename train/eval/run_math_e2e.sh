#!/usr/bin/env bash
# CAS 二期端到端评测：起 llama-server → 模型自行调 math_eval（真实 CAS）→ 判分。
# 用法：bash run_math_e2e.sh <gguf> <port> <tag>   （SCORE=1 出分，PY=... 指定 python）
set -u
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
if [ -x "$ROOT/tools/llama.cpp/build/bin/llama-server" ]; then
  BIN="$ROOT/tools/llama.cpp/build/bin"
else
  BIN="$ROOT/tools/llama_cpp_src/build/bin"
fi
MODEL=$1
PORT=$2
TAG=$3
PY=${PY:-python3}
OUT=${OUTDIR:-$ROOT/eval_tmp/math_e2e/$TAG}
mkdir -p "$OUT"

"$BIN/llama-server" -m "$MODEL" --host 127.0.0.1 --port "$PORT" -ngl 99 --jinja \
  --chat-template-kwargs '{"enable_thinking": false}' -c 8192 \
  > "$OUT/server.log" 2>&1 &
PID=$!
ready=0
for i in $(seq 1 120); do
  if curl -s --max-time 2 "http://127.0.0.1:$PORT/health" >/dev/null 2>&1; then ready=1; break; fi
  sleep 1
done
if [ "$ready" != "1" ]; then
  echo "SERVER_FAILED $TAG" | tee "$OUT/summary.txt"
  kill "$PID" 2>/dev/null
  exit 1
fi
"$PY" "$ROOT/train/eval/eval_math_e2e.py" --model "$MODEL" --port "$PORT" --outdir "$OUT"
RC=$?
kill "$PID" 2>/dev/null
wait "$PID" 2>/dev/null
if [ "${SCORE:-0}" = "1" ]; then
  "$PY" "$ROOT/train/eval/score_math_eval.py" --outputs "$OUT/outputs.json" \
    --eval "$ROOT/train/eval/math_eval.json" --outdir "$OUT"
fi
exit $RC
