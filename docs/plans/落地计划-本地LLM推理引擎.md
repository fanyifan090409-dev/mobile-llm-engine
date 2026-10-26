# 落地计划 — 移动端本地 LLM 推理引擎

> 规划时间：2026-10-23
> 状态：待用户拍板（路线 / M0 启动 / 训练机启用方式）
> 依据文档：docs/调研-本地LLM推理引擎选型.md（含第十节训练算力核算）

## 一、目标与范围（用户原话对齐）

**目标**：全新的推理引擎，让小模型本地部署到手机端，完成一些简单任务。

- 范围（本次计划，M0-M4）：引擎 SDK（iOS 优先 + Mac 同源）+ demo App + 单 agent 简单任务闭环（工具调用），开源发布；
- 后置（M5+，不阻塞）：本地多 Agent 协作平台（产品愿景）；训练线（agentic 后训练，需训练机启用确认）；
- 已拍板：交付形态 = 开源 SDK + demo App；首发平台 = iOS + Mac；模型侧重 = 中文优先（Qwen）；技术路线 = A（llama.cpp 底座，2026-10-23 确认）；
- 开工前新锁定（2026-10-23 用户嘱咐）：
  1. **速度档位 ≥4**：用户可调 token 生成速度来控制硬件负载（运行时特性，与内存档位正交），映射表 M2 真机实测后固化；
  2. **一键换模型**：模型下载/切换零门槛，无代码基础用户也能体验本地部署（不做桌面式手工部署）；
  3. **模型库首发 3 个，全部自训**：训练线从「后置」升级为「发布前置条件」（M4 发布依赖）；
  4. **训练画像 = 手机高频需求**：翻译、实时记录整理、日程提醒、消息文案、摘要检索；不做编程/项目类任务；
  5. **训练机**：两个常驻模型服务已下线（保留可恢复，不破坏），双卡 5090 全部用于训练；训练前先做大量设想与计划（见训练计划文档）。

### 使用形态（手机没有终端，「落地」长什么样）

终端只属于开发环境（Mac CLI 只做基准测试，不进交付）。对手机而言落地是两个渠道：

1. **用户渠道 = demo App（我们做）**：App Store 下载 → 自动检测内存推荐档位（6GB 推 1.7B / 12GB 推 4B）→ WiFi 下载 GGUF（或 AirDrop/「文件」App 导入）→ 全程离线使用。用户看到的形态和 PocketPal/MLC Chat 一样是「一个 App」，引擎编译在 App 内、对用户不可见；
2. **开发者渠道 = EngineKit SDK（产品本体）**：其他 App 开发者 `import EngineKit`，App 即内置本地 LLM 能力（类比：地图 App 内置地图 SDK、微信内置音视频引擎）。「引擎」的落法 = 让任何 App 装上本地推理能力；
3. **简单任务在手机上的样子**：用户说「帮我把明天下午三点加个提醒」→ 模型走工具调用 → 经 App Intents 建出系统提醒 → 全程无网。即 M4 验收闭环。

## 二、模型选型的依据（六条，硬门槛一票否决 + 软项加权）

| # | 维度 | 类型 | 标准 |
|---|---|---|---|
| 1 | 许可 | 硬门槛 | Apache 2.0 / MIT / BSD；拒绝 AGPL（传染 SDK）、Llama Community（>7 亿 MAU 需授权） |
| 2 | 内存适配 | 硬门槛 | Q4 量化权重 + 4K KV cache + 运行时开销 ≤ 目标档位内存预算（见第四节分档表） |
| 3 | 速度下限 | 硬门槛 | 目标机型 Metal/Vulkan 实测 ≥ 5-8 tok/s（简单任务可用线），测不猜 |
| 4 | 任务能力 | 软项 ×0.35 | 原生 tool/function calling、结构化 JSON 输出、指令跟随 |
| 5 | 中文能力 | 软项 ×0.25 | 中文对话与工具调用质量（目标用户中文优先） |
| 6 | 生态适配 | 软项 ×0.25 | 官方 GGUF 供给、llama.cpp 一等公民（避免转档出坑） |
| 7 | 可持续性 | 软项 ×0.15 | 社区活跃、更新频率、公开基准口碑 |

**候选打分**（软项 ★1-5）：

