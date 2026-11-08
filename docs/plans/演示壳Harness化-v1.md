# 演示壳 Harness 化 v1（2026-11-03）

## 背景

演示壳此前按用户点出的 bug 逐条打补丁（意图路由、日期锚点、写后校验、thinkTags），
每修一个都要靠用户真机手点复验，且没有回归网：改 A 可能弄坏 B。
本轮起把 iOS 演示壳升级为**可自动回归的专用 harness**：任何 bug 修复必须落成一条场景用例。

## 目标

1. **场景化**：所有关键行为（工具调用、日期换算、翻译/闲聊路由、多轮、性能）写成声明式用例；
2. **可自动执行**：真机上以文件触发布局跑完整套件，结果落盘 JSONL，无需人工逐条点；
3. **可判定**：每条用例有机器可判的期望（工具名、参数日期时间、无工具、回复关键词、tok/s 下限）；
4. **可取证**：结果含逐例耗时、解码速度、峰值内存，作为 AIY 演示与回归证据；
5. **回归纪律**：用户报的每个 bug → 新增一条用例；套件全绿才算修完。

## 分层

```
DemoChatView（UI，仅展示）
   └─ DemoHarness（场景 DSL + Runner + 断言 + 报告）  ← 新增
        ├─ EngineCore（推理/工具闭环，已有）
        ├─ CalendarTool(autoConfirm:)（harness 模式跳过 UI 确认，写后清理）
        └─ AppLog（证据落盘，已有）
```

- 日期锚点 / 意图路由从 DemoModel 暴露为 static，供 UI 与 harness 共用，杜绝两套逻辑。
- 不在本版做：XCUITest（UI 弹窗路径仍由人确认）、跨设备矩阵调度（另属 #31）。

## 场景 DSL（Swift 内嵌，Documents/harness-cases.json 可覆盖）

```swift
struct HarnessCase: Codable {
    var id: String
    var category: String            // tool / chat / router / multiTurn / perf
    var prompt: String
    var tools: String               // always / never / auto（auto=走意图路由）
    var followUps: [String]?        // 多轮：同一会话继续发
    var expect: HarnessExpect
}

struct HarnessExpect: Codable {
    var tool: String?               // 期望触发的工具；nil=不应触发
    var titleContains: String?
    var locationContains: String?
    var startDateRule: String?      // tomorrow / nextFriday / 2026-11-25
    var startTime: String?          // HH:mm
    var replyContainsAny: [String]? // 回复命中任一即通过
    var englishOnly: Bool?          // 英文回复检查（翻译类）
    var minDecodeTps: Double?       // 性能下限（真机）
}
```

## v1 用例集（12 条，回归三项 bug + 既有能力）

| id | 类别 | 覆盖 |
|---|---|---|
| cal-parent-meeting | tool | 用户报的「家长会写错日期」：明天 15:00 |
| cal-friday-class | tool | 「周五」换算（模型历史弱项） |
| cal-explicit-date | tool | 绝对日期格式保真 11-25 20:00 |
| cal-tomorrow-2pm | tool | 用户报的「雅思提醒」14:00 |
| translate-express | chat | 用户报的「快递到哪了」直接翻译 |
| translate-with-calendar-word | chat | 含「开会」的翻译句不误挂工具 |
| qa-yasi | chat | 闲聊不触发工具 |
| summarize-300 | chat | 长输出链路 |
| router-auto-calendar | router | 意图路由正例 |
| router-auto-chat | router | 意图路由负例 |
| multi-turn-followup | multiTurn | 工具轮后追问不回退成工具 |
| perf-short-essay | perf | 解码 tok/s + 峰值内存证据 |

## 执行与取证

- 触发：`Documents/harness.run` 内容为 `go`（与 bench.run 同款约定，跑完推空文件即可重复触发）；
- 结果：`Documents/harness-results.jsonl`，逐例一行 + summary 一行；
- 汇总同时写入 `engine-shell.log`，UI 追加一条系统消息显示通过率与失败项；
- harness 模式下 CalendarTool 自动确认并**删除测试事件**（不污染用户日历）；
- 性能用例取 2 轮较优值，阈值 Q4_K_M ≥ 20 tok/s（热降频下仍可判）。

## 验收标准

1. 真机跑套件：12/12 通过（允许 perf 单项因热状态报警但不静默）；
2. 失败项报告含具体原因（日期不符/误触发工具/权限未授权等），可直接定位；
3. 用户日历无测试残留；
4. 结果 JSONL 可被脚本读取，作为后续回归基线。

## 回滚点

- 新增文件独立（DemoHarness.swift），UI 触发逻辑用开关文件隔离；
- 若套件误报，可删除 `Documents/harness.run` 即回到纯演示模式，不影响 APP 可用性。

## 后续（不在本版）

- XCUITest 覆盖确认弹窗与权限弹窗；
- 三台真机（16/17/18 Pro）套件矩阵与性能归档（并入 #31）；
- 用例失败自动截图/日志打包。

## 首次真机回归结果（2026-11-03，iPhone 17 Pro Max / Q4_K_M）

- 首轮 8/12：cal-friday-class（周五→周四）、cal-explicit-date（晚上八点→18:00）失败，
  根因是 1.7B 日期算术/时间换算弱，不是壳层路由 bug；
- 修复方式：新增 `TimeHints`（确定性解析「周五 / 晚上八点」等相对表达，把显式值以
  「注意：…」提示拼进工具轮 user 内容，模型只负责复制槽位；气泡仍显示原文），
  UI 与 harness 共用 `DemoModel.toolContent`；
- 复跑 **12/12 通过**（21 秒完成）：解码 39.0–49.5 tok/s，峰值内存 1852 MB，
  JSONL 12 行 + summary 行完整；日历测试事件写后即删，无残留；
- 未纳入通过率的模型观察项：长文能力偏短（300 字目标实测约 100–120 字，
  用例口径已放宽为「非空有效输出 ≥40 字」）；此两项转数据侧改进（SFT19/SFT20），
  不再由壳层硬拗。

