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

## 模型能力指标（0.6B Q5_K_M 实测）

评测环境：Mac M5 Air、demo-cli、temperature 0.7。本仓库 `scripts/eval_hallucination.sh` 可复跑幻觉率部分；完整明细（40 题汇总、真实输出示例、15 题逐题结果、编造问答原文）见 [docs/评测/工具调用评测结果.md](docs/评测/工具调用评测结果.md)。

### 工具调用成功率（40 题遵循率评测，2026-10-26）

| 指标 | 结果 |
|---|---|
| tool_call 发射率 | **100%**（40/40） |
| schema 校验通过率（必填参数+时间格式） | **100%**（40/40） |
| 端到端写入成功 | 0%——评测 CLI 受 macOS 日历权限限制，真实写入链路归 iOS 侧 T4 阶段验证 |

### 幻觉率（2026-10-26 实测：15 题日期映射 + 5 题编造诱导）

| 指标 | 结果 |
|---|---|
| 日期参数正确率 | **0/15**（相对日期 0/9、绝对日期 0/6）——年份与钟点会被编造，例：「明天下午三点」→ `2021-06-01 15:00` |
| 编造诱导题 | 5 题中 3 题编造（天气/彩票号码/未来赛事），2 题正确拒绝（股价/他人手机号） |

已知短板：日期推算与事实类问答是 0.6B 训练分布外能力，正在修复中（1.7B 工具基座为修复路径）。结论：工具调用的「发射+格式」已达标，但**日期值目前不可信**——试用时请把它当原型验证，不要当作真实日历数据使用。

## 硬件与档位

- 仅支持 Apple Silicon Mac（静态库 arm64 专属），Intel 不支持
- 模型量化档位说明见 [docs/模型量化档位用户指南.md](docs/模型量化档位用户指南.md)
- 双 Mac 实测数据见 [docs/评测/M1.5-双Mac基准表.md](docs/评测/M1.5-双Mac基准表.md)

## 反馈

试跑中任何问题（装不上、跑不动、回答怪），直接提 [Issue](https://github.com/fanyifan090409-dev/mobile-llm-engine/issues)，附上你的 Mac 型号和终端输出。
