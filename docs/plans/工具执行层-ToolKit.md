# 工具执行层 ToolKit 计划（v0.1 草案）

> 状态：**T1-T3 已执行完毕（2026-10-26）**：契约骨架 + ToolLoop 两段解码 + demo-cli CalendarTool 端到端。
> 引擎闭环用官方 1.7B 实测通过；0.6B SFT2 工具调用遵循率实测不达标（风险 1 应验，训练线修复，见第 7 节与 §10）。
> 定位：产品价值 = 窄任务 + 可靠执行。本模块是产品成立的胜负手，升格为 **M2 并列目标**（不是 M3 顺带项）。
> 本计划只管「模型输出工具调用 → 本地执行 → 结果回填」闭环；多 Agent（M5+）不在范围。

## 1. 现状盘点（为什么是最大空白）

| 层 | 现状 |
|---|---|
| 训练侧 | SFT 数据已埋工具调用种子：schedule 类 8756 个 tool_call 样本（10M 总量） |
| 引擎侧（M1） | **纯文本进出**：加载/流式生成/卸载。无工具注册表、无 JSON 校验、无执行层 |
| 空白段 | 模型输出 `{"name":"add_calendar_event",...}` 之后无人接住——闹钟不会响，产品不成立 |

**训练数据契约（已核实，引擎必须逐字节对齐）**：
- 格式：Qwen3 XML，内嵌 assistant content：`<tool_call>\n{"name": "...", "arguments": {...}}\n</tool_call>`
- 首轮唯一工具 `add_calendar_event`，参数：`title`（必填）、`start_time`/`end_time`（必填，正则 `^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$`）、`location`（可选）、`note`（可选）
- 轨迹：`user → assistant(tool_call) → tool{content: {"status":"ok","event_id":"evt_xxx"}} → assistant(一句中文确认)`
- 训练时 user 消息干净、**无工具清单注入**（单工具时代模型直接从指令判断）

## 2. 接口契约（冻结）

```swift
// ---- 工具定义（引擎层纯 Swift，零平台依赖）----
public struct ToolParameterSpec: Codable {
    public let name: String
    public let type: String          // JSON Schema 类型：string / integer / number / boolean
    public let description: String   // 给模型的参数说明（多工具清单注入期使用）
    public let required: Bool
}

public struct ToolSpec: Codable {
    public let name: String
    public let description: String
    public let parameters: [ToolParameterSpec]
}

// ---- 工具实现（app 层注册；确认 UI 在 execute 内部处理，引擎无感知）----
public protocol LocalTool {
    var spec: ToolSpec { get }
    func execute(_ arguments: [String: Any]) async throws -> ToolResult
}

public struct ToolResult: Codable {
    public let status: String        // "ok" | "error"（对齐训练数据回填格式）
    public let content: String       // 给模型的结果（ok 时如 event_id；error 时为可读错误原因）
}

// ---- 引擎集成（扩展 M1 契约，不改已有方法签名；demo-cli 无需改动）----
// GenerationRequest 扩展（带默认值，不破坏现有调用方）：
//   public var tools: [String]?     // nil=纯文本模式（M1 行为）；[name...]=本次启用的工具白名单子集
// LocalEngine 协议新增：
//   func registerTool(_ tool: LocalTool)      // 白名单编译期注册（不动态加载）

// TokenEvent 扩展：
//   case toolCall(ToolCallEvent)              // UI 层显示「正在设置日程…」
public struct ToolCallEvent {
    public let toolName: String
    public let arguments: [String: Any]        // JSONSerialization 解析结果
    public let status: ToolCallStatus          // executed / rejected / failed
    public let resultText: String
}
```

## 3. 执行循环（T2 核心设计：两段解码）

