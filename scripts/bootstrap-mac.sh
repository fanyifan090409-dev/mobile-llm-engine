#!/usr/bin/env bash
# 第三方 Mac 一键引导：环境检查 → 装 cmake → 拉 llama.cpp 钉版 → 编静态库
# 产出即用：跑完再下模型（见 README 快速开始）就能 demo-cli 对话
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LLAMA_TAG="b11857"   # 钉版 tag，与 engine/Sources/CLLaMA/include 同步入库的头文件一致

# ① 硬件门槛：静态库只编 arm64（Apple Silicon），Intel Mac 不支持
if [ "$(uname -m)" != "arm64" ]; then
  echo "错误：本项目只支持 Apple Silicon Mac（M 系列），当前机器为 $(uname -m)"
  exit 1
fi

# ② 命令行工具（git / clang / swift）
if ! xcode-select -p >/dev/null 2>&1; then
  echo "缺少 Xcode Command Line Tools，先执行：xcode-select --install"
  exit 1
fi

# ③ cmake（CLT 不带，需 Homebrew）
if ! command -v cmake >/dev/null 2>&1; then
  if command -v brew >/dev/null 2>&1; then
    echo "安装 cmake（Homebrew）…"
    brew install cmake
  else
    echo "缺少 cmake 且未装 Homebrew。请先安装 Homebrew（https://brew.sh），再重跑本脚本。"
    exit 1
  fi
fi

# ④ llama.cpp 钉版浅克隆（已存在则跳过，不覆盖）
if [ ! -d "$ROOT/tools/llama.cpp" ]; then
  echo "拉取 llama.cpp 钉版 $LLAMA_TAG …"
  git clone --depth 1 --branch "$LLAMA_TAG" https://github.com/ggml-org/llama.cpp "$ROOT/tools/llama.cpp"
fi

# ⑤ 编译静态库（Metal 开），产物进 engine/Sources/CLLaMA/lib/macos/
"$ROOT/scripts/build-llama-static.sh"

echo
echo "引导完成。下一步下载模型并运行（见 README 快速开始）："
echo "  curl -L -o qwen3-0.6b-sft-Q5_K_M.gguf \\"
echo "    https://github.com/fanyifan090409-dev/mobile-llm-engine/releases/download/v0.1.0/qwen3-0.6b-sft-Q5_K_M.gguf"
echo "  cd apps/demo-cli && swift run demo-cli --model ../../qwen3-0.6b-sft-Q5_K_M.gguf --quant Q5_K_M --think-tags"
