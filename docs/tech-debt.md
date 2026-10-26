# 技术债清单（只记不改，专门任务再清理）

## 1. 自转 GGUF 缺 added_tokens 元数据（2026-10-26 发现）

- **现象**：`llama_tokenize("<|im_end|>", add_special=true)` 返回 6 个字面 subword token（`<`、`|`、`im`、`_end`、`|`、`>`），而非特殊 token 151645。字符串式聊天模板全部退化。
- **根因**：训练机 `tools/llama_convert/gguf-py` 是老版本（vocab.py 时代），只从 `tokenizer_config.json` 的 `added_tokens_decoder` 读特殊 token；Qwen3 该字段为空，added tokens 全在 `tokenizer.json` 的 `added_tokens`（26 个）→ GGUF 丢失 `tokenizer.ggml.added_tokens` 键。
- **影响面**：所有自转 GGUF（orig/sft1/sft2 全系）。词表本身完整（151936、EOG 标志完好），**PPL 类评测不受影响**（语料无特殊 token）；生成类评测（15 题抽查、demo 对话）受模板退化影响。
- **引擎侧已缓解**：EngineCore 按 token ID 直拼 Qwen3 聊天格式（151644/151645 钉死），与正确模板分词逐 token 等价，见 EngineCore.swift chatTokens 注释。
- **待修（训练线，需用户拍板）**：用钉版 llama.cpp（b11857）自带的新 gguf-py 重转 f16 → 重新量化 → 生成类评测重跑。引擎侧 ID 拼接保留（对两种 GGUF 都成立，不依赖修复时间）。

## 2. 0.6B 工具调用遵循率（2026-10-26 已解决，SFT3B 达标）

- **历史现象**：SFT2 零 tool_call 发射（40 题全口头确认）；SFT3 首轮（system 注入+空块+占比）仍 0%。
- **最终根因**：SFTDataset 只对最后一条 assistant 算 loss，五段式 schedule 轨迹的 tool_call 段永远被掩码在 prompt 里，模型从未被要求输出工具调用（SFT3 首轮只把口头确认训练得更强）。
- **修复**：assemble_train.py sft3 profile 把带 system 的轨迹按 assistant 逐条切前缀样本（6,346 条 tool_call 样本 + 6,355 条确认样本），SFT3B 重训 2 epochs。
- **结果（SFT3B Q5_K_M，40 题）**：发射率 100%、schema 通过率 100%、端到端 0%（CLI TCC 环境限制，见 #3）；15 题通用生成评测 PASS 无遗忘。
- **遗留观察**：泛化题的日期映射偏弱（「周五晚上七点」→ 2021-05-06 等，模型不从真实日期推算星期）。属 0.6B 训练分布外能力，T4 iOS 确认弹窗可兜底；若影响可用性再议日期指令增强。

## 3. demo-cli 无 app bundle，EventKit TCC 拒绝（2026-10-26 T3 实测）

- **现象**：`requestFullAccessToEvents` 在 CLI 下返回拒绝（「日历访问被拒绝」），日历无法真写入。
- **根因**：SPM 可执行文件无 Info.plist/签名 bundle，TCC 不弹授权。
- **影响面**：仅 demo-cli 端到端验证降级；引擎闭环验证不受影响（工具执行/回填/续跑已实测）。
- **待修**：T4 iOS app 里真机验证（Info.plist 权限串 + 系统弹窗），demo-cli 不修。
