import SwiftUI
import EngineKit
import Darwin

// ==================== 首启跑分 ====================

struct BenchmarkResult {
    let score: Int
    let speedScore: Int
    let stabilityScore: Int
    let memoryScore: Int
    let stableTps: Double
    let peakMB: Int
    let availableGB: Double
    let rounds: [Double]
    let modelLabel: String
}

struct BenchmarkRecommendation {
    let modelFile: String?
    let title: String
    let reason: String
    let cost: String
    let contextTokens: Int
    let speed: SpeedTier
}

// 设备分四档：80–100 强 / 60–79 稳 / 40–59 够用 / 0–39 轻量。
// 分档只决定推荐配置，不改变跑分算法本身（算法见下方 DeviceBenchmark 注释）。
enum BenchmarkTier: String {
    case strong = "强"
    case steady = "稳"
    case enough = "够用"
    case light = "轻量"

    static func of(_ score: Int) -> BenchmarkTier {
        switch score {
        case 80...: return .strong
        case 60..<80: return .steady
        case 40..<60: return .enough
        default: return .light
        }
    }

    var rangeText: String {
        switch self {
        case .strong: return "80–100"
        case .steady: return "60–79"
        case .enough: return "40–59"
        case .light: return "0–39"
        }
    }

    var title: String { "\(rawValue) · \(rangeText)" }
}

// 评分沿用 docs/plans/设备跑分与模型池推荐.md v0.1：
// 速度分 S = min(100, 稳定 tok/s × 2)，稳定分 T = 100 × 后半段 / 前半段，
// 内存分 M = min(100, 可用内存 GB × 10)，总分 = 0.6S + 0.25T + 0.15M。
// 负载固定 4 轮 300 字短文（输出必触 256 token 上限），取后 3 轮稳定值。
enum DeviceBenchmark {
    static let prompt = "写一篇300字左右的短文，介绍你理想中的一天，从早上起床写到晚上睡觉。"

    @MainActor
    static func measure(engine: EngineCore, modelLabel: String,
                        onRound: @escaping @MainActor (Int) -> Void) async -> BenchmarkResult {
        var tps: [Double] = []
        var peaks: [Int] = []
        for round in 1...4 {
            onRound(round)
            var decode: Double?
            var peak: Int?
            do {
                for try await event in engine.generate(GenerationRequest(
                    messages: [Message(role: "user", content: prompt)],
                    maxTokens: 256, temperature: 0.7, speed: .balanced, tools: nil)) {
                    if case .stats(let s) = event {
                        decode = s.tokensPerSecond
                        peak = s.peakMemoryMB
                    }
                }
            } catch {
                // 单轮失败不中断；全失败时结果为空，由 UI 提示重试
            }
            if let decode, decode > 0 { tps.append(decode) }
            if let peak { peaks.append(peak) }
        }

        let stable = tps.count >= 4 ? mean(Array(tps.suffix(3))) : mean(tps)
        let firstHalf = mean(Array(tps.prefix(2)))
        let secondHalf = mean(Array(tps.suffix(2)))
        let stability = firstHalf > 0 ? min(100, secondHalf / firstHalf * 100) : 0
        let speedScore = min(100, stable * 2)
        let availableGB = Double(os_proc_available_memory()) / 1_000_000_000
        let memoryScore = min(100, availableGB * 10)
        let total = 0.6 * speedScore + 0.25 * stability + 0.15 * memoryScore

        return BenchmarkResult(
            score: tps.isEmpty ? 0 : max(0, min(100, Int(total.rounded()))),
            speedScore: Int(speedScore.rounded()),
            stabilityScore: Int(stability.rounded()),
            memoryScore: Int(memoryScore.rounded()),
            stableTps: (stable * 10).rounded() / 10,
            peakMB: peaks.max() ?? 0,
            availableGB: (availableGB * 10).rounded() / 10,
            rounds: tps.map { ($0 * 10).rounded() / 10 },
            modelLabel: modelLabel)
    }

    private static func mean(_ xs: [Double]) -> Double {
        xs.isEmpty ? 0 : xs.reduce(0, +) / Double(xs.count)
    }
}

// ==================== 首启引导页 ====================

struct OnboardingView: View {
    @Bindable var model: DemoModel
    @Environment(\.colorScheme) private var scheme
    @State private var shownScore = 0
    @State private var applying = false

    var body: some View {
        ZStack {
            background
            ScrollView {
                VStack(spacing: 22) {
                    header
                    if let result = model.benchmark, !model.onboardingRunning {
                        resultView(result)
                    } else {
                        runningView
                    }
                }
                .padding(24)
                .frame(maxWidth: 560)
            }
            .scrollIndicators(.hidden)
        }
    }

    private var background: some View {
        LinearGradient(
            colors: scheme == .light
                ? [Color(red: 0.87, green: 0.91, blue: 0.98), Color(red: 0.97, green: 0.98, blue: 1.0)]
                : [Color(red: 0.04, green: 0.05, blue: 0.09), Color(red: 0.10, green: 0.12, blue: 0.18)],
            startPoint: .top, endPoint: .bottom)
        .ignoresSafeArea()
    }

