#!/usr/bin/env bash
# 合成完成看护：等待 synthesize_sft.py 退出 → 自动质检 → 写 SYNTH_DONE 标记
# 用法：cd /home/ubuntu/llm-mobile && nohup bash scripts/watch_synth.sh > logs/watch_synth.log 2>&1 &
set -u
cd /home/ubuntu/llm-mobile
DONE=data/sft/SYNTH_DONE
if [ -f "$DONE" ]; then
  echo "$(date '+%F %T') SYNTH_DONE 已存在，看护退出"
  exit 0
fi

while pgrep -f "synthesize_sft.py --target-tokens" >/dev/null 2>&1; do
  sleep 300
done

echo "$(date '+%F %T') 合成进程已退出，开始质检"
/home/ubuntu/Miniconda3/envs/vlm/bin/python3 scripts/qc_sft.py --dir data/sft --samples 5 \
  > data/sft/qc_report.txt 2>&1

{
  echo "watched_finished_at=$(date '+%Y-%m-%d %H:%M:%S')"
  echo "--- meta.json ---"
  cat data/sft/meta.json 2>/dev/null || echo "(无 meta.json —— 合成可能未正常收尾)"
  echo "--- log tail ---"
  tail -5 logs/synthesize.log
  echo "--- qc_report ---"
  cat data/sft/qc_report.txt
} > "$DONE"
echo "$(date '+%F %T') 看护完成，标记已写 $DONE"
