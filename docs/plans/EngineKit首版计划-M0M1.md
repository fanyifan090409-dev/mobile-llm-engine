# EngineKit 首版计划（M0+M1）· 接口契约 v0.1

> 状态：已拍板（2026-10-26 用户确认三决策点），M0 执行中。
> 范围：M0 地基 + M1 Mac 推理链路；M2 iOS 只定边界不做。训练线（0.6B 评测链）与本计划并行，互不阻塞。

## 1. 目标与边界

- **M0 地基**：git init、.gitignore、SPM 包骨架（可编译）、门禁脚本、llama.cpp 静态库构建。
- **M1 Mac 推理链路**：CLLaMA C 桥接层 + EngineKit 运行时子集（加载/流式生成/卸载）+ demo-cli + 双 Mac 基准表。
- **验收**（沿用落地计划）：
  - M0：`swift build && swift test` 全绿；
  - M1：Qwen3-1.7B Q4_K_M 官方 GGUF，M5 Air ≥ 15 tok/s；中文质量人工抽查 10 条。
- **不做**（后置 M2+）：iOS 打包/xcframework、BenchmarkKit（跑分）、热感知降档、投机采样、断点续推。
- **开发期替身**：M1 用官方 Qwen3 GGUF 做工程替身（发布模型必须自训三档，与落地计划一致）。

## 2. 目录结构（落地计划四节落地）

```
engine/                         # Swift Package「EngineKit」
├── Package.swift
├── Sources/
│   ├── CLLaMA/                 # llama.cpp C 绑定薄封装（不碰 kernel）
│   │   ├── include/            # 头文件（llama.h 等，随 tag 同步）
│   │   ├── lib/                # 静态库产物（libllama.a + libggml*.a，gitignore）
│   │   └── module.modulemap
│   └── EngineKit/              # 运行时：加载、流式生成、档位枚举（M3 前为子集）
│       ├── EngineCore.swift    # LocalEngine 协议实现
│       ├── ModelSpec.swift / GenerationRequest.swift / TokenEvent.swift / Message.swift
│       └── MemoryTier.swift / SpeedTier.swift
└── Tests/EngineKitTests/       # 冒烟单测（1 token 生成、卸载后内存回落）
apps/demo-cli/                  # Mac 基准 CLI：对话 + tok/s + 峰值 RSS
models/                         # GGUF 下载脚本 + 清单（模型文件 gitignore）
scripts/gate.sh                 # 门禁：swift build + swift test（+ lint 装好后接入）
```

## 3. 数据模型与接口契约（M1 子集）

对齐落地计划五节 v0.1 契约，M1 只实现其中可用的部分，**冻结枚举名与模型名**（M3 不再改名）：

```swift
// ---- 档位枚举（M1 定义，M3 用）----
public enum MemoryTier: CaseIterable { case low, standard, high }   // 0.6B / 1.7B / 4B 档
public enum SpeedTier: Int, CaseIterable { case powerSaver, balanced, performance, turbo }

// ---- 数据模型 ----
public struct ModelSpec {
    public let fileURL: URL          // GGUF
    public let quant: String         // "Q4_K_M" 等，展示用
    public let context: Int          // KV 上限，与内存预算联算
}

public struct Message: Codable { public let role: String; public let content: String }

public struct GenerationRequest {
    public let messages: [Message]
    public let maxTokens: Int
    public let temperature: Double
    public let speed: SpeedTier      // M1 映射到 ngl/线程数；四档全支持
}

public enum TokenEvent {             // 流式事件
    case token(String)               // 增量文本
    case stats(Stats)                // 收尾统计：tok/s、峰值 RSS、pp_ts
    public struct Stats { public let tokensPerSecond: Double; public let peakMemoryMB: Int; public let promptTokensPerSecond: Double }
}

// ---- 引擎协议（落地计划 v0.1 的 M1 子集；resolveTier 只做雏形，M3 完整）----
public protocol LocalEngine {
    func resolveTier(deviceMemory: Int) -> MemoryTier?   // 雏形：os_proc_available_memory 查表
    func load(_ spec: ModelSpec) async throws
    func generate(_ req: GenerationRequest) -> AsyncThrowingStream<TokenEvent, Error>
    func unload()
}
```

### 3.1 CLLaMA 桥接层草案（内部 API，不对外暴露语义）

