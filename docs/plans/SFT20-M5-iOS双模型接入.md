# SFT20 M5 第二切片：iOS 壳双模型接入

> 状态：2026-11-07 起稿。第一切片（EngineKit 派单 + Mac demo-cli）已完成；本切片把同一链路接进 iOS 壳。
> 用户已拍板「开始下一步」。

## 1. 目标

在现有「Agent 实验室」聊天壳里提供可选的**双模型协作模式**：

1. 领队（1.7B SFT20）+ 工人（0.6B SFT20c）都在设备本地运行，离线可用。
2. 用户一句「明天下午三点提醒我吃药」→ 领队派 `reminder_worker` → 工人算日期并输出 `set_reminder` → 壳执行 EventKit（人工确认）→ 领队汇总。
3. UI 能看见「领队理解 → 工人执行 → 汇总」三段过程，以及工人调用明细。
4. 默认关闭，开启前明确显示内存代价；模型缺失时不可开启并给出导入提示。

## 2. 关键决策

| 决策 | 结论 | 理由 |
|---|---|---|
| 模式入口 | 设置页新增「多模型协作（实验）」开关 | 不影响现有单模型用户；符合「可选 UI 必须标代价」 |
| 默认状态 | 关闭 | 双模型峰值约 3.1 GB，8GB 机型余量小 |
| 模型选择 | 自动识别 SFT20 领队 Q5 + SFT20c 工人 Q5/Q4，不做手动配对 | 首切片先控变量；模型库导入后自动可用 |
| 工人加载 | 懒加载，首次派单时加载；四种工人共用同一份 0.6B 权重 | 省内存；修 WorkerDispatcher 按工人名缓存导致的重复加载 |
| 工人上下文 | 固定 2K | 工人输入=系统提示+任务+日期表，2K 足够 |
| 领队上下文 | 沿用用户当前档位（4K/8K…） | 不另造一套设置；16K+ 仍走原风险确认 |
| 工具范围 | 本切片只执行日历/提醒；翻译/摘要返回「执行器未接入」 | 0.6B 工人只会发工具调用，翻译/摘要执行器需另一条生成链，单列后续 |
| 失败回退 | 开关关闭即恢复用户原单模型；工人加载失败回填错误给领队 | 不让实验模式锁死 App |

## 3. 接口与改动面

### 3.1 引擎（EngineKit）

- `WorkerDispatcher` 引擎缓存键从「工人名」改为「模型路径 + 量化 + 上下文」：
  四种工人共用同一 0.6B 时只加载一份；新增内部 `cacheKey(for:)` 供单测。
- 不改 `DispatchTool` / `ToolLoop` 契约（第一切片已验证）。

### 3.2 iOS 壳（apps/ios-shell）

`DemoModel`：

- 识别模型文件：
  - 领队：`qwen3-1.7b-sft20-Q5_K_M.gguf`
  - 工人：`qwen3-0.6b-sft20c-Q5_K_M.gguf` → 回退 `qwen3-0.6b-sft20c-Q4_K_M.gguf`
  - 在 `Documents/Models` 或 App Bundle 查找。
- `multiModelEnabled` 持久化（`UserDefaults`），默认 false。
- `enableMultiModel()` / `disableMultiModel()`：
  - 开启：重载领队模型（`thinkTags: true`）、构造 `WorkerDispatcher`（工人 ctx 2048）、注册 `DispatchTool`（执行器映射日历/提醒）。
  - 关闭：`dispatcher.unloadAll()`、重载用户原模型；派单工具保留注册但不再进白名单。
- 请求构造：
  - 多模型模式：messages 首部插入 `WorkerProfiles.leaderSystemPrompt + "\n" + DateHint.todayLine()`；用户内容用原文（不拼 TimeHints）；tools 固定 `["dispatch_to_worker"]`。
  - 单模型模式：完全沿用现有路径。
- 过程卡：多模型模式三段「领队理解 / 工人执行 / 汇总回复」；工具事件把 worker/task/结果写入新的 `DispatchCard`。

UI：

- 设置页「多模型协作（实验）」区块：开关、当前配对、峰值估算、缺失文件提示。
- 顶部胶囊在多模型模式下显示「双模型 · 4K」。
- 消息卡片新增派单卡：工人名、子任务、结果（成功/失败）。

## 4. 内存与代价

| 组成 | 估算 |
|---|---|
| 领队 1.7B Q5 权重 | 1.47 GB |
| 领队 4K KV | 0.44 GB |
| 工人 0.6B Q5 权重 | 0.53 GB |
| 工人 2K KV | 0.22 GB |
| 运行时缓冲 | ~0.4 GB |
| **合计（4K）** | **≈3.1 GB** |

