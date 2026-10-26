#!/usr/bin/env bash
# 门禁：EngineKit 包 build + test 全绿才算过（AGENTS.md 纪律 4，不过不合入）
# 环境适配（本机实测坑，2026-10-26）：
#  ① xcode-select 指向 CommandLineTools 时测试链不可用 → 若装了完整 Xcode 则临时指过去（不动系统配置）
#  ② Documents 在 iCloud 同步区，.build 产物被 fpfs 加扩展属性导致 codesign 拒签 → 构建目录挪出同步区
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

if ! xcodebuild -version >/dev/null 2>&1 && [ -d /Applications/Xcode.app ]; then
  export DEVELOPER_DIR=/Applications/Xcode.app
fi

SCRATCH="$HOME/.cache/engine-build"
# 模型冒烟：本机训练产物在则注入路径跑真冒烟（加载→1 token→卸载），不在则单测自动跳过
SFT_MODEL="$ROOT/train/gguf/qwen3-0.6b-sft-20261025/qwen3-0.6b-sft-Q5_K_M.gguf"
if [ -f "$SFT_MODEL" ]; then
  export ENGINEKIT_TEST_MODEL="$SFT_MODEL"
fi
cd "$ROOT/engine"
swift build --scratch-path "$SCRATCH"
swift test --scratch-path "$SCRATCH"
echo "GATE PASS: build + test 全绿"
