#!/usr/bin/env bash
# 0.6B 全链自动跑：语料打包 → 冒烟 → 续训 2.2B tokens → SFT 2 epochs（失败即停）
set -euo pipefail
export HF_ENDPOINT=https://hf-mirror.com
export MLFLOW_TRACKING_URI=http://127.0.0.1:5000
export MLFLOW_EXPERIMENT_NAME="llm-mobile"
export TOKENIZERS_PARALLELISM=false
cd /home/ubuntu/llm-mobile
VENV=/home/ubuntu/Miniconda3/envs/train/bin
mkdir -p logs data/pt checkpoints

phase() { echo "$1" | tee logs/STATUS.txt; }

phase "phase=prepare-语料打包 $(date '+%F %T')"
echo "===== [1/4] prepare 续训语料 $(date '+%F %T') ====="
[ -f data/pt/belle.bin ] || "$VENV/python" scripts/prepare_pt_data.py \
  --tokenizer models/Qwen3-0.6B --files "data/pt_raw/belle/train_3.5M_CN.json" \
  --json-keys instruction,input,output --max-tokens 250000000 \
  --out data/pt/belle.bin --workers 24 > logs/prepare_belle.log 2>&1
[ -f data/pt/fw2.bin ] || "$VENV/python" scripts/prepare_pt_data.py \
  --tokenizer models/Qwen3-0.6B --files "data/pt_raw/fineweb2_cmn/data/cmn_Hani/train/*.parquet" \
  --text-key text --max-tokens 1950000000 \
  --out data/pt/fw2.bin --workers 24 > logs/prepare_fw2.log 2>&1

phase "phase=smoke-冒烟10步 $(date '+%F %T')"
echo "===== [2/4] 冒烟 10 步（框架兼容验证）$(date '+%F %T') ====="
"$VENV/torchrun" --nproc_per_node=2 scripts/train_pt.py --model models/Qwen3-0.6B \
  --data data/pt/fw2.bin,data/pt/belle.bin --out checkpoints/smoke \
  --deepspeed scripts/ds_zero2.json --max-steps 10 --save-steps 1000000 \
  --seq-len 2048 --per-device-bs 16 --grad-accum 8 --logging-steps 1 \
  --chunked-ce --overwrite > logs/smoke.log 2>&1

phase "phase=pt-0.6B续训 $(date '+%F %T')"
echo "===== [3/4] 续训 2.2B tokens（双卡 ZeRO-2）$(date '+%F %T') ====="
# bs16×accum8：有效批量 256 与 bs4×accum32 完全一致 → 步数/LR 计划不变
# logits 内存墙由分块 CE 破掉；梯度检查点保持开（关掉会 OOM，实测教训）
"$VENV/torchrun" --nproc_per_node=2 scripts/train_pt.py --model models/Qwen3-0.6B \
  --data data/pt/fw2.bin,data/pt/belle.bin --out checkpoints/qwen3-0.6b-pt-20261024 \
  --deepspeed scripts/ds_zero2.json --epochs 1 --seq-len 2048 --per-device-bs 16 --grad-accum 8 \
  --chunked-ce --save-steps 2000 --logging-steps 10 > logs/pt_0.6b.log 2>&1

phase "phase=sft-0.6B微调 $(date '+%F %T')"
echo "===== [4/4] SFT 2 epochs（chat template + assistant 掩码）$(date '+%F %T') ====="
# bs16×accum4：有效批量 128 与原 bs4×accum16 一致 → 每 epoch 步数不变
"$VENV/torchrun" --nproc_per_node=2 scripts/train_sft.py \
  --model checkpoints/qwen3-0.6b-pt-20261024/final --tokenizer models/Qwen3-0.6B \
  --data data/train/train.jsonl --out checkpoints/qwen3-0.6b-sft-20261024 \
  --deepspeed scripts/ds_zero2.json --epochs 2 --max-len 2048 --per-device-bs 16 --grad-accum 4 \
  --chunked-ce --save-steps 500 --logging-steps 10 > logs/sft_0.6b.log 2>&1

phase "phase=ALL_DONE 0.6B 全链完成 $(date '+%F %T')"
echo "RUN_0.6B_DONE $(date '+%F %T')"
