# Mobile LLM Engine（移动端本地 LLM 推理引擎）

面向手机的本地大模型推理引擎（iOS 优先，Mac 同源验证）。模型为**基于 Qwen3 继续训练**的中文手机助手，专注工具调用类任务（如添加日历事件），数据不出设备。

当前开放试用：**0.6B 模型（Q5_K_M 量化，551MB）**，在 Apple Silicon Mac 上可跑。

## 快速开始（Mac）

前置条件：Apple Silicon（M 系列）Mac，macOS 14+，Xcode Command Line Tools 已装（`xcode-select -p` 有输出即可）。

```bash
git clone https://github.com/fanyifan090409-dev/mobile-llm-engine.git
cd mobile-llm-engine
./scripts/bootstrap-mac.sh          # 装 cmake → 拉 llama.cpp 钉版 → 编静态库（约 5-10 分钟）

# 下载模型（551MB）
curl -L -o qwen3-0.6b-sft-Q5_K_M.gguf \
  https://github.com/fanyifan090409-dev/mobile-llm-engine/releases/download/v0.1.0/qwen3-0.6b-sft-Q5_K_M.gguf

# 跑起来（交互对话）
cd apps/demo-cli
swift run demo-cli --model ../../qwen3-0.6b-sft-Q5_K_M.gguf --quant Q5_K_M --think-tags
```

首次 `swift run` 编译约 1-2 分钟，之后每次秒开。运行内存约 1GB。

## 参数速查（demo-cli）

| 参数 | 说明 |
|---|---|
| `--model <路径>` | GGUF 模型文件（必填） |
| `--think-tags` | **本模型必开**——SFT 训练模板含空思考块，推理必须同开同关 |
| `--tools --trust-tools` | 开启日历工具模式（`--trust-tools` 跳过确认，写日历直接执行） |
| `--speed <档位>` | powerSaver / balanced / performance / turbo（解码速度差异小，功耗与首响有差） |
| `-p "一句话"` | 一次性生成模式（基准用），结束打印 tok/s 统计 |

## 硬件与档位

- 仅支持 Apple Silicon Mac（静态库 arm64 专属），Intel 不支持
- 模型量化档位说明见 [docs/模型量化档位用户指南.md](docs/模型量化档位用户指南.md)
- 双 Mac 实测数据见 [docs/评测/M1.5-双Mac基准表.md](docs/评测/M1.5-双Mac基准表.md)

## 反馈

试跑中任何问题（装不上、跑不动、回答怪），直接提 [Issue](https://github.com/fanyifan090409-dev/mobile-llm-engine/issues)，附上你的 Mac 型号和终端输出。
