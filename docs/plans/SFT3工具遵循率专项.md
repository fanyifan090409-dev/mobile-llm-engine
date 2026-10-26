# SFT3 工具遵循率专项计划（v0.1，2026-10-26 用户拍板启动）

> 背景：ToolKit T3 实测（docs/plans/工具执行层-ToolKit.md §10）发现 0.6B SFT2 在训练分布同款 prompt 下零 tool_call、直接口头确认。引擎侧闭环已用官方 1.7B 验证通过，问题在模型侧。
> 本计划执行 tech-debt #2 的修复路径：schedule 占比调高 + 合成期 system 进推理模板 + 训练/推理模板对齐；1.7B 工具基座是最后兜底，不在本计划范围。

## 1. 根因链（2026-10-26 锁定，证据齐全）

1. **合成期 system 被剥离**：synthesize_sft.py 用 `SYNTH_SYS_SCHED1`（含工具定义+格式示例）引导 30B teacher 输出 `<tool_call>` XML，但写入数据集的轨迹**故意不含 system 消息**（「user 消息保持干净」）→ SFT1/2 训练时模型从未见过工具定义这个触发器。
2. **推理模板同样没有**：EngineCore 按 token ID 直拼模板只有 user/assistant（无 system 注入）→ 训练与推理虽然互相一致，但模型学到的触发条件（teacher 侧有 system）在两端都不存在。
3. **占比不足**：train.jsonl 实测 schedule 1.79M / 8.91M = **20%**（translate 34% + record_tidy 34% 主导），且轨迹内 tool_call XML 只占一部分 token → 直接作答是全数据的主流行为，0.6B 容量下条件行为被稀释。
4. **0.6B 容量边缘**：显式指令「只输出一个工具调用块」也照做不了（复述指令），说明 0.6B 学得到「关于格式的知识」但生成通路脆弱——需要更强的触发器与更高占比。

## 2. 修复方案（三阶段，今天内可完成）

### 阶段 0：引擎侧 system 注入 + 遵循率基线（本机 Mac）

- **引擎改动**（engine/Sources/EngineKit/EngineCore.swift + GenerationRequest）：请求带 `tools` 且解析出已注册工具时，chatTokens 前插一条 system 消息——内容由 ToolSpec 生成，措辞逐字对齐 SYNTH_SYS_SCHED1（「你是手机助手。当用户要求添加日历事件时，只输出一个工具调用块…」+ 参数 JSON 示例）。单工具硬对齐，多工具 M3 再泛化。
- **/no_think 结论**：Qwen3 官方模板的关思考=注入空 `<think>\n\n</think>\n\n` 块（token 151667/151668）；咱 SFT 数据全程无思考痕迹、训练模板未注入空块 → SFT3 训练与推理**保持都不注入**（对齐优先）。若评测发现 SFT3 输出出现 `<think>` 块，再按官方模板在推理侧注入空块。
- **遵循率评测 harness**（scripts/eval_toolcall.sh + 分析脚本）：
  - 40 条 prompt：30 条训练分布同款（复用 ACTIVITIES/TIME_PHRASES/LOCATIONS 模板，日期 2026-11）+ 10 条泛化（不同措辞/新场景）；
  - demo-cli `--tools --trust-tools -p` 非交互跑，抓 `[工具]` 事件与最终话术；
  - 四指标：tool_call 发射率 / XML+JSON 解析率 / schema 校验通过率（必填参数+时间正则）/ 端到端成功（执行+确认）率。
- **基线**：先对 SFT2 0.6B 跑 40 条 → 验证「system 触发器能否直接唤醒 SFT2」。无论结果如何都继续阶段 1（能唤醒=SFT3 更稳；不能=SFT3 必须）。

### 阶段 1：数据重拼装 + SFT3 训练（训练机）

- **数据后处理**（train/synthesize/assemble_train.py 扩展或新脚本，本地改后同步 llm-mobile/scripts/）：
  - schedule 每条轨迹 messages 前插 `{"role":"system","content":SYNTH_SYS_SCHED1}`（逐字复制合成脚本常量）；
  - CAPS 调为 SFT3 占比：schedule 1.79M 全保留（≈**40%**）、translate 1.3M、record_tidy 1.0M、summarize 0.5M、message 全保留（0.13M，过滤规则不变）、misc 0.15M → 总量 ≈ 4.9M tokens；
  - 输出 `data/train_sft3/`（train.jsonl + val.jsonl + report.txt），不动原始 jsonl 与 data/train/（SFT2 对比链今晚要用）。
- **训练**：run_sft3.sh 复制 run_sft2.sh（2 epochs、lr 1e-5、max-len 2048、bs16×accum4、chunked-ce + torch-compile 带重试），数据指向 train_sft3/，输出 checkpoints/qwen3-0.6b-sft3-20261026/。参考 SFT2 1348 步 36 分钟，SFT3 约 30-40 分钟。
- **模板对齐确认**：train_sft.py 的 apply_chat_template 默认 enable_thinking 未关 → 训练模板无空思考块，与推理一致，SFT3 保持不动（见阶段 0 /no_think 结论）。
- **convert**：训练完 convert_hf_to_gguf 出 f16（1.5GB），rsync 回 Mac。

### 阶段 2：量化 + 遵循率评测 + 归档（本机 Mac）

- 量化 Q5_K_M（旗舰档，551MB 量级）——先只出这一档跑评测，通过后再补齐 Q4_K_M/IQ4_XS 发布档；
- 遵循率评测 40 条 vs SFT2 基线四指标对比；
- 通过 → 更新模型池推荐（可选池替换旗舰款前先跑常规 15 题生成评测防遗忘）；不通过 → 升级路径（见 §4）。

## 3. 验收标准

- 阶段 0：引擎改动门禁全绿（swift build + 24 测试 + demo-cli 构建）；SFT2 基线四指标出数；
- 阶段 1：训练 TRAINING_FINISHED、f16 落盘回 Mac；
- 阶段 2：SFT3 遵循率 ≥ **70% 发射率** 且端到端 ≥ 50%（阈值先验，最终以报告数据说话；SFT2 基线为参照）；常规 15 题生成评测不红。

## 4. 升级路径（阶段 2 不达标时，需用户拍板）

1. **重启 30B teacher**（:8003，启停存档 train/训练机常驻服务启停.md 第五节命令）补合成 schedule 样本（目标 +1-2 万条，占比 40% 且总量不缩水）→ 重跑 SFT3；
2. 仍不达标 → **1.7B 做工具场景基座**（用户已预留的兜底）。

## 5. 回滚点

- 阶段 0 引擎改动独立 commit，不碰 M1 推理路径与 ToolLoop，可干净 revert；
- 数据侧只新增 data/train_sft3/，SFT2 的 data/train/ 与今晚对比评测链零冲突；
- SFT3 训练产物独立 checkpoints 目录，SFT2 final 不动；
- 全程不改原始 jsonl、不动 teacher 下线状态、不动 LiteLLM :4000。
