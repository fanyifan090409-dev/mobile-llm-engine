# SFT20 M5 第一切片：引擎多模型协作 + 日期表注入

> 状态：2026-11-06 起稿，用户已拍板「进行下一步」。本切片只做 Mac demo-cli 端到端，iOS 壳接入放第二切片。
> 2026-11-07 第一切片完成：36 项单测全绿；双模型实跑领队→工人派单与日期换算正确（详见第 4 节交付记录）。

## 1. 目标

让 SFT20 领队（1.7B）+ SFT20c 工人（0.6B）在 EngineKit 里真正跑起来：

1. 领队输出 `dispatch_to_worker` → 引擎拉起/复用工人 `EngineCore` → 工人输出自己的工具调用 → 应用执行 → 结果回填领队 → 领队汇总。
2. 日历/提醒工人用户消息自动追加「本周/下周/下下周」日期表（SFT20c 的硬前提）。
3. 领队/工人模型都按训练模板注入空 `<think></think>` 块。
4. 领队 system prompt 注入当天日期（SFT20 评测已验证必需）。

## 2. 接口契约

### 2.1 新增 `DateHint`
```swift
public enum DateHint {
    /// "日期参考：本周周一=2026-11-02，…；下周周一=…；下下周周一=…。"
    /// 周约定 ISO（周一起），格式与 SFT20c 训练数据逐字一致
    public static func threeWeekTable(for date: Date = Date(),
                                      calendar: Calendar = .current) -> String
}
```

### 2.2 新增 `WorkerProfile`
```swift
public struct WorkerProfile: Sendable {
    public let name: String          // calendar_worker 等
    public let systemPrompt: String  // 与 SFT20 worker_sft20.jsonl 逐字一致
    public let modelURL: URL
    public let quant: String
    public let context: Int
    public let thinkTags: Bool       // SFT20c = true
    public let needsDateTable: Bool  // 日历/提醒 true
}
```

### 2.3 新增 `WorkerDispatcher`（actor）
```swift
public struct WorkerToolCall: Sendable {
    public let worker: String
    public let toolName: String
    public let arguments: [String: String]
    public let rawText: String
}

public actor WorkerDispatcher {
    public init(profiles: [WorkerProfile],
                runner: (@Sendable (WorkerProfile, [Message]) async throws -> String)? = nil)
    public func dispatch(worker: String, task: String, now: Date = Date()) async throws -> WorkerToolCall
    public func unloadAll()
}
```
- 默认 runner 每个工人一个懒加载 `EngineCore`，工人模型共用同一个 GGUF 时按模型路径缓存实例。
- 无 runner 注入时真正跑 llama；测试注入假 runner，只校验提示词拼装。

### 2.4 新增 `DispatchTool: LocalTool`
- `ToolSpec.name = "dispatch_to_worker"`，参数 `worker` + `task`。
- `feedbackStyle = .result`（领队训练数据的工具回填是 `{"status":"ok","result":"…"}`，不是 `event_id`）。
- 可选 `executor: @Sendable (WorkerToolCall) async throws -> ToolResult`：demo-cli 传入真实日历/提醒工具；不传则返回「已生成工具调用（未执行）」。
- 工人返回的 `<tool_call>` 用现有 `ToolCallParser` 解析。

### 2.5 `ToolSpec` 增加 `feedbackStyle`
```swift
public enum ToolFeedbackStyle: String, Codable, Sendable { case eventID, result }
```
默认 `.eventID`，SFT3 单模型工具行为不变；派单工具用 `.result`。

## 3. 目录

- `engine/Sources/EngineKit/DateHint.swift`
- `engine/Sources/EngineKit/WorkerProfile.swift`
- `engine/Sources/EngineKit/WorkerDispatcher.swift`
- `engine/Sources/EngineKit/ToolKit/DispatchTool.swift`
- 改：`ToolSpec.swift`、`ToolLoop.swift`、`apps/demo-cli/Sources/demo-cli/main.swift`
- 测试：`engine/Tests/EngineKitTests/DateHintTests.swift`、`WorkerDispatcherTests.swift`

## 4. 验收

- `swift test` 全绿；新增用例：
  - 2026-11-06（周五）→ 本周一 11-02、下周一 11-09、下下周日 11-22；跨年 2026-12-31 正确。
  - 假 runner 校验：日历/提醒工人 user = task + 日期表；翻译/摘要不加表；system prompt 逐字一致。
  - `.result` 回填形状 `{"status":"ok","result":"…"}`；`.eventID` 旧形状不变。
- demo-cli 双模型实跑：
  `demo-cli --model qwen3-1.7b-sft20-Q5 --worker-model qwen3-0.6b-sft20c-Q5 --think-tags --worker-think-tags --tools -p "明天下午三点提醒我吃药"`
  期望：领队派 `reminder_worker` → 工人输出 `set_reminder` 且日期为明天 → 工具执行（trust 模式）→ 领队汇总。

### 交付记录（2026-11-07）

- 构建：`apps/demo-cli` `swift build` 通过；注意测试须用 `DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer`（CLT 无 Testing 模块）。
- 单测：`swift test` 36/36 通过（日期表/闰日/跨年/提示词拼装/回填形状/超时）。
- 实跑（`--trust-tools`，日期表随工人消息注入）：
  - “明天下午三点提醒我吃药” → 领队派 `reminder_worker`；工人 `set_reminder {"content":"吃药","remind_time":"2026-11-08 15:00"}`。
  - “下周三上午十点安排产品评审会，开一小时” → 工人 `add_calendar_event {"start_time":"2026-11-11 10:00","end_time":"2026-11-11 11:00"}`。
- 阻塞项：Mac CLI 进程未获 EventKit 授权（日历/提醒均报“访问被拒绝”），写入步骤止于 TCC；引擎派单/日期/工具调用链已验证，iOS 端由应用内权限弹窗解决。
- 性能参考（M5 Air，Q5 双模型）：解码 34.5–37.9 tok/s，峰值内存约 2.9–3.0 GB。

## 5. 回滚

- 新文件独立；`ToolSpec.feedbackStyle` 默认值保证旧路径不变。
- demo-cli 不传 `--worker-model` 时完全走旧单模型路径。
- 回滚 = 删除新文件 + revert ToolSpec/ToolLoop 两处小改。

## 6. 不在本切片

- iOS 壳双模型 UI/内存档位/工人执行器接入。
- 邮箱持久化、并行派单、多轮多工人调度。
- 翻译/摘要工具的实际执行（本切片只到日历/提醒）。
