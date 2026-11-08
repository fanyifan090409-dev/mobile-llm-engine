#!/usr/bin/env bash
# 训练机侧评测：SFT20d Q5，60 题日期 + 16 题边界。不依赖 Mac 路径。
set -u
BASE=/home/ubuntu/llm-mobile
BIN=$BASE/tools/llama_cpp_src/build/bin/llama-server
MODEL=$BASE/tools/llama_convert/sft20d_gguf/qwen3-0.6b-sft20d-Q5_K_M.gguf
PORT=8124
TAG=sft20d-q5
OUT=$BASE/eval_tmp/$TAG
mkdir -p "$OUT"
"$BIN" -m "$MODEL" --host 127.0.0.1 --port "$PORT" -ngl 99 --jinja \
  --chat-template-kwargs '{"enable_thinking": false}' -c 4096 \
  > "$OUT/server.log" 2>&1 &
PID=$!
ready=0
for i in $(seq 1 120); do
  if curl -s --max-time 2 "http://127.0.0.1:$PORT/health" >/dev/null 2>&1; then ready=1; break; fi
  sleep 1
done
if [ "$ready" != "1" ]; then
  echo "SERVER_FAILED" | tee "$OUT/summary.txt"
  kill "$PID" 2>/dev/null
  exit 1
fi
python3 "$BASE/eval_tmp/eval_date_worker.py" --model "$MODEL" --port "$PORT" \
  --outdir "$OUT/date60" --eval-file "$BASE/eval_tmp/date_worker_eval.json" > "$OUT/date60.log" 2>&1
RC1=$?
python3 "$BASE/eval_tmp/eval_date_worker.py" --model "$MODEL" --port "$PORT" \
  --outdir "$OUT/edges16" --eval-file "$BASE/eval_tmp/date_worker_edges_eval.json" > "$OUT/edges16.log" 2>&1
RC2=$?
kill "$PID" 2>/dev/null
wait "$PID" 2>/dev/null
echo "DATE60_RC=$RC1 EDGES16_RC=$RC2" | tee "$OUT/summary.txt"
grep -E "准确|精确|合计|通过|ACC|acc" "$OUT/date60.log" | tail -5 | tee -a "$OUT/summary.txt"
grep -E "准确|精确|合计|通过|ACC|acc" "$OUT/edges16.log" | tail -5 | tee -a "$OUT/summary.txt"
