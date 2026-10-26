import SwiftUI
import EngineKit

struct ContentView: View {
    @StateObject private var log = AppLog.shared
    @State private var engine = EngineCore()
    @State private var prompt = "你好，介绍一下你自己"
    @State private var output = ""
    @State private var loaded = false
    @State private var running = false

    var body: some View {
        VStack(spacing: 12) {
            HStack {
                Circle()
                    .fill(loaded ? Color.green : Color.orange)
                    .frame(width: 10, height: 10)
                Text(loaded ? "模型已加载" : "模型加载中…")
                    .font(.footnote)
                Spacer()
            }
            TextField("输入问题", text: $prompt, axis: .vertical)
                .textFieldStyle(.roundedBorder)
                .lineLimit(1...3)
                .disabled(!loaded)
            Button {
                Task { await run() }
            } label: {
                Text(running ? "生成中…" : "运行")
                    .frame(maxWidth: .infinity)
            }
            .buttonStyle(.borderedProminent)
            .disabled(!loaded || running)
            ScrollView {
                Text(output)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
            .frame(maxHeight: .infinity)
            .background(Color(.secondarySystemBackground))
            .clipShape(RoundedRectangle(cornerRadius: 8))
            ScrollView {
                Text(log.lines.joined(separator: "\n"))
                    .font(.footnote)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
            .frame(height: 140)
        }
        .padding()
        .task { await loadModel() }
    }

    // 模型定位：优先 Documents/Models（用户可换档），缺省用 bundle 内嵌（安装即用）
    private func findModel() -> URL? {
        let candidates = [
            FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0],
            Bundle.main.bundleURL,
        ]
        for base in candidates {
            let url = base.appendingPathComponent("Models/qwen3-0.6b-sft-Q5_K_M.gguf")
            if FileManager.default.fileExists(atPath: url.path) { return url }
        }
        return nil
    }

    private func loadModel() async {
        log.log("开始装载模型…")
        guard let url = findModel() else {
            log.log("未找到模型文件（Documents/Models 或 bundle 内嵌均无）")
            return
        }
        log.log("模型路径：\(url.path)")
        // thinkTags: true——SFT3B 训练模板含空思考块，训练/推理必须同开同关（demo-cli --think-tags 同源）
        let spec = ModelSpec(fileURL: url, quant: "Q5_K_M", context: 4096, thinkTags: true)
        do {
            try await engine.load(spec)
            loaded = true
            log.log("模型加载完成")
        } catch {
            log.log("模型加载失败：\(error)")
        }
    }

    private func run() async {
        guard loaded else { return }
        running = true
        output = ""
        log.log("开始生成：\(prompt)")
        do {
            for try await event in engine.generate(GenerationRequest(
                messages: [Message(role: "user", content: prompt)],
                maxTokens: 256, temperature: 0.7, speed: .balanced)) {
                switch event {
                case .token(let t):
                    output += t
                case .stats(let s):
                    log.log(String(format: "统计：解码 %.1f tok/s | 预填充 %.1f tok/s | 峰值内存 %d MB",
                                   s.tokensPerSecond, s.promptTokensPerSecond, s.peakMemoryMB))
                case .toolCall:
                    break   // 壳不注册工具，纯文本模式不会出现
                }
            }
            log.log("生成结束")
        } catch {
            log.log("生成出错：\(error)")
        }
        running = false
    }
}
