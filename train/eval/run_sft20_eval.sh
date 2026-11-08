#!/usr/bin/env bash
# 用法：bash run_sft20_eval.sh <gguf> <leader|worker> <port> <tag>
set -u
ROOT=/Users/fanyifan/Documents/Qoder/2026-10-23/90ee63b2
BIN=$ROOT/tools/llama.cpp/build/bin
MODEL=$1
ROLE=$2
PORT=$3
TAG=$4
OUT=$ROOT/train/nightly/work/sft20_dispatch/$TAG
mkdir -p "$OUT"

"$BIN/llama-server" -m "$MODEL" --host 127.0.0.1 --port "$PORT" -ngl 99 --jinja --chat-template-kwargs '{"enable_thinking": false}' -c 8192 \
  > "$OUT/server.log" 2>&1 &
PID=$!
ready=0
for i in $(seq 1 90); do
  if curl -s --max-time 2 "http://127.0.0.1:$PORT/health" >/dev/null 2>&1; then ready=1; break; fi
  sleep 1
done
if [ "$ready" != "1" ]; then
  echo "SERVER_FAILED $TAG" | tee "$OUT/summary.txt"
  kill "$PID" 2>/dev/null
  exit 1
fi

python3 "$ROOT/train/eval/eval_sft20_dispatch.py" \
  --model "$MODEL" --role "$ROLE" --port "$PORT" --outdir "$OUT"
RC=$?
kill "$PID" 2>/dev/null
wait "$PID" 2>/dev/null
exit $RC
