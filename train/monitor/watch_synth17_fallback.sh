#!/usr/bin/env bash
# cron 兜底（每 15 分钟）：看护进程自身死亡时接管（踩坑#6 防再犯）。
# 判定：心跳超时（>20 分钟）且合成已结束且标记未写 → 调接管脚本（锁防并发）。
# 合成仍在跑时只记录心跳超时，不杀合成（数据安全第一）。
set -u
cd /home/ubuntu/llm-mobile
HB=logs/watch_synth17.heartbeat
MARKER=data/sft/SYNTH_DONE.supp17
LOG=logs/watch_synth17.log

[ -f "$MARKER" ] && exit 0
[ -f "$HB" ] || HB_AGE=99999
[ -n "${HB_AGE:-}" ] || HB_AGE=$(( $(date +%s) - $(stat -c %Y "$HB") ))

if pgrep -f "synthesize_sft.py --target-tokens 17000000" >/dev/null 2>&1; then
  # 合成在跑：心跳新鲜=正常；心跳超时=看护已死，记录留证（不接管，等合成自然结束）
  if [ "$HB_AGE" -gt 1200 ]; then
    echo "$(date '+%F %T') FALLBACK17: 合成在跑但看护心跳超时 ${HB_AGE}s（看护进程可能已死）" >> "$LOG"
  fi
  exit 0
fi
# 合成已结束：心跳新鲜=看护会接管；心跳超时=兜底接管
if [ "$HB_AGE" -le 1200 ]; then
  exit 0
fi
echo "$(date '+%F %T') FALLBACK17: 看护死亡且合成已结束，兜底接管" >> "$LOG"
bash scripts/takeover_after_synth17.sh >> "$LOG" 2>&1
