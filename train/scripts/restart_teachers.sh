#!/bin/bash
# 训练机双 teacher 恢复脚本（比赛演示/合成前用）
# 用法：scp 到训练机后 bash restart_teachers.sh
# 前提：双卡空闲（训练结束且显存已释放）；LiteLLM :4000 保持运行无需操作
set -e

VLLM=/home/ubuntu/Miniconda3/envs/vlm/bin/vllm

# 8002：27B（GPU0）
tmux new-session -d -s teach27
tmux send-keys -t teach27 \
  "CUDA_VISIBLE_DEVICES=0 VLLM_USE_FLASHINFER_SAMPLER=0 $VLLM serve \
   /home/ubuntu/isef/models/Huihui-Qwen3.8-27B-abliterated \
   --served-model-name qwen3.8-27b --host 0.0.0.0 --port 8002 \
   --quantization bitsandbytes --load-format bitsandbytes \
   --gpu-memory-utilization 0.80 --max-model-len 32768 --enforce-eager \
   --allowed-local-media-path /home/ubuntu/isef \
   --enable-auto-tool-choice --tool-call-parser qwen3_xml --reasoning-parser qwen3" Enter

# 8003：30B-A3B GPTQ（GPU1）
tmux new-session -d -s teach30
tmux send-keys -t teach30 \
  "CUDA_VISIBLE_DEVICES=1 VLLM_USE_FLASHINFER_SAMPLER=0 $VLLM serve \
   /home/ubuntu/isef/models/Qwen3-30B-A3B-abliterated-GPTQ \
   --served-model-name qwen3-coder --host 0.0.0.0 --port 8003 \
   --quantization gptq_marlin --gpu-memory-utilization 0.80 --max-model-len 32768 \
   --enforce-eager --allowed-local-media-path /home/ubuntu/isef \
   --enable-auto-tool-choice --reasoning-parser qwen3 --tool-call-parser qwen3_xml" Enter

echo "已拉起 teach27(8002) / teach30(8003)，启动约 1-2 分钟；查看：tmux attach -t teach27"
echo "健康检查：curl -s http://127.0.0.1:8002/v1/models 和 :8003"
