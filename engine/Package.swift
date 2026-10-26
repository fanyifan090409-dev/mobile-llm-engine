// swift-tools-version:5.9
import PackageDescription
import Foundation

// 静态库目录：从 Package.swift 自身位置推导绝对路径，避免相对 -L 依赖构建时 cwd（scratch-path 下依然稳定）
let cllamaLibDir = URL(fileURLWithPath: #filePath)
    .deletingLastPathComponent()
    .appendingPathComponent("Sources/CLLaMA/lib")
    .path

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
            .unsafeFlags(["-L\(cllamaLibDir)"]),
            // 链接顺序：llama → ggml → 各后端（静态库符号从左到右解析）
            .linkedLibrary("llama"),
            .linkedLibrary("ggml"),
            .linkedLibrary("ggml-base"),
            .linkedLibrary("ggml-cpu"),
            .linkedLibrary("ggml-blas"),
            .linkedLibrary("ggml-metal"),
            // llama.cpp 是 C++ 实现；Metal/BLAS 后端依赖系统框架
            .linkedLibrary("c++"),
            .linkedFramework("Metal"),
            .linkedFramework("Accelerate"),
            .linkedFramework("Foundation"),
        ]
    ),
    .testTarget(
        name: "EngineKitTests",
        dependencies: ["EngineKit", "CLLaMA"]
    ),
]

let package = Package(
    name: "EngineKit",
    platforms: [.macOS(.v14), .iOS(.v16)],
    products: [
        .library(name: "EngineKit", targets: ["EngineKit"])
    ],
    targets: targets
)
