# 本地 LLM 推理引擎 — 市场调研与选型分析

> 调研时间：2026-10-23 10:47
> 调研人：Elthan（本会话）
> 目标：手机（iOS 优先）+ 低配笔记本双端本地部署小参数 LLM 的推理引擎，全新项目，与 YOLO/pose 线无关。

## 一、结论摘要

**推荐路线：以 llama.cpp 为统一底座，自研双端 SDK 层 + 演示 App。**
- iOS（Metal）、macOS/Windows（Metal/CUDA/Vulkan/CPU）、后续 Android（Vulkan）一套 C/C++ 核心覆盖全部目标平台；
- GGUF 是本地量化模型的事实标准，模型不绑定、社区供给无限；
- MIT 许可，可商用可闭源；
- 差异化打「双端统一 API + 中文优先适配 + 开源 SDK」这张牌——iOS 上现有竞品都是完整 App（PocketPal 是 MIT 但桥是 React Native 专用，MLC Chat 是 Apache 2.0 但锁 MLC 预编译模型），原生 Swift 开源 SDK 层是空白。

备选：MLC LLM（编译式、iOS 上速度最快但模型需预编译、上手门槛高）；平台原生混合（iOS 走 Core ML/Apple Foundation Models + 桌面走 llama.cpp，最省力但「引擎」叙事不成立）。

## 二、需求解读

用户原话要点：全新项目，主力做**手机上（iOS 优先）和笔记本上都能本地部署的推理引擎**，任务类型是 LLM，交付形态待定。

「引擎」二字决定产品形态是 SDK/库而非纯 App。两条价值路径：
1. **开源引擎/SDK**：社区运营、GitHub star、对美本申请/简历是硬通货（用户为国际学校高中生，美本申请中）；
2. **商用 SDK**：卖给需要本地 AI 能力的 App 开发者。

两者可组合：核心 SDK 开源 + 高级功能（模型分发服务、量化调优）商用。

## 三、引擎底座对比（2026-10 现状，官方来源为准）

| 引擎 | iOS | Android | 桌面 | 模型格式 | 许可 | 备注 |
|---|---|---|---|---|---|---|
| **llama.cpp** | ✅ Metal | ✅ Vulkan | ✅ Metal/CUDA/Vulkan/CPU | GGUF（事实标准） | MIT | GitHub 约 12.5 万 star、1450+ 贡献者，本地生态地基；官方仓库带 SwiftUI iOS 示例（llama.swiftui） |
| **MLC LLM** | ✅ Metal | ✅ OpenCL/Vulkan | ✅ CUDA/Vulkan/Metal | MLC 预编译权重（q4f16 等） | Apache 2.0 | TVM 编译式；MLCEngine 统一 API；模型须按平台预编译，自换模型门槛高；iOS 实测速度最快（Metal，约 14-20 tok/s） |
| **MediaPipe LLM Inference** | ✅ | ✅ | ❌（Web 有） | .task/.bin（Google 转换管线） | Apache 2.0 | Google 官方；模型锁定 Gemma/Phi/Falcon/StableLM 系，不能跑任意模型；产品集成最省事 |
| **ExecuTorch** | ✅ | ✅ | 部分 | .pte（AOT 编译） | BSD | PyTorch 官方端侧；LLM 生态较小，后端 XNNPACK/Core ML/Vulkan/骁龙 NPU |
| **ONNX Runtime (+GenAI)** | ⚠️ Mobile 版 | ⚠️ | ✅ 强 | ONNX | MIT | 桌面/Windows 生态好；LLM 的 ONNX 模型供给弱于 GGUF；移动端 LLM 实践案例少 |
| **MNN (阿里)** | ⚠️ 需自编译 | ✅ | ✅ | MNN 格式 | Apache 2.0 | MNN-LLM 支持 Metal；中文资料多；LLM 社区规模小于 llama.cpp |
| **Apple Foundation Models** | ✅（iOS 26+） | ❌ | ✅（macOS 26+） | 苹果私有 | 免费但模型不可分发 | 系统级 API：免费调苹果端侧 AFM + 可接任何 Language Model 协议模型；**是竞品也是潜在集成点**，但不是「自研引擎」 |