| 模型 | 许可 | Q4 权重 | 4K KV | 工具调用 | 中文 | GGUF | 综合判定 |
|---|---|---|---|---|---|---|---|
| Qwen3-0.6B | Apache 2.0 ✅ | ~0.4GB | ~0.45GB | ★3 | ★5 | 官方 | 低内存兜底档 |
| **Qwen3-1.7B** | Apache 2.0 ✅ | ~1.0GB | ~0.45GB | ★5 | ★5 | 官方 | **主力档** |
| **Qwen3-4B** | Apache 2.0 ✅ | ~2.4GB | ~0.6GB | ★5 | ★5 | 官方 | **旗舰档** |
| MiniCPM5-2B | Apache 2.0 ✅ | ~1.4GB | ~0.5GB | ★5（agent 特化） | ★5 | 官方 | agent 对拍标杆（训练线对标） |
| Gemma 4 E2B | Apache 2.0 ✅ | ~1.6GB | 128K ctx | ★5（原生 fc） | ★3 | 社区 | 多模态/英文扩展候选 |
| SmolLM3-3B | Apache 2.0 ✅ | ~1.9GB | 128K ctx | ★4 | ★2 | 社区 | 长上下文扩展候选 |
| Phi-4-mini | MIT ✅ | ~2.4GB | 128K ctx | ★4 | ★3 | 官方 | 英文备选 |
| Llama 3.2 1B/3B | 许可受限 ✗ | — | — | — | — | — | 出局 |

**选型逻辑一句话**：内存预算定档位 → 档位内按「任务能力 × 中文 × GGUF 生态」选 → **Qwen3 家族三档全胜**（同一家族还能保证工具调用行为一致）。MiniCPM5-2B 不首发但必测——它是端侧 agent 榜第一，是训练线的对拍目标。

## 三、普通人手机能不能带动（答案：能，靠内存分档自动选模型）

运行占用 ≈ Q4 权重 + KV cache + 框架开销（~0.3GB）。

| 模型 | 权重 | 4K KV | 合计 | 速度（iPhone Metal / 中端 Android Vulkan） |
|---|---|---|---|---|
| Qwen3-0.6B | 0.4GB | 0.45GB | ~1.1GB | 25+ / 20+ tok/s |
| Qwen3-1.7B | 1.0GB | 0.45GB | ~1.7GB | 10-15 / 8-12 tok/s |
| Qwen3-4B | 2.4GB | 0.6GB | ~3.4GB | 5-8 / 4-7 tok/s |
| Qwen3-8B（Q4） | 4.9GB | 0.6GB | ~5.8GB | 旗舰机边缘，不推 |

**手机分档**（iOS 有 jetsam 硬顶：4GB 设备约 2GB、6GB 约 3GB、12GB 约 6GB 单进程上限；Android 无 jetsam 但 OEM 杀进程更狠）：

| 档位 | 典型机型 | 能跑 | 结论 |
|---|---|---|---|
| 低端 4GB | 老 iPhone SE / 入门 Android | 0.6B | 兜底档，能聊不能干复杂活 |
| **主流 6-8GB** | **iPhone 12-15 / 中端 Android（普通人手机主力）** | **1.7B Q4 ✅** | **简单任务完全可用** |
| 旗舰 12GB | iPhone 16 Pro+/18 Pro Max/旗舰 Android | 4B Q4 ✅ | 效果最好 |

**简单任务的时间账**（1.7B 档，10 tok/s）：查日程、写消息、总结 200 字这类任务回答 100-300 token ≈ 10-30 秒完成——普通人可接受。

**结论**：普通人手机带的动。前提是运行时**按设备内存自动选档位**（0.6B/1.7B/4B 三档），这正是桌面引擎没有、我们要做的「移动优先运行时」核心功能，也是选型表锁 Qwen3 三档的原因——三个档位行为一致，用户无感。

## 四、架构与目录

```
90ee63b2/
├── AGENTS.md
├── docs/plans/                     # 本计划 + 后续功能计划
├── engine/                         # Swift Package「EngineKit」
│   ├── Sources/EngineKit/          # 运行时：内存预算、档位选择、热控、生命周期、流式 API
│   ├── Sources/CLLaMA/             # llama.cpp C 绑定薄封装（桥接层，不碰 kernel）
│   └── Tests/
├── apps/demo-cli/                  # Mac 基准 CLI（对话 + tok/s + 内存）
├── apps/demo-ios/                  # SwiftUI demo App
├── models/                         # GGUF 下载脚本 + 清单（模型文件 gitignore）
├── scripts/gate.sh                 # 门禁：swift build + swift test
└── train/                          # 训练机侧脚本（后置）
```

## 五、接口契约 v0.1（M3 冻结）

```swift
public enum MemoryTier: CaseIterable { case low, standard, high }   // 0.6B / 1.7B / 4B 档
public enum SpeedTier: Int, CaseIterable { case powerSaver, balanced, performance, turbo }  // ≥4 档速度/功耗档（用户可调）

public struct ModelSpec {
    let fileURL: URL        // GGUF
    let quant: Quant        // Q4_K_M 等
    let context: Int        // KV 上限，与内存预算联算
}

public struct GenerationRequest {
    let messages: [Message]
    let tools: [ToolSchema]?            // 简单任务：工具调用
    let maxTokens: Int
    let temperature: Double
    let speed: SpeedTier = .balanced   // 用户速度档位 → ngl/线程/投机解码映射
}

public protocol LocalEngine {
    func resolveTier(deviceMemory: Int) -> MemoryTier?   // 内存预算 → 可用档位（核心差异化）
    func load(_ spec: ModelSpec, tier: MemoryTier) async throws
    func generate(_ req: GenerationRequest) -> AsyncThrowingStream<TokenEvent, Error>
    func unload()                                       // 内存墙：用后即卸
}
```

