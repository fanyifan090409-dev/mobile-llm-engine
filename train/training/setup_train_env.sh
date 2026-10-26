#!/usr/bin/env bash
# 训练环境搭建：conda 环境 + 依赖 + 三档 base 模型 + 续训语料（全部走 hf-mirror，HF 直连被墙）
# 训练机无 sudo、无系统 pip、无 python3-venv → 用 Miniconda 克隆 base 建独立环境
set -euo pipefail
export HF_ENDPOINT=https://hf-mirror.com
export HF_HOME=/home/ubuntu/.cache/huggingface
cd /home/ubuntu/llm-mobile
# 防重入：已有实例在跑则直接退出
if [ -f logs/setup.pid ] && kill -0 "$(cat logs/setup.pid)" 2>/dev/null; then
  echo "setup 已在运行（pid $(cat logs/setup.pid)），退出"
  exit 0
fi
echo $$ > logs/setup.pid
trap 'rm -f logs/setup.pid' EXIT
VENV=/home/ubuntu/Miniconda3/envs/train/bin
mkdir -p logs models data/pt_raw

echo "[1/5] conda 环境（克隆 base，已存在则跳过）"
source /home/ubuntu/Miniconda3/etc/profile.d/conda.sh
conda env list | grep -q "^train " || conda create -y -n train --clone base
"$VENV/python" -m pip install -U pip -q
"$VENV/python" -m pip install -q huggingface_hub
# 克隆环境偶发丢失 console script 入口，强制重装确保 huggingface-cli 存在
[ -x "$VENV/huggingface-cli" ] || "$VENV/python" -m pip install --force-reinstall -q huggingface_hub

echo "[2/5] 下载三档 base 模型（Qwen3-0.6B/1.7B/4B，stdlib 下载器）"
python3 scripts/dl_mirror.py model Qwen/Qwen3-0.6B models/Qwen3-0.6B "" "*.md,*.txt"
python3 scripts/dl_mirror.py model Qwen/Qwen3-1.7B models/Qwen3-1.7B "" "*.md,*.txt"
python3 scripts/dl_mirror.py model Qwen/Qwen3-4B models/Qwen3-4B "" "*.md,*.txt"

echo "[3/5] 下载续训语料：fineweb-2 中文前 10 分片 + BELLE 3.5M 对话"
python3 scripts/dl_mirror.py dataset HuggingFaceFW/fineweb-2 data/pt_raw/fineweb2_cmn "data/cmn_Hani/train/000_0000?.parquet" ""
python3 scripts/dl_mirror.py dataset BelleGroup/train_3.5M_CN data/pt_raw/belle "train_3.5M_CN.json" ""

echo "[4/5] 安装 torch（阿里云镜像优先，失败回退 PyPI）"
"$VENV/python" -m pip install -q -i https://mirrors.aliyun.com/pypi/simple/ torch || "$VENV/python" -m pip install -q torch

echo "[5/5] 安装训练框架"
"$VENV/python" -m pip install -q -i https://mirrors.aliyun.com/pypi/simple/ transformers datasets accelerate deepspeed mlflow || "$VENV/python" -m pip install -q transformers datasets accelerate deepspeed mlflow

"$VENV/python" -c "import torch; print('torch', torch.__version__, 'cuda', torch.cuda.is_available())"
touch logs/setup_done.marker
echo SETUP_DONE