关键事实（官方核实）：
- llama.cpp：README 明确支持 Metal/Android/Windows/WebAssembly/CUDA/Vulkan，MIT，GGUF，Apple Silicon 一等公民（[官方仓库](https://github.com/ggml-org/llama.cpp)）。
- MLC LLM：Apache 2.0，iOS/Android/macOS/Windows/Linux/WebGPU 全平台，MLC 权重按平台预编译（[官方仓库](https://github.com/mlc-ai/mlc-llm)）。
- MediaPipe LLM Inference：官方文档导航含 Android/iOS/Web 三端（[Google AI Edge 文档](https://developers.google.com/edge/mediapipe/solutions/genai/llm_inference)）。
- Apple Foundation Models：iOS 26/iPadOS 26/macOS 26 起免费开放，原生 Swift，支持设备端 AFM 与任意 Language Model 协议供应商（[Apple 开发者页](https://developer.apple.com/cn/apple-intelligence/)、[Apple Newsroom](https://www.apple.com/sg/newsroom/2025/09/apples-foundation-models-framework-unlocks-new-intelligent-app-experiences/)）。
- 安全记录：2026-08 曝出 llama.cpp GGUF 解析器 5 个堆溢出 CVE（最高 8.8），Ollama/LM Studio 等受影响，升级即修复——SDK 需锁定上游版本并跟进安全更新。

## 四、小模型现状（0.6B-4B，端侧可用）

| 模型 | 参数 | 许可 | 亮点 | 端侧适配 |
|---|---|---|---|---|
| **Qwen3 系列** | 0.6B / 1.7B / 4B | Apache 2.0 | 119 语言、双思考模式、32K-128K 上下文；中文最强；官方支持 vLLM/Ollama/llama.cpp/MLC | GGUF 生态最全，社区量化版本多 |
| **Qwen3.5** | 2B / 4B | Apache 2.0 | 2026-02 发布，Gated DeltaNet 线性注意力解码加速，面向端侧 | 较新，GGUF 供给在增长 |
| **Gemma 4 E2B/E4B** | 有效 2B/4B（总 5.1B） | Apache 2.0 | 2026-04 发布；Gemma 系首次全系 Apache 2.0；128K 上下文、多模态（文本/图像/音频）、原生 function calling + 结构化 JSON；与 Pixel/高通/联发科联合优化，4GB 内存手机可跑 | 端侧性能新标杆；Ollama/llama.cpp 已支持 |
| **Gemma 3n** | E2B(2GB)/E4B(3GB) | Apache 2.0 | 2025-05 发布，移动优先多模态（音频理解） | MediaPipe/Ollama/llama.cpp 支持 |
| **SmolLM3** | 3B | Apache 2.0 | 128K 长上下文、GQA+NoPE、Think/No-Think 双模式、工具调用；11.2T token 训练；3B 级 12 项基准领先 | 完整训练管线开源，社区活跃 |
| **Phi-4-mini** | 3.8B | MIT | 推理能力在 3-4B 档口碑好；iOS 评测基准常用 | GGUF 供给成熟 |
| **Llama 3.2** | 1B / 3B | Llama Community（>7 亿 MAU 需授权） | 端侧老兵，生态深 | 许可有约束，商用注意 |

结论：**模型不绑定**（引擎支持任意 GGUF），但首发适配清单建议：Qwen3-1.7B/4B（中文）+ Gemma 4 E2B（多模态/Agent 能力）+ SmolLM3-3B（长上下文）。笔记本端可放开到 7B-14B 档（Qwen3-8B/14B 等）。

## 五、竞品格局与机会

**产品定位修正（2026-10-23 用户确认）**：不是「推理引擎」而是**本地多 Agent 协作平台**——引擎是地基，产品是 agent 运行时 + 多 agent 编排。用户判断：本地部署多 agent 协作是未来趋势（手机日常 + 笔记本办公），要做市场第一个，不完善也先占位。

### 本地/端侧 Agent 格局（2026 Q4，白热化）

| 层 | 玩家 | 形态 | 边界 |
|---|---|---|---|
| 平台系统级 | Apple：Foundation Models + App Intents（iOS 26+） | 系统编排单模型（AFM），免费 | 锁苹果生态；无跨平台、无多模型自由 |
| 平台系统级 | Google：Gemini Nano v3/v4（1.4 亿设备）+ AICore + ADK for Kotlin/Android | 官方开源 agent SDK，端云混合、多 agent 层级编排 | 仅 Android；端侧模型锁 Nano |
| 平台系统级 | 国内厂商：豆包 AI 手机跨应用协同、三星/华为/小米本地智能体沙盒、Conductor | 各自封闭入口 | 生态割据 |
| 桌面框架 | LangGraph / AutoGen / CrewAI / Microsoft Agent Framework / LocalAI v4（4.8 万星） | Python 桌面/服务器，LocalAI 已长 agent 能力（MCP、工具、RAG） | 不上手机；服务器思维 |
| 端侧研究 | PalmClaw（EMNLP 2026，Android 原生 agent 框架）、nanoMuse（「every device you own」个人 agent，GPL）、蚂蚁移动端 agent SDK（Rust 沙箱+工具系统+跨 agent 互联）、ZorvAI | Android 为主、研究/早期 | 无 iOS、无桌面、协议未定 |
| 端侧模型 | 面壁 MiniCPM5-2B（Artificial Analysis 开源 Agent 榜第一）、讯飞星火 1.7B/4B、元空 Boxer（端侧模型+Agent Runtime+长期记忆） | 模型层供给 | — |

**空白确认（带诚实的 nuance）**：
- 平台层已拥挤（Apple/Google/国内 OEM 都在抢系统级入口），但全部**生态锁定**——Apple 只服务苹果设备，ADK 端侧只跑 Android；
- **跨平台开源「本地多 agent 运行时」层是空的**：iOS + 桌面统一 SDK、模型自由（GGUF 任意换）、agent 间协作协议开源，没有任何人在做；
- 最近的对手：nanoMuse（愿景最像，但 GPL、Android 手机为主、2026-09 刚起步）、PalmClaw（研究项目）；
- **窗口期判断**：趋势已白热化（Q4 多智能体框架「指挥台」争夺战、骁龙 8 Elite Gen6 原生支持端侧多 agent 并行调度），「第一个」的位置最多保持 6-12 个月，先发优势靠社区速度而不是技术壁垒。

### 对方案的影响

1. **产品三层结构**：引擎层（llama.cpp，GGUF 模型自由——多 agent 场景下「不同 agent 用不同模型」是刚需，MLC 预编译摩擦进一步出局）+ agent 运行时层（agent loop、工具调用、记忆、沙箱、多 agent 编排，**这才是产品本体**）+ 设备接入层（Swift SDK for iOS/macOS）；
2. **模型清单加一个**：MiniCPM5-2B（端侧 agent 专用、Agent 榜第一、中文系）进入首发适配候选；Qwen3 系（工具调用强）+ Gemma 4 E2B（原生 function calling/结构化输出）保留；
3. **系统级竞品的借力**：iOS 26 的 App Intents 是「我们的 agent 调用系统能力」的现成通道——把 Apple 的平台能力当工具源，而不是当对手；
4. **「不完善也先占位」的落地方式**：开源节奏比完整度重要——先发最小可用 SDK（单 agent + 2 个工具 + 1 个协作模式），社区起势后迭代。

### iOS 本地 LLM App（2026 实测榜单）
- PocketPal AI：免费开源（MIT，2026-10-23 经 GitHub LICENSE 字段核实），llama.cpp 底座（经 MIT 许可的 llama.rn JSI 桥），事实默认选择，约 10-15 tok/s；
- MLC Chat：免费开源，Metal 加速，速度最快（14-20 tok/s）；
- LLM Farm：免费开源，可配置性最强；
- Private LLM：约 £10 买断，iOS Shortcuts/Siri 集成；
- Apple Intelligence（iOS 18+ 内置）+ iPhone 18 内置端侧大模型：系统级免费对手。

**桌面**：Ollama（MIT、llama.cpp 底座、OpenAI 兼容 API、模型库最大）、LM Studio（闭源、GUI 体验最好）、MLX（Apple Silicon 专属，非 iOS）。

**机会点（为什么还有空间）**：
1. **开源 SDK 空白**：iOS 上竞品全是「App」——PocketPal 虽是 MIT，但它是完整产品，且其 llama.cpp 桥（llama.rn）是 React Native 专用的 JSI/TurboModule，Swift 原生 App 用不了；MLC Chat（Apache 2.0）锁 MLC 预编译模型。**没有把 llama.cpp 包成原生 Swift SDK 的成熟开源项目**，「MIT 原生 Swift SDK + 移动优先运行时」仍是差异化位；
2. **双端统一**：一套 API 跑 iOS + 笔记本的产品叙事，Ollama 不碰移动端、PocketPal 不碰桌面；
3. **中文优化**：现有 iOS 竞品模型榜单以英文模型为主，中文 Qwen 系适配 + 中文文档是差异化；
4. **Apple Foundation Models 的挤压与借力**：iOS 26+ 苹果免费送端侧模型，通用聊天类 App 价值被抽干；但「可控的第三方模型引擎」（微调模型、私有部署、跨平台一致）仍有场景——叙事要避开「通用聊天」红海，主打「模型自由 + 离线可控」。

## 六、候选路线

### 路线 A：llama.cpp 统一底座 + 自研 SDK（推荐）
- 结构：C 核心（锁定上游 tag）→ Swift Package（iOS/macOS）/ C++ SDK（Windows）+ 演示 App；
- 优点：一套底座全平台、GGUF 生态、MIT、社区最大、后续 Android 无缝；
- 代价：C/C++ 层维护与上游跟进；iOS 上走 Metal GPU（ANE 对第三方框架不可用，Apple 自家模型才上 ANE）；
- 性能预期：iPhone 16 Pro 级跑 1-3B Q4_K_M 约 10-15 tok/s（PocketPal 实测口径）；笔记本 M 系/独显可 20+ tok/s。

### 路线 B：MLC LLM 编译式
- 优点：iOS 速度最快、统一 MLCEngine API 优雅；
- 代价：模型须逐平台预编译（q4f16），自换模型/微调模型工作量大；社区规模小于 llama.cpp；「引擎」自主性弱（核心是 TVM）。

### 路线 C：平台原生混合
- iOS 用 Apple Foundation Models / Core ML，桌面用 Ollama 封装；
- 最省力，但「自研引擎」叙事不成立，双端行为不一致，不做主力推荐。

## 七、分层分析：「改进推理引擎」对非 C 开发者意味着什么（2026-10-23 追加）

用户约束：不会 C 语言、不熟底层，从零造引擎不现实；观察到 vLLM/Ollama 重硬件、少有人做手机端引擎，希望「在现有引擎上做面向手机的改进」。

### 引擎的三层结构（洋葱模型）

| 层 | 内容 | 语言 | 非 C 开发者可达性 |
|---|---|---|---|
| Kernel 层 | GEMM/注意力/量化反量化 kernel、Metal shader | C/C++/MSL/汇编 | ❌ 不可达（也不需要——llama.cpp 1400+ 贡献者在维护） |
| Runtime 层 | 图调度、KV cache、内存映射、采样器 | C++（llama_ 系列 API） | ⚠️ 经绑定可「调用与编排」，不可改核心 |
| Orchestration 层 | 模型生命周期、内存预算、量化档位选择、调度、工具循环、多 agent 编排、热控、系统生命周期适配 | Swift / Python / Kotlin | ✅ 完全可达，**「改进」的真正主战场** |

### 手机端真实痛点（桌面引擎从不处理的，全是机会）

1. **内存墙**：iOS 无 swap，jetsam 直接杀进程；实测 12GB 设备单进程仍约 6GB 硬顶（Apple 开发者论坛 2026-06，Gemma 4 在 mlx-swift-lm 实测 4.4GB 常驻即逼近极限）；6GB 设备阈值约 3GB。桌面引擎的「有多少吃多少」策略在手机上必死——需要内存预算感知的加载/卸载/档位选择；
2. **热墙**：持续生成 10-15 分钟触发降频，tok/s 掉 30-50%（约 38°C 阈值），功耗 3-5W、每小时 20-30% 电量——需要热感知调度（模型轮换、任务拆分、上下文压缩）；
3. **生命周期**：iOS 后台长任务受限、无 JIT、无未签名动态代码——需要 checkpoint/断点续推机制；
4. **分发**：App Store 下载上限 4GB、模型不宜进 bundle——需要按需下载 + 多量化档位分发；
5. **ANE 封闭**：第三方推理只能 Metal GPU（Apple 自家模型独占 ANE），功耗/速度天花板低于系统模型。

### 三条可行路线

**A. llama.cpp 钉版本 + 自研 Swift 运行时层（推荐）**
- llama.cpp 当黑盒算力核心，Swift 层做全部手机端改进（上述 1-4 全在 Swift 可写范围）；
- 现状验证：Swift 封装层已有先例但都薄——LLM.swift（2024，简单回调抽象）、官方 llama.swiftui 示例、llama-kit 类库，**没人做「跑得好」的移动运行时**，空位成立；
- 优点：GGUF 生态、MIT、跨平台（后续 Android 走同核心的 Kotlin 层）。

**B. MLX Swift 原生栈**
- Apple 官方支持（WWDC25 有 MLX Swift 专题），mlx-swift-lm 已有人在 iPhone 上跑通 Gemma 4 多模态；
- 全 Swift 栈对非 C 开发者友好（模型定义都是 Swift）；
- 缺点：iOS 生态仍新、模型转换社区弱（mlx-community 供给远小于 GGUF）、要动 kernel 时还是 C++；锁 Apple 生态。

**C. Core AI / Core ML 系统路径**
- Apple 2026-06 开源 coreai-models（「on-device AI 的模型导出配方 + Swift 运行时工具」），WWDC26 推「用 Core AI 部署自定义端侧模型」——官方路线、ANE 可达；
- 缺点：模型转换受约束、彻底锁死苹果生态，与跨平台愿景冲突。可作 iOS 侧增强（ANE 加速档），不作主路线。

### 结论

「改进推理引擎」的正确打开方式 = **移动优先推理运行时（mobile-first inference runtime）**。kernel 不是我们的战场；桌面引擎忽视的手机约束（内存墙/热墙/生命周期/分发）才是。这个层纯 Swift 可写、不碰 C，且与「本地多 agent 协作平台」定位天然兼容：agent 运行时坐在推理运行时之上。

## 八、风险清单

1. **Apple 平台挤压**：iOS 26+ 免费端侧 AFM + iPhone 18 内置大模型，通用聊天场景没有第三方引擎的生存空间——产品定位必须避开；
2. **上游安全**：llama.cpp GGUF 解析器 CVE 历史——锁定版本 + 安全更新机制；
3. **ANE 不可用**：第三方推理在 iOS 只能 Metal GPU，功耗/速度天花板低于系统模型（Apple 自家用 ANE）；
4. **算力缺口**：模型量化评测需要 GPU——训练机自 2026-10-01 收官休息（仅常驻服务），新任务要算力需先确认；
5. **双端维护成本**：iOS + Windows/Mac 两套构建链，一个人维护有压力——建议首个里程碑只做 iOS + Mac（技术栈同源 Metal，工作量砍半）。

## 九、待用户拍板（下一步）

1. 路线确认：A（llama.cpp 底座，推荐）/ B（MLC）/ C（平台原生）；
2. 产品形态：开源 SDK + demo App / 闭源商用 SDK / 先纯 demo 验证；
3. 首发平台组合：iOS+Mac 同源组合（推荐）还是 iOS+Windows；
4. 首发模型侧重：中文优先（Qwen）/ 全球通用（Gemma 4 E2B + SmolLM3）/ 不绑定全都要；
5. 项目归属与算力：是否需要训练机 GPU 资源（量化/评测）。

## 十、训练算力核算（2026-10-23 追加，按真实硬件）

用户训练机实测配置：**2× RTX 5090 32GB + Threadripper 7980X（64C/128T）+ 128GB RAM + 2TB 盘**。

- 理论算力：5090 单卡 FP16/BF16 张量密集 ≈ 419 TFLOPS，双卡 ≈ 838 TFLOPS；小模型续训按 MFU 25-35% 折算，有效算力 ≈ 210-290 TFLOPS；
- 显存账（全参训练 = BF16 权重 2B + 梯度 2B + Adam 状态 12B = 16 bytes/param）：1.7B ≈ 27GB，64GB 显存内无压力；4B ≈ 64GB，恰好压线，需 ZeRO-3 分片 + 优化器状态 offload 到 128GB RAM（CPU 有 64 核，offload 兜底成立）；
- 7980X + 128GB RAM 的定位：数据合成/预处理主力 + 优化器 offload 兜底；2TB 盘充足（5B tokens 文本 ≈ 20-40GB，1.7B/4B checkpoint 各约 10/25GB）。

| 方案 | 成本 C≈6ND | 预计时长 | 显存可行性 |
|---|---|---|---|
| Qwen3-1.7B 全参续训 5B tokens | 5.1e19 FLOPs | ≈ 2.5 天 | 无压力 |
| Qwen3-1.7B 全参续训 10B tokens | 1.0e20 | ≈ 5 天 | 无压力 |
| Qwen3-4B 全参续训 5B tokens | 1.2e20 | ≈ 5-6 天 | ZeRO-3 + CPU offload |
| Qwen3-4B 全参续训 10B tokens | 2.4e20 | ≈ 2 周 | 同上 |
| Qwen3-4B LoRA/QLoRA SFT（0.5-1B tokens） | — | 数小时-1 天 | 轻松 |

结论修正：真实硬件把训练档位从「1.7B 稳妥」拉到「**4B 是新的甜点**」。建议两级走：先 1.7B 全参续训跑通「数据→训练→量化→端侧」全管线（2-3 天，管管线验证），再训 4B 生产 agent 模型（1-2 周）。Mac 端不训练，直接量化现成 Qwen3-8B/14B GGUF。可选加速：Blackwell FP8（理论再翻倍），训练框架支持成熟再试，默认 BF16 求稳。

前提待确认：训练机 GPU 自 2026-10-01 收官（仅常驻服务：huihui 27B 占 GPU0 :8002、mikudev 30B 占 GPU1 :8003 经 LiteLLM :4000）——若 5090 双卡就是这两个服务的宿主，训练需确认共存方式（夜间窗口？暂停服务？），或另有算力。另：常驻双千问可兼职数据合成 teacher（合成 agent 轨迹数据），一举两得。

## 十一、竞品源码实现拆解（2026-10-23 追加，agent 抓 GitHub 源码核实）

| 维度 | PocketPal AI | MLC Chat |
|---|---|---|
| UI 栈 | React Native + TypeScript + MobX | 纯 SwiftUI |
| 引擎接入 | llama.cpp 经 **llama.rn**（MIT npm 包）JSI/TurboModule 桥；`patches/llama.rn+0.13.0-rc.7.patch` 自维护补丁（ContextManager 防悬垂） | MLCEngine（TVM 编译产物 + Swift 封装，`ios/MLCChat/States/ChatState.swift`） |
| 流式路径 | `LlamaContext.completion(params, callback)` 逐 token JSI 回调 | `engine.chat.completions.create()` 返回 AsyncStream，UI `for await` 消费 |
| 模型分发 | HF API 拉清单 → `hf.co/<repo>/resolve/main/<file>` 直下 → 存 `Documents/models/`；设备推荐矩阵在独立仓库 pocketpal-device-rules（CDN 下发） | 打包配置 `mlc-package-config.json` 驱动，模型存 app cache；可选 bundle 进 App |
| 参数面 | n_ctx、n_gpu_layers（默认 99）、use_mmap（smart）、use_mlock、flash_attn、投机解码；按机型给 ngl/flash 推荐矩阵 | 无显式 ngl（TVM 内部决策）；context 经打包期 overrides（默认 2048） |
| 内存守卫 | 读 GGUF metadata 对部分量化自动 mmap=false | 加载前 `os_proc_available_memory()` vs 预估 VRAM，不够拒绝加载 |
| 版本钉法 | llama.rn vendor llama.cpp，`vendor/VERSIONS` 钉 commit bf9a0cc（≈b11385，2026-10-04），落后上游约 2-3 周 | 随 mlc-llm monorepo 版本走 |
| 许可 | **MIT** | Apache 2.0 |

**对我们自研 SDK 的启示**：
1. 流式 API 形状统一成 OpenAI 风格（completion + token/工具调用回调），MLC 的 AsyncStream 是 Swift SDK 首选范式——与我们接口契约 v0.1 的 AsyncThrowingStream 一致；
2. 参数面照抄思路：n_ctx / ngl / mmap / mlock / flash-attn 按机型矩阵化、数据驱动（PocketPal 的 device-rules 模式），不硬编码；
3. 内存守卫：加载前用 `os_proc_available_memory()` 对照模型预估占用，体面拒绝比 OOM 崩溃好；
4. llama.rn（MIT）只作桥接思路参考，不引入（RN 专用）；我们走 llama.cpp 官方 Swift Package 直连；
5. 许可教训：PocketPal 实为 MIT 而非早期调研所记 AGPL——「原生 Swift SDK 空白」结论不变，但理由从「许可传染」修正为「桥的形态差」（RN 专用桥 Swift 用不了）。

## 附：信息来源（官方优先）

- llama.cpp 官方仓库：https://github.com/ggml-org/llama.cpp
- MLC LLM 官方仓库/文档：https://github.com/mlc-ai/mlc-llm 、https://llm.mlc.ai/docs/
- MediaPipe LLM Inference 官方文档：https://developers.google.com/edge/mediapipe/solutions/genai/llm_inference
- Apple Foundation Models：https://developer.apple.com/cn/apple-intelligence/ 、https://www.apple.com/sg/newsroom/2025/09/apples-foundation-models-framework-unlocks-new-intelligent-app-experiences/
- Qwen3 官方博客：https://qwenlm.github.io/blog/qwen3/
- Gemma 4 发布（2026-04，Apache 2.0）：https://www.huxiu.com/ainews/12884.html 、https://post.m.smzdm.com/p/ad7x7zpz/
- Gemma 3n 与模型卡：Hugging Face / Google AI Edge 文档
- SmolLM3：Hugging Face 官方博客与《Smol 训练手册》
- iOS 竞品实测：https://www.promptquorum.com/zh/power-local-llm/best-local-llm-apps-iphone-2026
- 本地 LLM 软件目录（160+ 工具）：https://www.promptquorum.com/power-local-llm/local-llm-software-directory-2026
- llama.cpp CVE 报道：https://m.freebuf.com/news/496360.html
