#!/usr/bin/env bash
# 训练看护：每 300s 记录 GPU 温度/占用、训练进程、日志尾 → logs/watch_train.log
while true; do
  {
    date "+%F %T"
    nvidia-smi --query-gpu=index,temperature.gpu,utilization.gpu,memory.used --format=csv,noheader
    pgrep -af "train_p[t]|train_sf[t]" | head -3 || echo "no training process"
    echo "--- STATUS ---"
    cat /home/ubuntu/llm-mobile/logs/STATUS.txt 2>/dev/null
    echo "--- 最新 loss ---"
    tail -n 40 /home/ubuntu/llm-mobile/logs/pt_0.6b.log 2>/dev/null | grep -E "loss" | tail -1
    tail -n 40 /home/ubuntu/llm-mobile/logs/sft_0.6b.log 2>/dev/null | grep -E "loss" | tail -1
    echo "--- runner ---"
    tail -n 2 /home/ubuntu/llm-mobile/logs/run_0.6b.log 2>/dev/null
    echo
  } >> /home/ubuntu/llm-mobile/logs/watch_train.log 2>&1
  sleep 300
done
