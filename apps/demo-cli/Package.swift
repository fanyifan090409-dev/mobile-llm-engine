// swift-tools-version:5.9
import PackageDescription

let package = Package(
    name: "demo-cli",
    platforms: [.macOS(.v14)],
    dependencies: [
        .package(path: "../../engine")
    ],
    targets: [
        .executableTarget(
            name: "demo-cli",
            dependencies: [
                .product(name: "EngineKit", package: "engine")
            ]
        )
    ]
)