```
用户输入 → 解码 ──检测到 </tool_call>（或裸 JSON 的 "arguments" 键）──▶ 暂停自回归
                                              │
        ┌─────────────────────────────────────┘
        ▼
① 提取 <tool_call>…</tool_call> 间文本 → JSON 解析（容错：剥离 markdown 围栏、外层 tool_call 键、
   无 XML 包裹的裸 JSON 尾部 {…} 段——T3 实测官方 1.7B 输出裸 JSON，已兜住）
② 白名单校验：工具名不在 registry → 拒绝执行（防幻觉工具名），错误回填
③ 参数 schema 校验：必填/类型/时间正则（与训练期 QC 同款规则）
④ await tool.execute(args)（超时默认 5s；含用户确认等待的工具由集成方传 nil 不限时——
   T3 实测发现确认时长由用户决定，引擎不能替用户设限）
⑤ 结果以 role="tool" 消息回填（带 tool_call_id，对齐训练轨迹）→ 继续解码出确认话术
⑥ 循环上限 3 轮；校验失败回填错误让模型改一次，仍失败 → 终止循环转纯文本兜底
```

- **为什么流中检测而不是生成完解析**：小模型生成完 tool_call 后可能继续胡说，流中截断干净。
  实现期决定走**字符串级检测**（累积文本命中 `</tool_call>` 或 `"arguments"`）而非 token-ID 级：
  解析层本来就是字符串，且自转 GGUF 缺 added_tokens 元数据（tech-debt #1），
  字符串检测天然规避 tokenizer 差异；误报由 parseCall 解析失败→继续生成兜住。
- **单工具期不注入工具清单**（与训练数据分布一致）；多工具期（M2+）清单注入放 system/首条 user 消息，格式待定。
- 线程模型：工具循环跑在 generation 队列内（同一会话串行），流事件经 AsyncThrowingStream 回 UI。

## 4. iOS 系统能力边界（诚实清单，产品决策依据）

| 能力 | iOS 公开 API | 备注 |
|---|---|---|
| 日历增/查/删 | ✓ EventKit `EKEventStore` | 需 `NSCalendarsUsageDescription` 权限描述 |
| 提醒事项 | ✓ EventKit `EKReminder` | 同上 |
| **闹钟** | ✗ **无公开 API**（Clock.app 不开放） | 产品替代：提醒事项/计时器——待拍板 ② |
| 备忘录 | ✗ Notes 无 API | 替代：app 内存储或映射提醒事项 |
| 天气/联网查询 | ⚠ 需网络 | PIPL 默认不做，数据不出设备 |
| App Intents | ✓ iOS 16+ | M2+ 评估：把工具能力暴露给 Siri/快捷指令的官方正道 |

## 5. 目录结构

```
engine/Sources/EngineKit/ToolKit/     # 引擎层：纯 Swift，无平台依赖
├── ToolSpec.swift                     # ToolSpec / ToolParameterSpec / ToolResult
├── LocalTool.swift                    # LocalTool 协议 + ToolCallEvent
├── ToolRegistry.swift                 # 白名单注册表（查重、查找、清单生成）
├── ToolCallParser.swift               # XML 提取 + JSON 容错解析
├── ToolCallValidator.swift            # schema 校验（必填/类型/时间正则）
└── ToolLoop.swift                     # 两段解码循环（T2 加）
apps/demo-cli/Sources/                 # app 层：真实工具实现（T3 加）
└── CalendarTool.swift                 # EventKit add_calendar_event 实现
```

## 6. 步骤与验收（每步一个 commit，门禁全绿才合入）

| 步 | 内容 | 验收 |
|---|---|---|
| T1 | 契约冻结 + ToolKit 骨架（Spec/Registry/Parser/Validator） | ✅ 单测 10 条全绿：registry 查重拒绝、白名单拒绝、时间正则边界、markdown 围栏容错 |
| T2 | ToolLoop 两段解码集成 EngineCore + mock 工具 | ✅ 单测 24 条全绿：四路径（正常/缺参回填/幻觉拒绝/超时）+ 轮数上限 + 用户取消映射 |
| T3 | demo-cli 接 EventKit 真实工具 | ✅ 引擎闭环实测通过（见 §10）；日历真写入受 CLI 无 bundle 限制（TCC 拒绝），真机 iOS 验证归 T4 |
| T4 | iOS 适配（M2 后）：权限流、确认 UI、真机三台验证 | 真机端到端通过 + 权限拒绝路径 |
| T5 | 评测链接入「工具调用遵循率」（格式正确率/参数正确率/端到端成功率） | 与今晚报告 schedule 解析率口径对齐 |

## 7. 风险与对策

