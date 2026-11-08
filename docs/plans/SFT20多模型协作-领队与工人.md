# SFT20 多模型协作专项：1.7B 领队 + 0.6B 工人

> 状态：M1-M4 已完成（2026-11-06），M5 引擎多模型协作进行中
> 训练与评测（2026-11-06）：1.7B 领队 12 题 JSON/schema 12/12、10/10 派单正确；0.6B 工人 8 题 8/8。工人日期补训 SFT20c（查表版）60 题 93.3%、下周X 22/22，详见 `docs/评测/SFT20b-SFT20c-工人日期补训.md`。**M5 必须先落地两条推理约束：① worker 用户消息追加本周/下周/下下周日期表；② assistant 回合注入空思考块（enable_thinking=false）。**
> 数据进度（2026-11-04 11:30）：用户云端生成首版 `multimodel_sft_1300.jsonl`（1300 条，约 0.98M 字符）已收进 `train/synthesize/cloud_sft20/` 并同步训练机 `data/cloud_sft20/`；QC 通过（0 坏 JSON、0 重复、worker schema 全对齐）。分布：leader 500 / worker 800；worker 四工种各 200；leader 含 mixed 150 / chat 100 / error 50。leader 500 条偏少，正式 SFT20 前建议扩到 1500+；引擎侧 `dispatch_to_worker`、`translate_text`、`summarize_text` 尚未实现。
> 数据进度（2026-11-04 18:35）：第二批 1900 条已收并独立 QC。清理后 1756 条：error 类按「用户话术×消息轮数×首次派单」去重，200→56；24 条摘要异常的「长」×900 占位原文替换为真实长文。两批合并 3056 条 = leader 1856 / worker 1200，已拆为 `leader_sft20.jsonl` / `worker_sft20.jsonl`，清单见 `manifest_sft20.json`。下一步：assemble_train.py 加 sft20 profile → 0.6B 工人线 / 1.7B 领队线。
> 前置依赖：SFT19 数学强化线完成（当前训练机合成 9.28M/10M 进行中）

## 一、调研结论：2026 多模型协作最火的方式（三条主线）

### 1. 范式：多 LLM 协作已从工程技巧升格为学术主流
- ACL 2026 立场论文《When One LLM Drools, Multi-LLM Collaboration Rules》给出多 LLM 协作分类法，主张「追求单一全能大模型是死路」；
- **MoA（Mixture-of-Agents）**：多模型多层聚合（propose→aggregate），2026 仍是主流范式；
- **TRINITY**：~0.6B 协调器编排比它大 100 倍的模型达到 SOTA——直接证明「小模型当调度者」可行，与我们的「大领小」互补（我们是 1.7B 领 0.6B，手机内存现实）；
- ICML 2026 FusionRoute 理论结论：router 必须「指挥+补位」双角色，不能只选专家。

### 2. 协作模式：Supervisor（中心化）胜出
三分类：Supervisor（中心化，适合 2-10 agent 可控场景）/ Hierarchical（分层，大型组织）/ Swarm（去中心化，探索性任务，难调试）。
我们的场景（1 领队 + 2 工人）正好落在 Supervisor 的甜点区。代表框架：MetaGPT（71k stars）、CAMEL（18k）。

### 3. 协议标准：A2A + MCP 双轨格局成型（2026-03 定型）
- **A2A v1.0**（Linux Foundation 托管，2026-03 发布）：agent↔agent 通信——能力发现（agent-card）、任务委派、异步执行、状态同步。基于 HTTP/JSON-RPC；
- **MCP**：agent↔工具（我们 ToolLoop 的角色）；
- OpenAI/微软/Meta 均已宣布同时支持两协议。

## 二、Git 仓库问题的答案：手机上不用 Git

Git 协作确实是编码 agent 圈 2026 最火的玩法之一：
- Cloudflare 公开招募「为 agent 设计的下一代 Git 平台」（数千 agent 同仓库协作）；
- Cursor 2.0 原生多 agent（最多 8 个并发，每人独立 git worktree 隔离）；
- Munder Difflin（2.5k stars）：**本地 git 仓库装纯文件——per-agent 记忆、原子文件邮箱、共享黑板**；Buzz（block 开源，29.8k stars）共享频道+审计。

