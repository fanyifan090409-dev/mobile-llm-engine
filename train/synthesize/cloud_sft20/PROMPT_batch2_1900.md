# SFT20 第二批补数据提示词（1900 条：leader 1500 / worker 400）

> 交付用户侧云端大模型（2026-11-04 v2）。目标：在第一批 1300 条基础上补齐领队样本量，并保证与第一批不重复。

```text
你是训练数据合成专家。请为「手机本地多模型协作系统」生成第二批监督微调（SFT）训练样本，共 1900 条。全部中文、JSONL 格式、可直接用于模型训练。

【背景设定】
系统由两类小模型协作：
- 领队模型（1.7B）：常驻内存。负责理解用户任务、拆解成子任务、派单给工人、汇总工人结果并回应用户。
- 工人模型（0.6B）：按需加载。4 个工种：
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
  {"role": "assistant", "content": "<tool_call>\n{\"name\": \"dispatch_to_worker\", \"arguments\": {\"worker\": \"calendar_worker\", \"task\": \"添加日历事件：家长会，明天下午三点，时长约一小时。今天是2026年11月5日。\"}}\n</tool_call>"},
  {"role": "tool", "content": "{\"status\": \"ok\", \"result\": \"已添加日历事件：家长会，2026-11-06 15:00-16:00\"}"},
  {"role": "assistant", "content": "<tool_call>\n{\"name\": \"dispatch_to_worker\", \"arguments\": {\"worker\": \"reminder_worker\", \"task\": \"设置提醒：今晚九点吃药。今天是2026年11月5日。\"}}\n</tool_call>"},
  {"role": "tool", "content": "{\"status\": \"ok\", \"result\": \"已设置提醒：2026-11-05 21:00 吃药\"}"},
  {"role": "assistant", "content": "都安排好了：明天下午三点的家长会已加入日历，今晚九点会提醒你吃药。"}
]}

类型 2：工人样本（role=worker，训练 0.6B）
{"role": "worker", "task_type": "calendar", "messages": [
  {"role": "system", "content": "你是手机上的日历工人，只处理日历相关派单。收到派单后只输出一个工具调用块，不要任何其他文字，格式：\n<tool_call>\n{\"name\": \"add_calendar_event\", \"arguments\": {\"title\": \"事件名称\", \"start_time\": \"YYYY-MM-DD HH:mm\", \"end_time\": \"YYYY-MM-DD HH:mm\", \"location\": \"地点\", \"note\": \"备注\"}}\n</tool_call>；没有的地点或备注填空字符串。日期必须换算成具体日期，不允许输出相对日期。"},
  {"role": "user", "content": "派单：添加日历事件：部门周会，下周三上午十点，时长一小时，地点公司会议室。今天是2026年11月5日。"},
  {"role": "assistant", "content": "<tool_call>\n{\"name\": \"add_calendar_event\", \"arguments\": {\"title\": \"部门周会\", \"start_time\": \"2026-11-11 10:00\", \"end_time\": \"2026-11-11 11:00\", \"location\": \"公司会议室\", \"note\": \"\"}}\n</tool_call>"}
]}

其余工种的工具块格式：
- reminder_worker：{"name": "set_reminder", "arguments": {"content": "提醒内容", "remind_time": "YYYY-MM-DD HH:mm"}}
- translate_worker：{"name": "translate_text", "arguments": {"text": "原文", "target_lang": "zh" 或 "en"}}
- summary_worker：{"name": "summarize_text", "arguments": {"text": "原文", "max_words": 数字}}

【本批构成：1900 条】
领队样本 1500 条（role=leader）：
- 单派单 500 条：一个子任务，派一次 → 汇总
- 多派单 550 条：2-3 个子任务，派 2-3 次 → 汇总（可并行可顺序）
- 直接回答 250 条：寒暄、致谢、常识、简单换算、简单建议等不需要派单的对话
- 异常处理 200 条：工人返回 status=error（如时间无法解析、文本过长），领队修正后重派一次或如实告知用户

工人样本 400 条（role=worker），四个工种各 100 条：
- calendar_worker：各种时间表达 + 缺省时长一小时 + 部分带地点/备注
- reminder_worker：各种时间表达 + 提醒内容
- translate_worker：中→英、英→中，覆盖日常对话/校园/邮件/通知
- summary_worker：把 300-800 字文本压缩到指定字数（max_words 取 50-200）

【去重要求（重要）】
- 第一批 1300 条已存在，本批不得复用其原句或近义复写；换场景、换人物、换表达。
- 场景要覆盖：校园、家庭、工作、通勤、就医、健身、购物、社交、旅行、节日。
- 时间表达要多样：明天/后天/大后天/下周X/周五晚上/月底/元旦/春节前/12月5号/下个月初……
- 人物与地点要多样，不要反复出现「家长会」「吃药」「公司会议室」。
- 领队样本直接回答类不能出现工具调用块；异常处理类必须真实出现 status=error。

【硬性要求】
1. JSON 必须合法，一行一个样本，不要 markdown 代码块包裹，不要行内注释。
2. tool_call 块文本格式与示例逐字一致（<tool_call> 与 </tool_call> 包裹，内部是合法 JSON）。
3. 凡涉及日期时间换算的样本，派单 task 或工人输入里必须写明「今天是YYYY年MM月DD日」，日期换算必须正确；arguments 里禁止出现相对日期。
4. 用户语言口语化、像真人（可少量省略、口语词）；领队/工人回复简洁，不啰嗦，不出现「选项/以下几种/供你选择」。
5. 派单 task 必须自包含：工人不看历史就能执行（含完整事件名/文本/时间基准）。
6. tool 角色 result 为 JSON 字符串，字段固定 {"status": "ok" 或 "error", "result": "说明"}。
7. 领队汇总不得编造工人未返回的信息；工人报错时如实说明。

【分批生成】
单次输出可能超长，可分 5 批生成，每批 380 条（leader 300 + worker 80），合计 1900 条。
每批内部比例保持一致：单派单 100 / 多派单 110 / 直接回答 50 / 异常处理 40；工人四工种各 20。
最后把 5 批合并成一个文件 multimodel_sft_batch2_1900.jsonl（UTF-8，无 BOM）。

【生成后自查清单】
生成完成后另附一份简短报告（不要混进 JSONL 文件）：
1. 总条数、领队/工人各多少、四类领队与四工种各多少；
2. 抽样验证 10 行 JSON 合法、字段齐全；
3. 抽查 10 条日期换算正确性；
4. 是否存在相对日期泄漏进 arguments；
5. 与第一批是否出现重复句子（抽检 20 条）。
```
