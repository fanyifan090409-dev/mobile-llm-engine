# 技术债清单（只记不改，专门任务再清理）

## 1. 自转 GGUF 缺 added_tokens 元数据（2026-10-26 发现）

- **现象**：`llama_tokenize("<|im_end|>", add_special=true)` 返回 6 个字面 subword token（`<`、`|`、`im`、`_end`、`|`、`>`），而非特殊 token 151645。字符串式聊天模板全部退化。
- **根因**：训练机 `tools/llama_convert/gguf-py` 是老版本（vocab.py 时代），只从 `tokenizer_config.json` 的 `added_tokens_decoder` 读特殊 token；Qwen3 该字段为空，added tokens 全在 `tokenizer.json` 的 `added_tokens`（26 个）→ GGUF 丢失 `tokenizer.ggml.added_tokens` 键。
- **影响面**：所有自转 GGUF（orig/sft1/sft2 全系）。词表本身完整（151936、EOG 标志完好），**PPL 类评测不受影响**（语料无特殊 token）；生成类评测（15 题抽查、demo 对话）受模板退化影响。
- **引擎侧已缓解**：EngineCore 按 token ID 直拼 Qwen3 聊天格式（151644/151645 钉死），与正确模板分词逐 token 等价，见 EngineCore.swift chatTokens 注释。
- **待修（训练线，需用户拍板）**：用钉版 llama.cpp（b11857）自带的新 gguf-py 重转 f16 → 重新量化 → 生成类评测重跑。引擎侧 ID 拼接保留（对两种 GGUF 都成立，不依赖修复时间）。

## 2. 0.6B SFT2 工具调用遵循率不达标（2026-10-26 T3 实测）

- **现象**：训练分布同款 prompt 下（temp 0.7 与贪心各一次）均直接口头确认，零 tool_call；显式格式指令也照做不了。
- **数据侧已排除**：train.jsonl 含 8581 条完整 schedule 轨迹（XML tool_call + tool 回填 + 确认话术，20% 占比，2 epochs）。
- **待修（训练线，SFT3 专项）**：schedule 占比调高；/no_think 推理模板；合成期 system 提示进推理模板。仍不达标则 1.7B 做工具场景基座。
- **引擎侧不受影响**：闭环已用官方 1.7B 实测通过（docs/plans/工具执行层-ToolKit.md §10）。

## 3. demo-cli 无 app bundle，EventKit TCC 拒绝（2026-10-26 T3 实测）

- **现象**：`requestFullAccessToEvents` 在 CLI 下返回拒绝（「日历访问被拒绝」），日历无法真写入。
- **根因**：SPM 可执行文件无 Info.plist/签名 bundle，TCC 不弹授权。
- **影响面**：仅 demo-cli 端到端验证降级；引擎闭环验证不受影响（工具执行/回填/续跑已实测）。
- **待修**：T4 iOS app 里真机验证（Info.plist 权限串 + 系统弹窗），demo-cli 不修。