```swift
// 薄封装 llama.h：对象 → 生命周期管理，指针不出层
internal final class ModelHandle      // llama_model_params + llama_load_model_from_file
internal final class ContextHandle    // llama_context（batch decode、KV 上限）
internal final class SamplerHandle    // llama_sampler 链（temp/top-p，chain 式）
internal func tokenize(_ ctx: ContextHandle, _ text: String) -> [llama_token]
internal func decode(_ ctx: ContextHandle, _ batch: [llama_token]) -> Bool
```

- 桥接层只做**所有权与错误转换**（C 指针 → Swift 类 + deinit 释放），推理循环在 EngineKit 层写。
- 线程模型 M1：Metal 后端，解码在独立队列（generation queue），流式输出经 AsyncThrowingStream 回主调用方。

## 4. llama.cpp 集成方案（已拍板：静态库 + module map）

- **推荐：本地静态库 + module map**。llama.cpp（已钉 b11857）补编静态版（`GGML_METAL=ON`、`BUILD_SHARED_LIBS=OFF`）→ 产 libllama.a + libggml*.a 放 `Sources/CLLaMA/lib/`，头文件拷 `include/`，SPM `systemLibrary` + `linkerSettings`（-lllama 等）接入。M1 一天内可通，路径全在包内、无全局依赖。
- **备选：一步到位 xcframework**（参照官方 llama.swiftui 的 build-xcframework 脚本）。iOS 必需形态，但打包链长，M2 再升级不迟。
- **回退：直接链现有 dylib**（tools/llama.cpp/build/bin 已有 libllama.dylib）——rpath 麻烦但可应急。

## 5. 步骤与验收（每步一个 commit，Conventional Commits）

| 步 | 内容 | 验收 |
|---|---|---|
| M0.1 | git init + .gitignore（GGUF/大文件/构建产物排除）+ commit | `git status` 干净 |
| M0.2 | SPM 骨架：engine/Package.swift + 空 Sources + 空测试 | `swift build && swift test` 全绿 |
| M0.3 | llama.cpp 静态库构建脚本（tools/llama.cpp 内跑，不动现有 build） | libllama.a 等产出、大小校验 |
| M0.4 | scripts/gate.sh（build+test，lint 后接入） | 门禁全绿 |
| M1.1 | CLLaMA 桥接层 + 冒烟单测（加载 0.6B Q5_K_M、生成 1 token、unload） | 单测绿 |
| M1.2 | EngineKit：EngineCore 流式生成（chat 模板、采样链、tok/s 统计） | demo-cli 可对话 |
| M1.3 | demo-cli：参数解析、流式打印、峰值 RSS（/usr/bin/time -l 语义同训练侧） | 与 llama-cli 输出可比 |
| M1.4 | models/ 下载脚本（Qwen3-1.7B Q4_K_M 官方 GGUF，断点续传） | 下载可复跑 |
| M1.5 | 双 Mac 基准表（M5 Air/M5 Pro：tok/s、pp_ts、峰值 RSS）+ 中文 10 条抽查 | **1.7B Q4 M5 Air ≥ 15 tok/s** |

## 6. 回滚点

- git 每个可验证增量一个 commit；**M0.2 空包骨架先行 commit**，C 库集成失败（M1.1）可干净回退到骨架。
- 静态库构建失败 → 回退 dylib 链接方案（第 4 节回退项），不动上游 llama.cpp tag。
- 本计划零外部服务、零训练机操作，无部署回滚风险。

## 7. 风险与依赖

1. **Xcode 未装（实测确认）**：本机仅 CommandLineTools，`xcodebuild` 不可用。M1（macOS SPM）不受影响；**M2 iOS 前必须装完整 Xcode（用户侧待办）**。
2. **llama.h 契约以 b11857 仓库头文件为准**，不照抄网络教程旧版 API（踩坑积累教训：对安装版本核契约）。
3. **Metal 后端 ngl 调优**是 15 tok/s 验收关键：1.7B Q4 全部层上 GPU（ngl=99）预期远超 15，但需实测避免 Metal 上传开销反超。
4. SPM systemLibrary + 静态库链接细节（header 路径、C++ 运行时链接）预算半天踩坑。
5. Swift 6.3.3 编译器可用；**语言模式建议 Swift 5（待拍板 ②）**——C 指针互操作在 strict concurrency 下报错面大，M1 求快不求新。

## 8. 已拍板（2026-10-26 用户确认）

1. **集成方式**：静态库 + module map（M1 够用且快，M2 上 iOS 时升级 xcframework）。
2. **语言模式**：Swift 5 模式起步（编译器 6.3.3，tools-version 5.9；M3 再评估升 6）。
3. **Xcode**：M1 期间用户抽空装完整 Xcode，M2 开工前就绪。