**关键洞察**：这些方案里 git 的本质不是版本控制，是「共享黑板 + 消息邮箱」——agent 间交换消息用原子文件。

**手机端结论：不用 git**。理由：
1. 手机上的模型间没有「代码工作区冲突」问题——交换的是结构化消息，不是文件 diff；
2. libgit2 重、文件 IO 慢，与手机内存/热控约束冲突；
3. 单 App 内进程内通信零协议开销（Google ADK codelab 同款结论：本地子 agent 走进程内 AgentTool，不走 HTTP）。

**替代**：进程内邮箱/黑板（Swift 实现，SQLite 或内存队列），消息格式借鉴 A2A 语义（task 描述/status/result 三字段——即我们 tool 角色的 JSON 结构）。git 方案唯一值得借鉴的是「原子写」思想，但那是实现细节。

## 三、手机端架构规划（草案，待确认）

```
App 层
  用户一句话任务
      ↓
领队 EngineCore（1.7B 常驻，KV cache 保活）
  ├─ dispatch_to_worker 进 ToolLoop 白名单（复用现成调度通道）
  ├─ 拆解 → 派单（结构化 JSON 消息）
  ↓ 进程内邮箱（借鉴 A2A 语义，不走 HTTP）
工人 EngineCore（0.6B 按需换入换出）
  ├─ calendar_worker / reminder_worker / translate_worker / summary_worker
  └─ 窄任务执行 → 结构化结果回报
      ↓
领队汇总 → 自然语言回应用户
```

**三个工程难点（已在 PPT 中如实标注「规划中，尚未实现」）**：
1. 内存：领队常驻 + 工人权重换入换出（1.7B+0.6B Q4 同时驻留 ≈2.2GB，8GB 设备可行，12GB 从容）；
2. EngineCore 多实例改造：现为单例假设，需支持多上下文并存；
3. 领队调度能力训练：dispatch 拆解/重派/汇总一轮专项（SFT20）。

**与学界差异点（对外叙事）**：TRINITY 是小模型协调大模型，我们是 1.7B 领 0.6B——「大领小」是手机内存预算下的现实选择，且调度者必须常驻（FusionRoute「指挥+补位」结论）。

## 四、训练数据契约

- **类别**：新增 `dispatch` 类，产物 `data/sft20/{leader,worker}_*.jsonl`；
- **格式**：复用现有 messages 多轮 + `<tool_call>` 块契约（与 SYNTH_SYS_SCHED1 同款），dispatch_to_worker 进推理侧白名单；
- **两类样本**：
  - leader（训 1.7B）：拆解派单 / 多派单 / 直接回答 / 异常重派；
  - worker（训 0.6B）：4 工种窄任务执行 + 结构化回报；
- **质检锚点**：日期换算样本必须含「今天是YYYY年MM月DD日」，arguments 禁止相对日期（SFT17 幻觉率教训）。

## 五、数据合成

本次由用户侧云端大模型生成（提示词见下节，已交付 2026-11-03）。
生成后走现有链：QC → 变式扩展（variant_gen）→ 拼装（assemble_train.py 加 sft20 profile）→ 领队/工人分别进 1.7B/0.6B 训练。

## 六、里程碑与回滚点

- M1：云端生成 1300 条样本 → QC 通过 → 落 data/sft20/（回滚=删除目录）
- M2：assemble_train.py 加 sft20 profile → 拼装冒烟（回滚=revert profile 常量）
- M3：0.6B 工人线 SFT（工人样本+历史池降采样防遗忘）→ 量化 → 窄任务评测
- M4：1.7B 领队线 SFT（leader 样本+历史池）→ 量化 → dispatch 遵循率评测
- M5：EngineCore 多实例改造 + 进程内邮箱 + WorkerDispatcher（三周日期表注入 + 空思考块）→ 真机多模型协作 demo

## 七、合成提示词（交付用户侧云端大模型，2026-11-03 v1）

