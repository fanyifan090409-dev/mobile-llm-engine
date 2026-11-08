# AIY27 iOS 演示壳（方向一 · 苹果原味）

- 日期：2026-11-03
- 目标：把 ios-shell 测试壳升级为参赛演示 App，用于 AIY 27 初级站 8 分钟视频的真实 Demo。
- 设计方向：用户已从三方向 mockup 选定「方向一 · 苹果原味」（Liquid Glass 玻璃卡片 + 对话 + 展开式过程卡）。
- 设计规则来源：emilkowalski/skills 的 apple-design（WWDC 设计讲座蒸馏）——弹簧参数、材质层次、字距、触感、减少动效。

## 1. 接口契约（壳 ↔ EngineKit，引擎零改动）

| 引擎 API | 壳用法 |
|---|---|
| `engine.registerTool(LocalTool)` | 注册 CalendarTool（EventKit 写日历，确认走系统弹窗） |
| `engine.generate(GenerationRequest)` | `tools: ["add_calendar_event"]`，流式收 `TokenEvent`（单次 generate 内引擎自动完成 工具调用→执行→回填→确认话术 闭环） |
| `.token(String)` | 助手气泡流式打字 |
| `.toolCall(ToolCallEvent)` | 过程卡步骤 2/3 点亮 + 结果卡数据源（真实终态） |
| `.stats(Stats)` | 过程卡底部性能行（解码 tok/s、峰值内存，真实引擎统计） |

模型：`qwen3-1.7b-sft17-Q4_K_M.gguf`（40 题日历工具调用成功率 97.5%；18 Pro Max 稳定解码 61.1 tok/s，17 Pro Max 38.5），`thinkTags: false`（SFT17 为 --no-think 训练）。findModel 改为候选清单：sft17 Q4_K_M → Q8_0 → Q5_K_M → 0.6b sft3b（取第一个存在者，Documents/Models 优先于 bundle）。

演示 prompt 用**训练分布同款格式**（40 题评测 30/30 通过）：「帮我在手机日历里加一个事件：{活动}，时间{时间短语}，地点{地点}。日期用2026年11月里的日子，时长约一小时。」——活动/时间短语/地点均取自合成期词表（家长会/明天下午三点/学校、健身私教课/周五晚上七点/健身房）。

## 2. 数据模型（壳内）

```swift
struct ChatMessage: Identifiable {
    let id = UUID()
    let role: Role            // user / assistant
    var text: String
    var steps: [ProcessStep]  // 空 = 纯文本轮
    var result: ToolResultCard?   // 工具调用成功后有
    var statsLine: String?    // 生成结束后填真实统计
}
struct ProcessStep: Identifiable {
    let id = UUID()
    let title: String         // 理解意图 / 调用工具 / 执行结果
    var detail: String?       // 如「add_calendar_event · 家长会」
    var state: StepState      // pending / active / done
    var elapsed: Double?      // 真实事件时刻-发送时刻（秒）
}
```

步骤状态机由真实事件驱动：发送→步骤1 active；首个 token→步骤1 done、步骤2 active；toolCall→步骤2 done（detail=工具名）、步骤3 active；生成结束→步骤3 done。无工具调用的轮次只显示「理解意图」+「生成回复」两步。时间来自 `Date()` 差值，不是假数据。

## 3. 界面结构（方向一）

1. **状态徽章**（顶部玻璃胶囊）：`● 离线 · 数据不出设备`，两态：模型加载中（橙点）/ 已就绪（绿点）。长按 3 秒打开日志 sheet（AppLog 证据链保留，但不出现在演示画面）。
2. **对话区**：用户气泡（系统蓝 #0A84FF、右下小尾巴）；助手玻璃卡片（流式打字 + 生成中闪烁 shimmer 条）。
3. **过程卡**（玻璃，助手回复完成后自动展开）：步骤行逐个点亮（✓ 圆章），每步右侧真实耗时；底部性能行（真实 tok/s · 峰值内存）。
4. **结果卡**（玻璃）：工具调用成功后显示——事件名、起止时间、地点、状态（数据来自 ToolCallEvent 的 validated arguments 与真实终态）。
5. **快捷短语 chips**：两个训练分布格式 prompt（家长会/明天下午三点/学校、健身私教课/周五晚上七点/健身房）——视频里免打字，一键发任务。
6. **输入栏**：玻璃圆角 + 发送按钮。

