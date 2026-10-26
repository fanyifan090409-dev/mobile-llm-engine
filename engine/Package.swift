// swift-tools-version:5.9
import PackageDescription
import Foundation

// 静态库目录：从 Package.swift 自身位置推导绝对路径，避免相对 -L 依赖构建时 cwd（scratch-path 下依然稳定）
// Mac 与 iOS 的 .a 同名但产物不同（Metal 后端 embedded metallib 等），分目录存放、按平台条件选 -L
let cllamaLibRoot = URL(fileURLWithPath: #filePath)
    .deletingLastPathComponent()
    .appendingPathComponent("Sources/CLLaMA/lib")
let cllamaMacLibDir = cllamaLibRoot.appendingPathComponent("macos").path
let cllamaIosLibDir = cllamaLibRoot.appendingPathComponent("ios").path

let targets: [Target] = [
    .systemLibrary(
        name: "CLLaMA",
        path: "Sources/CLLaMA"
    ),
    // 链接配置放在 EngineKit 上：tools 5.9 的 systemLibrary 不接受 linkerSettings，
    // 而普通 target 的 linkerSettings 会在最终链接产物时生效
    .target(
        name: "EngineKit",
        dependencies: ["CLLaMA"],
        linkerSettings: [
            .unsafeFlags(["-L\(cllamaMacLibDir)"], .when(platforms: [.macOS])),
            .unsafeFlags(["-L\(cllamaIosLibDir)"], .when(platforms: [.iOS])),
            // 链接顺序：llama → ggml → 各后端（静态库符号从左到右解析）
            .linkedLibrary("llama", .when(platforms: [.macOS, .iOS])),
            .linkedLibrary("ggml", .when(platforms: [.macOS, .iOS])),
            .linkedLibrary("ggml-base", .when(platforms: [.macOS, .iOS])),
            .linkedLibrary("ggml-cpu", .when(platforms: [.macOS, .iOS])),
            .linkedLibrary("ggml-blas", .when(platforms: [.macOS, .iOS])),
            .linkedLibrary("ggml-metal", .when(platforms: [.macOS, .iOS])),
            // llama.cpp 是 C++ 实现；Metal/BLAS 后端依赖系统框架
            .linkedLibrary("c++", .when(platforms: [.macOS, .iOS])),
            .linkedFramework("Metal", .when(platforms: [.macOS, .iOS])),
            .linkedFramework("Accelerate", .when(platforms: [.macOS, .iOS])),
            .linkedFramework("Foundation", .when(platforms: [.macOS, .iOS])),
        ]
    ),
    .testTarget(
        name: "EngineKitTests",
        dependencies: ["EngineKit", "CLLaMA"]
    ),
]

let package = Package(
    name: "EngineKit",
    // iOS 下限 17：官方脚本产出的 .a 按 iOS 16.4 编译（链接告警实测），且测试机均为 iOS 18+
    platforms: [.macOS(.v14), .iOS(.v17)],
    products: [
        .library(name: "EngineKit", targets: ["EngineKit"])
    ],
    targets: targets
)
