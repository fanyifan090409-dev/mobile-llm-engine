import SwiftUI
import UniformTypeIdentifiers
import UIKit

// ==================== 模型库（导入 / 删除 / 切换） ====================

struct ModelLibraryView: View {
    @Bindable var model: DemoModel
    @Environment(\.openURL) private var openURL
    @State private var importing = false
    @State private var switchingFile: String?
    @State private var busyImport: String?
    @State private var errorText: String?
    @State private var showImportNotice = false
    @AppStorage("ggufImportNoticeAccepted") private var importNoticeAccepted = false

    private let accent = Color(red: 0.04, green: 0.52, blue: 1.0)
    private let repoURL = URL(string: "https://github.com/fanyifan090409-dev/mobile-llm-engine")!

    private var ggufType: UTType { UTType(filenameExtension: "gguf") ?? .data }
    private var installed: [DemoModel.InstalledModel] { model.installedModels() }
    private var totalGB: Double { installed.reduce(0) { $0 + $1.sizeMB } / 1000 }
    private var freeGB: Double? {
        guard let values = try? URL(fileURLWithPath: NSHomeDirectory())
            .resourceValues(forKeys: [.volumeAvailableCapacityForImportantUsageKey]),
            let bytes = values.volumeAvailableCapacityForImportantUsage else { return nil }
        return Double(bytes) / 1_000_000_000
    }

    var body: some View {
        List {
            Section {
                ForEach(installed) { item in
                    row(item)
                }
            } header: {
                Text("已安装")
            } footer: {
                Text(storageFooter)
            }

            Section {
                Button {
                    if importNoticeAccepted {
                        importing = true
                    } else {
                        showImportNotice = true
                    }
                } label: {
                    Label("从文件导入 GGUF…", systemImage: "square.and.arrow.down")
                }
                .disabled(model.running || busyImport != nil)
            } footer: {
                Text("支持任意 GGUF 文件，导入后可直接切换。大文件（约 1–2 GB）需要几秒，导入期间请保持 App 在前台。\n\n本 App 仅提供本地推理环境，不提供模型下载、上传或分发服务。导入的 GGUF 由你自行获取，请确认拥有相应许可；模型文件只保存在本机。")
            }

            Section {
                Button {
                    openURL(repoURL)
                } label: {
                    HStack {
                        Label("查看模型兼容说明（GitHub）", systemImage: "arrow.up.right")
                        Spacer()
                        Image(systemName: "arrow.up.right")
                            .font(.caption)
                            .foregroundStyle(.tertiary)
                    }
                }
            } header: {
                Text("模型说明")
            } footer: {
                Text("App 内不下载模型。兼容的 1.7B / 0.6B 量化档说明见项目主页；模型需你自行从外部获取并遵守其许可。")
            }
        }
        .navigationTitle("模型库")
        .navigationBarTitleDisplayMode(.inline)
        .fileImporter(isPresented: $importing, allowedContentTypes: [ggufType],
                      allowsMultipleSelection: true) { result in
            handleImport(result)
        }
        .overlay {
            if let busyImport {
                importOverlay(busyImport)
            }
        }
        .alert("操作失败", isPresented: Binding(
            get: { errorText != nil },
            set: { if !$0 { errorText = nil } })) {
            Button("好", role: .cancel) { errorText = nil }
        } message: {
            Text(errorText ?? "")
        }
        .confirmationDialog("导入前请确认", isPresented: $showImportNotice,
                            titleVisibility: .visible) {
            Button("我已了解，继续导入") {
                importNoticeAccepted = true
                importing = true
            }
            Button("取消", role: .cancel) {}
        } message: {
            Text("App 仅提供本地推理环境，不提供模型下载、上传或分发服务。请确认你拥有所导入 GGUF 的使用许可；文件只保存在本机。")
        }
    }

    // MARK: 行