```text
你是训练数据合成专家。请为「手机本地多模型协作系统」生成监督微调（SFT）训练样本。全部样本中文、JSONL 格式、可直接用于模型训练。

【背景设定】
系统由两类小模型协作：
- 领队模型（1.7B）：常驻内存。负责理解用户任务、拆解成子任务、派单给工人、汇总工人结果并回应用户。
- 工人模型（0.6B）：按需加载。各司其职的窄任务专家，共 4 个工种：
  calendar_worker（日历事件：解析日期时间、添加事件）
  reminder_worker（提醒事项：解析时间、设置提醒）
  translate_worker（中英互译）
  summary_worker（长文本摘要、信息整理）

协作规则：领队与工人只通过结构化消息通信。领队输出派单指令（tool_call 块），工人执行后回传 JSON 结果。

【输出格式】
输出 JSONL，每行一个样本，两类：

类型 1：领队样本（role=leader，训练 1.7B）
{"role": "leader", "task_type": "calendar", "messages": [
  {"role": "system", "content": "你是手机上的领队助手。规则：1) 判断用户任务是否需要派单；简单问题直接回答，不派单；2) 需要派单时只输出一个工具调用块，不要任何其他文字，格式：\n<tool_call>\n{\"name\": \"dispatch_to_worker\", \"arguments\": {\"worker\": \"工人名\", \"task\": \"完整子任务描述\"}}\n</tool_call>；3) 收到工人结果后继续派单或汇总回复用户；4) 汇总时用自然、简洁的中文。"},
  {"role": "user", "content": "帮我安排：明天下午三点和家长会老师碰面，顺便提醒我今晚九点吃药。"},
  {"role": "assistant", "content": "<tool_call>\n{\"name\": \"dispatch_to_worker\", \"arguments\": {\"worker\": \"calendar_worker\", \"task\": \"添加日历事件：家长会，明天下午三点，时长约一小时。今天是2026年11月3日。\"}}\n</tool_call>"},
  {"role": "tool", "content": "{\"status\": \"ok\", \"result\": \"已添加日历事件：家长会，2026-11-04 15:00-16:00\"}"},
  {"role": "assistant", "content": "<tool_call>\n{\"name\": \"dispatch_to_worker\", \"arguments\": {\"worker\": \"reminder_worker\", \"task\": \"设置提醒：今晚九点吃药。今天是2026年11月3日。\"}}\n</tool_call>"},
  {"role": "tool", "content": "{\"status\": \"ok\", \"result\": \"已设置提醒：2026-11-03 21:00 吃药\"}"},
  {"role": "assistant", "content": "都安排好了：明天下午三点的家长会已加入日历，今晚九点会提醒你吃药。"}
]}

类型 2：工人样本（role=worker，训练 0.6B）
{"role": "worker", "task_type": "calendar", "messages": [
  {"role": "system", "content": "你是手机上的日历工人，只处理日历相关派单。收到派单后只输出一个工具调用块，不要任何其他文字，格式：\n<tool_call>\n{\"name\": \"add_calendar_event\", \"arguments\": {\"title\": \"事件名称\", \"start_time\": \"YYYY-MM-DD HH:mm\", \"end_time\": \"YYYY-MM-DD HH:mm\", \"location\": \"地点\", \"note\": \"备注\"}}\n</tool_call>；没有的地点或备注填空字符串。日期必须换算成具体日期，不允许输出相对日期。"},
  {"role": "user", "content": "派单：添加日历事件：家长会，明天下午三点，时长约一小时。今天是2026年11月3日。"},
  {"role": "assistant", "content": "<tool_call>\n{\"name\": \"add_calendar_event\", \"arguments\": {\"title\": \"家长会\", \"start_time\": \"2026-11-04 15:00\", \"end_time\": \"2026-11-04 16:00\", \"location\": \"\", \"note\": \"\"}}\n</tool_call>"}
]}

其余工种的工具块格式：
- reminder_worker：{"name": "set_reminder", "arguments": {"content": "提醒内容", "remind_time": "YYYY-MM-DD HH:mm"}}
- translate_worker：{"name": "translate_text", "arguments": {"text": "原文", "target_lang": "zh" 或 "en"}}
- summary_worker：{"name": "summarize_text", "arguments": {"text": "原文", "max_words": 数字}}

【硬性要求】
1. JSON 必须合法，一行一个样本，不要 markdown 代码块包裹；
2. tool_call 块文本格式与示例逐字一致（<tool_call> 与 </tool_call> 包裹，内部是合法 JSON）；
3. 凡涉及日期时间换算的样本，派单或输入里必须写明「今天是YYYY年MM月DD日」，日期换算必须正确（明天=+1 天等）；arguments 里禁止出现相对日期（如「明天下午三点」）；
4. 用户语言口语化、像真人（可少量省略、口语词）；领队/工人回复简洁、不啰嗦、不出现「选项/以下几种/供你选择」；
5. task 字段（派单描述）必须自包含：工人不看历史就能执行；
6. tool 角色的 result 内容为 JSON 字符串，字段固定 {"status": "ok" 或 "error", "result": "说明"}。

【样本构成：共约 1300 条】
领队样本（约 500 条），四种情况都覆盖：
- 单派单：一个子任务，派一次 → 汇总（约 200 条）
- 多派单：2-3 个子任务，多次派单 → 汇总（约 150 条）
- 直接回答：简单问题不派单直接答（约 100 条）
- 异常处理：工人返回 status=error，领队重派或向用户如实说明（约 50 条）

工人样本（约 800 条），四个工种均匀分布（各约 200 条）：
- calendar_worker：解析各种时间表达（明天/后天/下周三/今晚八点/元旦/圣诞节…），时长缺省默认一小时
- reminder_worker：同上，输出 set_reminder
- translate_worker：中→英、英→中，覆盖日常对话/校园场景/邮件
- summary_worker：把 300-800 字文本压缩到指定字数

【生成后自查清单】
生成完成后自查并报告：
1. 总条数、领队/工人各多少、各工种多少；
2. 每行 JSON 合法、字段齐全（可用脚本验证）；
3. 抽查 10 条日期换算正确性；
4. 是否存在相对日期泄漏进 arguments 的情况。
```