8GB 机型可行但余量小；16K 领队上下文合计约 4.4 GB，开关处标红提示。工人量化可选 Q4（省 70MB），首版优先 Q5。

## 5. 验收

1. `scripts/gate.sh` 全绿（引擎 36+ 单测）。
2. `xcodebuild -sdk iphoneos CODE_SIGNING_ALLOWED=NO` 编译通过（不连手机）。
3. 真机（手机连接后）：
   - 关闭开关 → 原单模型对话/工具回归正常。
   - 开启开关（两模型已导入）→ 「明天下午三点提醒我吃药」出现派单卡，工人参数 `2026-11-08 15:00`，确认后写入提醒，领队汇总。
   - 「下周三上午十点安排产品评审会，开一小时」→ `2026-11-11 10:00–11:00`。
   - 关闭开关 → 原模型恢复，历史保留。
4. 失败路径：未导入工人模型时开关禁用；工人输出无工具调用时界面显示失败原因。

## 6. 回滚

- 引擎：`WorkerDispatcher` 缓存键改动独立，revert 即回单工人一引擎。
- iOS：开关默认关闭；删除设置区块与 `DispatchCard` 渲染即回旧 UI；模型文件不内置进包。

## 7. 不在本切片

- 翻译/摘要执行器。
- 双模型同时常驻的精细内存回收（后台/内存警告自动卸载工人）。
- 多工人并行派单、Agent 邮箱。
- 双模型 harness 自动回归（先人工真机走查，稳定后再补用例）。

## 8. 实施记录（2026-11-08 00:00）

- 引擎：`WorkerDispatcher` 缓存键改为「模型路径|量化|上下文」，四种工人共用同一 0.6B；单测 38/38 + `scripts/gate.sh` PASS。
- 对齐修正：工人训练 user 全部以「派单：」开头，`dispatch` 入口自动补齐前缀（已带则不重复）。
- iOS：`DemoModel` 增加多模型开关/配对识别/领队 system 日期注入/派单卡；设置页新增「多模型协作（实验）」及峰值估算；单模型档位列表隐藏双模型配对文件，双模型使用中禁止删除配对文件。
- 编译：`xcodebuild -sdk iphoneos CODE_SIGNING_ALLOWED=NO` BUILD SUCCEEDED（未连手机）。
- 待办：手机连接后推送 `qwen3-1.7b-sft20-Q5_K_M.gguf` 与 `qwen3-0.6b-sft20c-Q5_K_M.gguf` 到 `Documents/Models`，真机走查开关、派单、日期与 EventKit 确认。
- 真机推送命令（UDID 按实际替换）：
  ```bash
  DEV=/Applications/Xcode.app/Contents/Developer/usr/bin/devicectl
  $DEV device copy to --device <UDID> --domain-type appDataContainer \
    --domain-identifier com.enginekit.ios-shell \
    --source train/gguf/qwen3-1.7b-sft20-20261106/qwen3-1.7b-sft20-Q5_K_M.gguf \
    --destination Documents/Models/qwen3-1.7b-sft20-Q5_K_M.gguf
  $DEV device copy to --device <UDID> --domain-type appDataContainer \
    --domain-identifier com.enginekit.ios-shell \
    --source train/gguf/qwen3-0.6b-sft20c-20261106/qwen3-0.6b-sft20c-Q5_K_M.gguf \
    --destination Documents/Models/qwen3-0.6b-sft20c-Q5_K_M.gguf
  ```

## 9. 工作流可视化（2026-11-08 追加）

- 设置页多模型区块新增「工作流可视化」开关（默认开，`workflowVisualizationEnabled` 持久化）。
- 引擎新增 `DispatchStage`（started → workerOutput → finished），由 `WorkerDispatcher` / `DispatchTool` 在真实阶段回调；不是定时假动画。
- iOS 聊天页在双模型 + 开关开启时，用 `WorkflowCard` 替代原过程卡：
  - 四节点：领队 1.7B → 工人 0.6B → 工具 → 汇总；
  - 节点状态 pending/active/done/failed，执行中蓝色脉冲；
  - 派单明细、工具结果、总耗时、本地离线标识；
  - 领队直接回答时自动收成「领队 → 回复」两节点。
- 验证：EngineKit 39 项单测 + gate PASS；iOS `xcodebuild` BUILD SUCCEEDED。
- 界面示意：`multimodel-workflow-mockup` 可视化（设置页 + 工作流聊天页）。