## 4. 设计 token（apple-design 规则 → SwiftUI）

- 弹簧：默认 `.spring(response: 0.35, dampingFraction: 1.0)`（临界阻尼）；无回弹——回弹只给手势携带动量的交互，本界面无此类手势。
- 步骤点亮：stagger 0.12s 递进 + 弹簧；`accessibilityReduceMotion` 时退化为直接显示（无位移无弹跳）。
- 玻璃 = `.ultraThinMaterial` 底 + 白色渐变覆盖层 + 顶部 1px 亮边（模拟材质受光）+ 浅投影。部署目标 iOS 17，不用 glassEffect（26+）。
- 触感：`.sensoryFeedback(.impact(flexible))` 发送时；`.success` 工具执行成功时（因果对齐——只在实际事件发生帧触发）。
- 字号全走语义样式（.footnote/.body/.title3），Dynamic Type 自适应；标签色 #6E6E73 系。
- 深色模式：玻璃自动加深，用户气泡保持系统蓝。

## 5. 目录

- `apps/ios-shell/Sources/CalendarTool.swift`（新增）——demo-cli 同款日历工具移植到 iOS：EventKit 写本地日历，确认闭包换成系统 UIAlertController 弹窗；usagePrompt 与训练侧 SYNTH_SYS_SCHED1 逐字一致（三处同步铁律）。
- `apps/ios-shell/Sources/DemoChatView.swift`（新增）——方向一全部 UI + DemoModel（@Observable 驱动）。
- `apps/ios-shell/Sources/ContentView.swift`（重写）——改为承载 DemoChatView。
- `apps/ios-shell/Sources/AppLog.swift`（不动）——证据链保留。

## 6. 回滚点

- 重写前 `cp ContentView.swift /tmp/ContentView.testshell.bak.swift`。
- 原测试壳逻辑（KV 清理/历史重发/token 计数/日志落盘）全部保留进 DemoModel，只是换皮不换骨。

## 7. 验证门禁

- `xcodebuild -project apps/ios-shell/EngineShell.xcodeproj -scheme EngineShell -sdk iphoneos CODE_SIGNING_ALLOWED=NO build`（本机模拟器不可用，编译级验证）。
- EngineKit 零改动，`swift build` + `swift test` 不受影响。
- 真机运行（视觉/触感/工具调用）由用户在 iPhone 上验证，视频录制前需用户走查。

## 8. 2026-11-03 晚追加（已编译，待真机验收）

- 工具扩展：日历 / 提醒 + 翻译 / 问答 / 总结 + 自动路由；时间短语解析自检 1 条，真机 Harness 13/13（21.7s、峰值 1804MB、场景解码 42–79 tok/s）。
- 模型库：速度更新为 iPhone 18 Pro Max 六档实测（Q4 61.1 / Q5 56.5 / Q8 40.1 / 0.6B 100.5 / 119.7 / 121.1）；导入前免责确认；页脚「App 仅提供本地推理环境」；关于页隐私 / 许可 / 路线（当前单 Agent，多 Agent 规划）。
- 启动钩子 `-modelLibrary` 仅用于截图/演示，不改变正常启动路径。
- 展示名改为「Agent 实验室」（`INFOPLIST_KEY_CFBundleDisplayName`）；快捷 chips 增加「总结 · 三句话」「问答 · 雅思写作」，共 6 条。
- 门禁：iOS 编译通过（`CODE_SIGNING_ALLOWED=NO`）；EngineKit `scripts/gate.sh` 24 tests 全绿。
- 待办：真机解锁后安装新签名包（device install 当前因锁屏 4016 失败），走查模型库免责 / 档位 / 关于路线 / 新 chips，再做 TestFlight 外壳验收。
