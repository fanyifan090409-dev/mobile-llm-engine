#!/usr/bin/env bash
# SFT20 双线串行：先工人线（0.6B，快），再领队线（1.7B）。
# 工人线失败不阻塞领队线；两线各自的详细日志见 logs/sft20_0.6b.log / logs/sft20_1.7b.log。
set -u
cd "$(dirname "$0")/.."
LOG=logs/sft20_all.log
echo "===== SFT20 双线串行启动 $(date '+%F %T') =====" >> "$LOG"

if bash scripts/run_sft20_worker.sh; then
  echo "WORKER_OK $(date '+%F %T')" >> "$LOG"
else
  echo "WORKER_FAILED，继续跑领队线 $(date '+%F %T')" >> "$LOG"
fi

if bash scripts/run_sft20_leader.sh; then
  echo "SFT20_ALL_DONE $(date '+%F %T')" >> "$LOG"
else
  echo "SFT20_LEADER_FAILED $(date '+%F %T')" >> "$LOG"
fi
