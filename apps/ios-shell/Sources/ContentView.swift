import SwiftUI

// AIY 演示壳入口：方向一「苹果原味」UI（玻璃卡片 + 过程卡 + 真实工具调用），
// 设计契约见 docs/plans/AIY27-iOS演示壳.md
struct ContentView: View {
    var body: some View {
        if ProcessInfo.processInfo.arguments.contains(where: { $0.hasPrefix("-voicePOC") }) {
            VoicePOCView()
        } else {
            DemoChatView()
        }
    }
}