    private var header: some View {
        HStack(alignment: .top) {
            VStack(alignment: .leading, spacing: 4) {
                Text("设备跑分")
                    .font(.title2.bold())
                Text("离线 · 数据不出设备 · 仅用于本机配置推荐")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            Spacer()
            if model.onboardingRunning {
                Button("跳过") { model.skipOnboarding() }
                    .font(.footnote)
                    .foregroundStyle(.secondary)
            }
        }
    }

    // MARK: 跑分进行中

    private var runningView: some View {
        VStack(spacing: 26) {
            ZStack {
                Circle()
                    .stroke(.primary.opacity(0.10), lineWidth: 14)
                Circle()
                    .trim(from: 0, to: CGFloat(model.onboardingProgress) / 4)
                    .stroke(AngularGradient(colors: [.blue, .cyan, .green, .blue], center: .center),
                            style: StrokeStyle(lineWidth: 14, lineCap: .round))
                    .rotationEffect(.degrees(-90))
                    .animation(.easeInOut(duration: 0.6), value: model.onboardingProgress)
                VStack(spacing: 2) {
                    Text("\(model.onboardingProgress)/4")
                        .font(.system(size: 46, weight: .bold, design: .rounded))
                        .contentTransition(.numericText())
                    Text("轮次")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
            .frame(width: 190, height: 190)

            Text("正在测试本机解码性能")
                .font(.headline)
            Text("\(model.modelShortLabel) · \(model.contextTokens / 1024)K · 标准短文负载\n约 20 秒，全程离线，不上传任何数据")
                .font(.footnote)
                .multilineTextAlignment(.center)
                .foregroundStyle(.secondary)
                .lineSpacing(3)
        }
        .padding(.top, 30)
    }

    // MARK: 跑分结果

    private func resultView(_ result: BenchmarkResult) -> some View {
        VStack(spacing: 22) {
            if result.rounds.isEmpty {
                Text("跑分失败")
                    .font(.title3.bold())
                Text("模型未能完成标准负载，请检查模型是否加载正常后重试。")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.center)
                Button("重新跑分") { model.startBenchmark() }
                    .buttonStyle(.borderedProminent)
            } else {
                scoreRing(result)
                Text(scoreTitle(result.score))
                    .font(.title3.weight(.semibold))
                Text("基于 \(result.modelLabel) · 稳定 \(String(format: "%.1f", result.stableTps)) tok/s · 峰值 \(result.peakMB) MB")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.center)
                subScores(result)
                if let rec = model.recommendation(for: result) {
                    recommendationCard(rec)
                    Button {
                        Task {
                            applying = true
                            await model.applyRecommendation(rec)
                            applying = false
                        }
                    } label: {
                        HStack(spacing: 8) {
                            if applying { ProgressView().tint(.white) }
                            Text(applying ? "正在应用…" : "使用推荐配置")
                                .font(.headline)
                        }
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 14)
                        .background(Color(red: 0.04, green: 0.52, blue: 1.0), in: RoundedRectangle(cornerRadius: 16, style: .continuous))
                        .foregroundStyle(.white)
                    }
                    .buttonStyle(.plain)
                    .disabled(applying || model.running)

                    Button("手动选择") {
                        model.showOnboarding = false
                        Task {
                            try? await Task.sleep(nanoseconds: 400_000_000)
                            model.showContextPicker = true
                        }
                    }
                    .font(.footnote)
                    .foregroundStyle(.secondary)
                }
            }
        }
        .task(id: result.score) {
            shownScore = 0
            guard result.score > 0 else { return }
            for i in 1...result.score {
                try? await Task.sleep(nanoseconds: 15_000_000)
                shownScore = i
            }
        }
    }

    private func scoreRing(_ result: BenchmarkResult) -> some View {
        ZStack {
            Circle()
                .stroke(.primary.opacity(0.10), lineWidth: 16)
            Circle()
                .trim(from: 0, to: CGFloat(shownScore) / 100)
                .stroke(ringGradient(result.score),
                        style: StrokeStyle(lineWidth: 16, lineCap: .round))
                .rotationEffect(.degrees(-90))
                .animation(.easeOut(duration: 0.2), value: shownScore)
            VStack(spacing: 0) {
                Text("\(shownScore)")
                    .font(.system(size: 68, weight: .bold, design: .rounded))
                    .contentTransition(.numericText())
                Text("设备分")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
        .frame(width: 220, height: 220)
        .padding(.top, 8)
    }

    private func subScores(_ result: BenchmarkResult) -> some View {
        VStack(spacing: 10) {
            subScore("速度", result.speedScore, .blue)
            subScore("稳定", result.stabilityScore, .green)
            subScore("内存", result.memoryScore, .orange)
        }
        .padding(16)
        .frame(maxWidth: .infinity)
        .glass()
    }

    private func subScore(_ title: String, _ value: Int, _ color: Color) -> some View {
        HStack(spacing: 10) {
            Text(title)
                .font(.caption)
                .foregroundStyle(.secondary)
                .frame(width: 34, alignment: .leading)
            ProgressView(value: Double(value), total: 100)
                .tint(color)
            Text("\(value)")
                .font(.caption.monospacedDigit())
                .foregroundStyle(.secondary)
                .frame(width: 30, alignment: .trailing)
        }
    }

    private func recommendationCard(_ rec: BenchmarkRecommendation) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text("推荐配置")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.secondary)
                Spacer()
                Image(systemName: "sparkles")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            Text(rec.title)
                .font(.headline)
            Text(rec.reason)
                .font(.footnote)
                .foregroundStyle(.secondary)
                .lineSpacing(2)
            Text(rec.cost)
                .font(.caption2.monospacedDigit())
                .foregroundStyle(.tertiary)
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .glass()
    }

    private func scoreTitle(_ score: Int) -> String {
        BenchmarkTier.of(score).title
    }

    private func ringGradient(_ score: Int) -> AngularGradient {
        let colors: [Color]
        switch BenchmarkTier.of(score) {
        case .strong: colors = [.green, .mint, .cyan, .green]
        case .steady: colors = [.blue, .cyan, .green, .blue]
        case .enough: colors = [.orange, .yellow, .green, .orange]
        case .light: colors = [.red, .orange, .yellow, .red]
        }
        return AngularGradient(colors: colors, center: .center)
    }
}