    private func row(_ item: DemoModel.InstalledModel) -> some View {
        Button {
            switchTo(item)
        } label: {
            HStack(spacing: 12) {
                VStack(alignment: .leading, spacing: 4) {
                    HStack(spacing: 6) {
                        Text(item.option.title)
                            .font(.body.weight(.medium))
                            .foregroundStyle(.primary)
                        if item.isBundled { badge("内置") }
                        if !item.isCataloged { badge("导入") }
                    }
                    Text("\(sizeText(item.sizeMB)) · \(item.option.speed)")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    Text("权重 \(String(format: "%.2f", item.option.weightGB)) GB · 峰值约 \(String(format: "%.1f", peakGB(item.option))) GB（\(model.contextTokens / 1024)K）")
                        .font(.caption2.monospacedDigit())
                        .foregroundStyle(.tertiary)
                }
                Spacer()
                if item.isCurrent {
                    Image(systemName: "checkmark.circle.fill")
                        .foregroundStyle(accent)
                } else if switchingFile == item.option.file {
                    ProgressView()
                }
            }
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .disabled(model.running || switchingFile != nil)
        .swipeActions(edge: .trailing, allowsFullSwipe: false) {
            if !item.isBundled && !item.isCurrent {
                Button(role: .destructive) {
                    delete(item)
                } label: {
                    Label("删除", systemImage: "trash")
                }
            }
        }
    }

    private func badge(_ text: String) -> some View {
        Text(text)
            .font(.caption2.weight(.medium))
            .foregroundStyle(.secondary)
            .padding(.horizontal, 6)
            .padding(.vertical, 2)
            .background(.quaternary, in: Capsule())
    }

    // 峰值 ≈ 权重 + KV（112 KB/token）+ Metal/运行时缓冲约 0.2 GB
    private func peakGB(_ opt: DemoModel.ModelOption) -> Double {
        opt.weightGB + Double(model.contextTokens) / 1024.0 * 0.11 + 0.2
    }

    private func sizeText(_ mb: Double) -> String {
        mb >= 1000 ? String(format: "%.2f GB", mb / 1000) : String(format: "%.0f MB", mb)
    }

    private var storageFooter: String {
        let free = freeGB.map { String(format: " · 可用 %.1f GB", $0) } ?? ""
        return "共 \(installed.count) 个模型，占用 \(String(format: "%.2f", totalGB)) GB\(free)。模型只保存在本机，不会上传。"
    }

    // MARK: 操作

    private func switchTo(_ item: DemoModel.InstalledModel) {
        guard !item.isCurrent, switchingFile == nil else { return }
        switchingFile = item.option.file
        Task {
            await model.useModel(item)
            switchingFile = nil
        }
    }

    private func delete(_ item: DemoModel.InstalledModel) {
        do {
            try model.deleteModel(item)
        } catch {
            errorText = error.localizedDescription
        }
    }

    private func handleImport(_ result: Result<[URL], Error>) {
        switch result {
        case .failure(let error):
            errorText = error.localizedDescription
        case .success(let urls):
            guard !urls.isEmpty else { return }
            Task { await importFiles(urls) }
        }
    }

    private func importFiles(_ urls: [URL]) async {
        for url in urls {
            busyImport = url.lastPathComponent
            do {
                try await model.importModel(from: url)
            } catch {
                busyImport = nil
                errorText = error.localizedDescription
                return
            }
        }
        busyImport = nil
    }

    private func importOverlay(_ name: String) -> some View {
        ZStack {
            Color.black.opacity(0.18).ignoresSafeArea()
            VStack(spacing: 12) {
                ProgressView()
                    .controlSize(.large)
                Text("正在导入…")
                    .font(.headline)
                Text(name)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(2)
                    .multilineTextAlignment(.center)
                Text("大文件约需几秒，请保持 App 在前台")
                    .font(.caption2)
                    .foregroundStyle(.tertiary)
            }
            .padding(24)
            .frame(maxWidth: 300)
            .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 20, style: .continuous))
            .shadow(color: .black.opacity(0.12), radius: 20, y: 8)
        }
    }
}

