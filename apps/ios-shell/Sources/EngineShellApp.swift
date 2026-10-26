import SwiftUI

// 测试壳入口：真机验证 EngineKit 的最小壳（加载→推理→日志落盘），跑通后升级为跑分壳
@main
struct EngineShellApp: App {
    var body: some Scene {
        WindowGroup {
            ContentView()
        }
    }
}