1. **0.6B 工具格式遵循率不达标**（最大风险，**T3 实测已应验**）→ 训练分布同款 prompt 下贪心/采样都不发 tool_call，
   直接口头确认（SFT2 含 8581 条 schedule 轨迹 ×2 epochs 仍失效）；对策升级为 SFT3 专项：schedule 占比调高 +
   合成期 system 提示进推理模板（/no_think）+ 若仍不达标考虑 1.7B 做工具基座。
2. **流中检测误报/漏报** → 已缓解：字符串级触发 + parseCall 解析失败即继续生成；官方 1.7B 裸 JSON 形状已实测兜住。
3. **确认类操作阻塞** → 确认下沉到工具实现内部（app 层 UI），引擎只 await；执行超时对交互工具传 nil（T3 修正）。
4. **iOS 闹钟无 API** → 待拍板 ②，产品层替代方案先行。
5. **训练数据 tool 消息带 `tool_call_id`** → 引擎回填同款字段（`call_` + uuid8），token-ID 模板扩展 tool 角色（`im_start` + `tool\n` + content），T2 实现期验证。
6. **macOS CLI 无 bundle，EventKit TCC 拒绝**（T3 实测）→ demo-cli 端到端降级为引擎闭环验证；日历真写入验证归 T4 iOS app（Info.plist 权限串 + 系统弹窗）。

## 8. 回滚点

- T1 为独立新模块，不碰 M1 推理路径，任何一步可干净回退。
- T2 若两段解码复杂度失控 → 回退 T2' 简版（生成完解析 + 单次工具调用，不做多轮循环），多轮循环后置。
- 每步一个 commit；工具白名单为编译期注册，无动态加载路径。

## 9. 已拍板（2026-10-26 用户确认）

1. **首版工具集**：单工具 `add_calendar_event`，先把最小闭环做出来（对齐训练数据，今晚评测链出遵循率基线）。
2. **闹钟替代**：用提醒事项替代（EventKit `EKReminder` 可设定时提醒）。
3. **确认策略**：写操作默认每次确认；允许用户显式开启「完全信任」模式（开启时强提醒提示风险）；删除类危险操作始终确认。
4. **里程碑**：M1.5 收尾后立即开工 ToolKit T1-T3（Mac 可全链路验证）。
5. **分工**：Tailscale 里有台 Mac Pro（workbuddy CLI 可用），可分担 M5 Pro 基准与后续部分工作。

## 10. T3 端到端实测记录（2026-10-26）

**引擎闭环（官方 1.7B Q4_K_M 实测通过）**：
- 模型输出裸 JSON（无 XML 包裹）→ `"arguments"` 键触发检测 → 解析（裸 JSON 尾部 {…} 段兜底）→ schema 校验过 →
  确认提示「『和客户开会』2026-11-05 14:00 ~ 15:00 @公司会议室」→ 执行 → 结果回填 → 模型续跑第 2 轮 → 3 轮上限生效后 stop。
- 两个实测暴露的问题已修：① 检测只认 `</tool_call>`，裸 JSON 不触发 → 触发条件扩展 + parseCall 兜底；
  ② 用户取消（status=error 不抛错）被误报 executed → 按 ToolResult.status 映射事件与回填形状。

**0.6B SFT2 遵循率实测（不达标）**：
- 训练分布同款 prompt（「帮我在手机日历里加一个事件…日期用2026年11月里的日子」）下，
  temp 0.7 与贪心（temp 0）各跑一次，均直接输出确认话术，**零 tool_call**；
  显式指令「只输出一个工具调用块」也照做不了（复述指令而不输出 XML）。
- 训练数据侧已排除：train.jsonl 含 8581 条完整 schedule 轨迹（20% 占比，2 epochs）。
- 结论：模型侧缺陷，非引擎缺陷。修复路径（SFT3 专项）：schedule 占比调高、/no_think 推理、
  合成期 system 提示进推理模板；仍不达标则 1.7B 做工具场景基座。

**EventKit CLI 限制**：demo-cli 无 app bundle，`requestFullAccessToEvents` 被 TCC 拒绝（「日历访问被拒绝」）
——预期内，日历真写入验证归 T4 iOS app。