## 附：来源索引

- ACL 2026 立场论文与学术主线：雪球综述 [多层次多维度多场景多模型复杂协同融合式AI范式](https://xueqiu.com/2961204996/411608938)
- 协作三模式对比：[CSDN 多 Agent 协作模式](https://blog.csdn.net/haohaizi_liu/)
- GitHub 框架排行：MetaGPT（71k）/ CAMEL（18k）/ MindSearch
- A2A 协议：[a2aprotocol.ai](https://a2aprotocol.ai/)；A2A 与 MCP 对比：[a2acn.com](https://a2acn.com/docs/topics/a2a-and-mcp/)；协议时间线：[CSDN 多Agent通信协议指南](https://blog.csdn.net/BADAO_LIUMANG_QIZHI/article/details/167385228)
- Git 协作趋势：[Cloudflare next Git platform](https://blog.cloudflare.com/next-git-platform-on-cloudflare)、[x-cmd Git 革命](https://blog.csdn.net/edwinjhlee/article/details/163506233)、[Git Worktree Isolation](https://www.google.com/goto?url=CAEShQEB6zswFYf7i3fhvrW_Bx9UWa9-k_kS9BnnGv98MiD97tqeZ01mwXVAPJdMZR1Vm32uihuIe16euGe3yC57QQOXXsuJ3krGVhC2QSsCD1DpARH8S44wyjnY3G_UgAo87rV6SiXqIZkP6MoXwEupoWs7TGZQ1SOQYlwX8fEdS5pyC6kS6NDf)
- 手机端编排：Google [LiteRT-LM](https://developers.google.com/edge/litert)、端侧 AI 产业链 [搜狐](https://m.sohu.com/a/1086865009_120732800/)、手机本地部署实测 [CSDN](https://m.blog.csdn.net/weixin_32770423/article/details/166717732)
- 端侧系统综述：[On-Device LLM Systematic Survey](https://www.aminer.cn/pub/6ab66f4f25ef7be5fb39d2cc/on-device-large-language-models-for-mobile-applications-a-systematic-survey-of)
