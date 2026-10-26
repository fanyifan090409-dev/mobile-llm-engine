#!/usr/bin/env bash
# 合成后接管（唯一执行者）：质检 → 优雅下线双 teacher → 写 SYNTH_DONE.supp17 → 启动 1.7B PT。
# 被 watch_synth17.sh（正常路径）与 cron 兜底（看护死亡路径）共同调用；
# mkdir 锁保证全局只执行一次。teacher 下线用 pgrep 取 PID + kill -TERM（绝不 pkill -f）。
set -u
cd /home/ubuntu/llm-mobile
MARKER=data/sft/SYNTH_DONE.supp17
LOCK=/tmp/synth17_takeover.lock
LOG=logs/watch_synth17.log

[ -f "$MARKER" ] && { echo "$(date '+%F %T') TAKEOVER: 标记已存在，跳过"; exit 0; }
mkdir "$LOCK" 2>/dev/null || { echo "$(date '+%F %T') TAKEOVER: 锁被持有，跳过"; exit 0; }
echo "$(date '+%F %T') TAKEOVER: 开始接管（合成已完成）" >> "$LOG"

# 1) 质检（结果进标记，不进退出码判定——合成脚本自己已写 meta.json）
/home/ubuntu/Miniconda3/envs/train/bin/python3 scripts/qc_sft.py --dir data/sft --samples 5 \
  > data/sft/qc_report_supp17.txt 2>&1 || true

# 2) 优雅下线双 teacher：pgrep 精确匹配 vllm 端口命令行，取 PID 逐个 TERM
for port in 8002 8003; do
  pid=$(pgrep -f "vllm.*--port $port" | head -1)
  if [ -n "$pid" ]; then
    kill -TERM "$pid"
    echo "$(date '+%F %T') TAKEOVER: teacher :$port PID $pid 已发 TERM" >> "$LOG"
  fi
done

# 3) 等端口关闭（vLLM 卸载权重需 ~30-60s，最多等 2 分钟）
for i in $(seq 1 24); do
  left=$(ss -tln | grep -cE ":8002|:8003" || true)
  [ "$left" = "0" ] && break
  sleep 5
done

# 4) 确认双卡显存释放再进训练（防 PT 与残留进程抢卡）
gpu_ok=0
for i in $(seq 1 24); do
  used=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader | grep -o '[0-9]*' | sort -n | tail -1)
  [ -n "$used" ] && [ "$used" -lt 1024 ] && { gpu_ok=1; break; }
  sleep 5
done

# 5) 写完成标记（含质检与现场快照，供复盘）
{
  echo "supp17_finished_at=$(date '+%Y-%m-%d %H:%M:%S')"
  echo "--- meta.json ---"
  cat data/sft/meta.json 2>/dev/null || echo "(无 meta.json —— 合成可能未正常收尾)"
  echo "--- 合成日志尾部 ---"
  tail -5 logs/synthesize_supp17.log 2>/dev/null
  echo "--- qc_report ---"
  cat data/sft/qc_report_supp17.txt 2>/dev/null
  echo "gpu_free_check=$gpu_ok"
} > "$MARKER"

if [ "$gpu_ok" != "1" ]; then
  echo "$(date '+%F %T') TAKEOVER: GPU 未释放，不启动 PT（标记已写，需人工介入）" >> "$LOG"
  rmdir "$LOCK" 2>/dev/null
  exit 2
fi

# 6) 启动 1.7B PT（脚本自带冒烟门禁 + 自愈 attempts，冒烟已提前独立验证过）
tmux new-session -d -s pt17 'cd /home/ubuntu/llm-mobile && bash scripts/run_pt2_1.7b.sh'
echo "$(date '+%F %T') TAKEOVER: PT 已启动（tmux 会话 pt17），接管完成" >> "$LOG"
rmdir "$LOCK" 2>/dev/null