## 六、里程碑（M0-M5，单人 + Agent 辅助）

| 里程碑 | 内容 | 产出 | 验收标准 | 预估 |
|---|---|---|---|---|
| **M0 地基** | git init、.gitignore、Xcode/SPM 工具链验证、llama.cpp 依赖审批（锁 tag）、门禁脚本 | 可编译空 Package | `swift build && swift test` 全绿 | 0.5-1 周 |
| **M1 Mac 推理链路** | llama.cpp 集成（参考官方 llama.swiftui）、Qwen3 官方 GGUF 下载脚本、demo-cli | 双 Mac 基准表（M5 Air/M5 Pro） | 1.7B Q4 M5 Air ≥ 15 tok/s；中文质量人工抽查 10 条 | 1-2 周 |
| **M2 iOS demo** | SwiftUI App、模型导入、流式输出；iPhone 18 Pro Max 真机内存/速度/热曲线 | 真机数据表（热降频曲线是 M3 输入） | 真机 1.7B ≥ 8 tok/s、内存峰值 < jetsam、10 分钟连续生成不崩 | 2-3 周 |
| **M3 运行时 SDK** | 内存预算感知档位自动选、热感知降档、断点续推、按需下载 | EngineKit v0.1 + 单测 + API 文档 | 单测覆盖档位选择逻辑；demo 切到 SDK | 3-4 周 |
| **M4 简单任务闭环** | 工具调用循环 + 2 个本地工具（日程提醒/本地笔记）、结构化输出；自建 50 条中文任务评测集；一键换模型全流程 | **开源发布**：MIT、README、中文文档、发布博客；**模型库首发 3 个自训模型 GGUF** | 任务成功率 ≥ 80%；非技术用户 5 分钟内完成模型下载+切换；3 个自训模型上线 | 3-4 周 |
| **训1 训练线（与 M1-M3 并行，M4 前置）** | 数据合成（teacher 方案待拍板）→ 0.6B/1.7B/4B 三模型续训+SFT → llama-quantize 量化入库 | 3 个自训 GGUF + 训练/评测记录 | 三档位评测达标（对拍 Qwen3 原版/MiniCPM5-2B） | 2-3 周 GPU 时间 |
| **M5 后置** | 多 agent 协作 1 模式 | 协作协议 v0.1 | 待定 | — |

**总时长：约 2.5-3.5 个月到 M4 开源发布。** 开发期（M1-M3）用 Qwen3 官方 GGUF 做工程替身；**发布模型必须是自训三档**（训1 与开发并行，M4 前完成）。

## 七、依赖审批清单（请用户批）

1. **llama.cpp**（MIT）——唯一硬依赖，用途：GGUF 推理核心，锁 tag。替代方案：MLC LLM（模型需预编译）/ MLX Swift（锁 Apple 生态）。
2. 其余零第三方依赖起步：网络 URLSession、JSON Codable、UI SwiftUI 全部原生。
3. 参考实现（只借鉴不引入，2026-10-23 源码拆解结论）：llama.rn（MIT，PocketPal 的 RN 专用 JSI 桥，钉 llama.cpp bf9a0cc≈b11385）——桥接与参数面思路可借鉴；MLC Chat（Apache 2.0）——AsyncStream 流式范式与 `os_proc_available_memory()` 加载守卫可合法参考。

## 八、风险与回滚

1. llama.cpp iOS 集成遇阻（CVE 钉版本/真机加载坑）→ M1 及早真机验证，回退备选 MLC（路线 B）；
2. 真机内存/热不达标 → 降档 0.6B 起步 + 热控提前到 M2；
3. 上游模型迭代快（Qwen3.5/Gemma 4）→ 选型表按季度复盘，接口契约不绑定具体模型；
4. 训练线质量不达标 → 三档对拍（Qwen3 原版/MiniCPM5-2B），不达标先发官方模型占位，自训达标后替换入库；
5. Apple AFM（iOS 26+ 免费端侧模型）挤压 → demo 主打工具调用/离线可控/模型自由，不做通用聊天；
6. 每个里程碑打 tag，可回退。

## 九、待用户拍板

1. ~~技术路线：A（llama.cpp 底座，推荐）/ B（MLC）/ C（平台原生）~~ → **已拍板：路线 A（2026-10-23）**；
2. ~~计划修改点~~ → **已锁定：开工前 5 条新要求（速度档位≥4 / 一键换模型 / 3 个自训模型 / 手机需求画像 / 双卡全训）**；
3. ~~训练机 GPU 启用方式~~ → **已定：常驻双服务下线（保留可恢复），双卡全训（2026-10-23 已执行）**；
4. 训练计划（设想）确认 → 确认后开工 M0 与数据合成（合成 teacher 方案 A/B 见训练计划第三节）。
