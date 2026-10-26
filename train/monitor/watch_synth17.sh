#!/usr/bin/env bash
# 补合成看护（1.7B 线）：等 synthesize_sft.py --target-tokens 17000000 退出 → 调接管脚本。
# 心跳文件 logs/watch_synth17.heartbeat 每轮刷新；看护自身死亡时由 cron 兜底
# watch_synth17_fallback.sh 检测心跳超时并接管（踩坑#6：看护进程死亡=轮询链盲区）。
set -u
cd /home/ubuntu/llm-mobile
HB=logs/watch_synth17.heartbeat
MARKER=data/sft/SYNTH_DONE.supp17
LOG=logs/watch_synth17.log

if [ -f "$MARKER" ]; then
  echo "$(date '+%F %T') WATCH17: 标记已存在，看护退出"; exit 0
fi

touch "$HB"
# 上限 48h（17M @ 实测 ~350tok/s ≈ 13.5h，留足余量）
DEADLINE=$(( $(date +%s) + 48*3600 ))
while pgrep -f "synthesize_sft.py --target-tokens 17000000" >/dev/null 2>&1; do
  if [ "$(date +%s)" -ge "$DEADLINE" ]; then
    echo "$(date '+%F %T') WATCH17: 合成 48h 未完成，放弃接管（teacher 保持在线，需人工介入）" >> "$LOG"
    exit 3
  fi
  touch "$HB"
  sleep 300
done
touch "$HB"
echo "$(date '+%F %T') WATCH17: 合成进程已退出，调用接管" >> "$LOG"
bash scripts/takeover_after_synth17.sh >> "$LOG" 2>&1