// ==================== 关于与隐私 ====================

struct AboutView: View {
    @Bindable var model: DemoModel
    @Environment(\.openURL) private var openURL

    private let repoURL = URL(string: "https://github.com/fanyifan090409-dev/mobile-llm-engine")!
    private let accent = Color(red: 0.04, green: 0.52, blue: 1.0)

    private var version: String {
        let short = Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "1.0"
        let build = Bundle.main.infoDictionary?["CFBundleVersion"] as? String ?? "1"
        return "\(short)（\(build)）"
    }

    private var appName: String {
        Bundle.main.infoDictionary?["CFBundleDisplayName"] as? String ?? "EngineShell"
    }

    var body: some View {
        List {
            Section {
                VStack(spacing: 10) {
                    Image(systemName: "cpu")
                        .font(.system(size: 30, weight: .semibold))
                        .foregroundStyle(.white)
                        .frame(width: 64, height: 64)
                        .background(
                            LinearGradient(colors: [accent, Color(red: 0.25, green: 0.75, blue: 0.95)],
                                           startPoint: .topLeading, endPoint: .bottomTrailing),
                            in: RoundedRectangle(cornerRadius: 16, style: .continuous))
                    Text(appName)
                        .font(.headline)
                    Text("本地 Agent 实验室 · 离线运行")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                .frame(maxWidth: .infinity)
                .padding(.vertical, 8)
                .listRowBackground(Color.clear)
            }

            Section("当前运行") {
                LabeledContent("模型", value: model.modelShortLabel)
                LabeledContent("上下文", value: "\(model.contextTokens / 1024)K")
                LabeledContent("速度档位", value: DemoModel.speedTitle(model.speedTier))
                LabeledContent("设备分", value: model.lastScore > 0
                               ? "\(model.lastScore) · \(BenchmarkTier.of(model.lastScore).rawValue)"
                               : "未跑分")
            }

            Section("路线") {
                Label("当前：单 Agent + 工具调用闭环（日历 / 提醒 / 翻译 / 问答 / 总结）。", systemImage: "checkmark.circle")
                Label("下一步：本地 DIY 多 Agent 编排（规划，未上线）——自己拆任务、配角色、看内存代价。", systemImage: "square.stack.3d.up")
            }
            .font(.footnote)

            Section("应用信息") {
                LabeledContent("版本", value: version)
                LabeledContent("系统", value: "iOS \(UIDevice.current.systemVersion)")
                LabeledContent("推理引擎", value: "llama.cpp（钉版本）")
            }

            Section("隐私") {
                Label("所有推理都在本机完成，对话内容不上传到任何服务器。", systemImage: "lock.shield")
                Label("应用不含统计、广告或崩溃上报 SDK，不收集使用数据。", systemImage: "hand.raised")
                Label("对话、跑分和设置只保存在本机；删除 App 即全部清除。", systemImage: "iphone")
                Label("App 仅提供本地推理环境，不提供模型下载、上传或分发服务；内置演示模型仅用于功能验证，第三方 GGUF 由你自行获取并遵守其许可。", systemImage: "shippingbox")
            }
            .font(.footnote)

            Section {
                Button {
                    openURL(repoURL)
                } label: {
                    HStack {
                        Label("项目主页（GitHub）", systemImage: "link")
                        Spacer()
                        Image(systemName: "arrow.up.right")
                            .font(.caption)
                            .foregroundStyle(.tertiary)
                    }
                }
            } header: {
                Text("开源与致谢")
            } footer: {
                Text("推理内核 llama.cpp（MIT License）。模型基于 Qwen3 继续训练（Apache 2.0）。App 仅提供本地推理环境，不提供模型下载或分发服务；第三方 GGUF 的许可由获取者自行确认。")
            }
        }
        .navigationTitle("关于与隐私")
        .navigationBarTitleDisplayMode(.inline)
    }
}
