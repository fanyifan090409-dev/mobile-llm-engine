import AVFoundation
import Darwin
import SherpaOnnx
import SwiftUI

// P0 隔离验证页：不进入正式聊天链路，只用官方 sherpa-onnx 包验证 TTS/ASR
@MainActor
final class VoicePOCModel: ObservableObject {
    @Published var ttsStatus = "未检测"
    @Published var asrStatus = "未检测"
    @Published var ttsInfo = ""
    @Published var transcript = ""
    @Published var isRecording = false
    @Published var isSpeaking = false

    private let docs = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
    private var voiceRoot: URL { docs }
    private var ttsDir: URL { voiceRoot.appendingPathComponent("kokoro-int8-multi-lang-v1_1") }
    private var asrDir: URL { voiceRoot.appendingPathComponent("sherpa-onnx-streaming-zipformer-zh-14M-2023-02-23") }

    private var tts: SherpaOnnxOfflineTtsWrapper?
    private var recognizer: SherpaOnnxRecognizer?
    private var audioEngine: AVAudioEngine?
    private var playerEngine: AVAudioEngine?
    private var playerNode: AVAudioPlayerNode?

    init() {
        ttsStatus = exists(ttsDir.appendingPathComponent("model.int8.onnx")) ? "模型已就位" : "缺模型"
        asrStatus = exists(asrDir.appendingPathComponent("encoder-epoch-99-avg-1.int8.onnx")) ? "模型已就位" : "缺模型"
    }

    private func exists(_ url: URL) -> Bool {
        FileManager.default.fileExists(atPath: url.path)
    }

    private func footprintMB() -> Double {
        var info = task_vm_info_data_t()
        var count = mach_msg_type_number_t(
            MemoryLayout<task_vm_info_data_t>.size / MemoryLayout<natural_t>.size)
        let result = withUnsafeMutablePointer(to: &info) {
            $0.withMemoryRebound(to: integer_t.self, capacity: Int(count)) {
                task_info(mach_task_self_, task_flavor_t(TASK_VM_INFO), $0, &count)
            }
        }
        guard result == KERN_SUCCESS else { return 0 }
        return Double(info.phys_footprint) / 1024 / 1024
    }

    func currentMemoryMB() -> Double {
        footprintMB()
    }

    private func configureSession() {
        let session = AVAudioSession.sharedInstance()
        try? session.setCategory(.playAndRecord, mode: .default,
                                 options: [.defaultToSpeaker, .allowBluetooth])
        try? session.setActive(true)
    }

    // MARK: TTS

    func loadTTS() {
        guard tts == nil else { return }
        let loadStart = Date()
        let model = ttsDir.appendingPathComponent("model.int8.onnx")
        guard exists(model) else { ttsStatus = "缺模型：\(ttsDir.path)"; return }
        let kokoro = sherpaOnnxOfflineTtsKokoroModelConfig(
            model: model.path,
            voices: ttsDir.appendingPathComponent("voices.bin").path,
            tokens: ttsDir.appendingPathComponent("tokens.txt").path,
            lexicon: [
                ttsDir.appendingPathComponent("lexicon-us-en.txt").path,
                ttsDir.appendingPathComponent("lexicon-zh.txt").path,
            ].joined(separator: ","))
        let modelConfig = sherpaOnnxOfflineTtsModelConfig(kokoro: kokoro, numThreads: 2, debug: 0)
        var config = sherpaOnnxOfflineTtsConfig(
            model: modelConfig,
            ruleFsts: [
                ttsDir.appendingPathComponent("date-zh.fst").path,
                ttsDir.appendingPathComponent("phone-zh.fst").path,
                ttsDir.appendingPathComponent("number-zh.fst").path,
            ].joined(separator: ","))
        tts = SherpaOnnxOfflineTtsWrapper(config: &config)
        if let tts {
            ttsStatus = String(
                format: "已加载 · %d Hz · %d 音色 · 初始化 %.2f 秒 · 内存 %.0f MB",
                tts.sampleRate, tts.numSpeakers,
                Date().timeIntervalSince(loadStart), footprintMB())
        } else {
            ttsStatus = "加载失败"
        }
    }

    func speakSample() {
        configureSession()
        loadTTS()
        guard let tts else { return }
        let started = Date()
        let audio = tts.generate(text: "你好，我是本地 Agent。", sid: 0, speed: 1.0)
        let samples = audio.samples
        guard !samples.isEmpty else {
            ttsInfo = "生成失败：空音频"
            return
        }
        let outURL = docs.appendingPathComponent("voice-poc-tts.wav")
        _ = audio.save(filename: outURL.path)
        let seconds = Double(samples.count) / Double(audio.sampleRate)
        ttsInfo = String(
            format: "生成 %.2f 秒 · %d Hz · %d samples · 耗时 %.2f 秒 · 内存 %.0f MB\n已保存 voice-poc-tts.wav",
            seconds, Int(audio.sampleRate), samples.count,
            Date().timeIntervalSince(started), footprintMB())
        play(samples: samples, sampleRate: Double(audio.sampleRate))
    }

    private func play(samples: [Float], sampleRate: Double) {
        let format = AVAudioFormat(standardFormatWithSampleRate: sampleRate, channels: 1)!
        guard let buffer = AVAudioPCMBuffer(
            pcmFormat: format, frameCapacity: AVAudioFrameCount(samples.count)) else { return }
        buffer.frameLength = AVAudioFrameCount(samples.count)
        samples.withUnsafeBufferPointer { ptr in
            guard let base = ptr.baseAddress, let channel = buffer.floatChannelData?[0] else { return }
            channel.update(from: base, count: samples.count)
        }

        if playerEngine == nil {
            let engine = AVAudioEngine()
            let node = AVAudioPlayerNode()
            engine.attach(node)
            engine.connect(node, to: engine.mainMixerNode, format: format)
            playerEngine = engine
            playerNode = node
        }
        guard let engine = playerEngine, let node = playerNode else { return }
        try? engine.start()
        isSpeaking = true
        node.scheduleBuffer(buffer, at: nil, options: [], completionHandler: nil)
        node.play()
        Task { @MainActor in
            while node.isPlaying { try? await Task.sleep(nanoseconds: 100_000_000) }
            isSpeaking = false
        }
    }

    // MARK: ASR

    func loadASR() {
        guard recognizer == nil else { return }
        let loadStart = Date()
        let encoder = asrDir.appendingPathComponent("encoder-epoch-99-avg-1.int8.onnx")
        guard exists(encoder) else { asrStatus = "缺模型：\(asrDir.path)"; return }
        let modelConfig = sherpaOnnxOnlineModelConfig(
            tokens: asrDir.appendingPathComponent("tokens.txt").path,
            transducer: sherpaOnnxOnlineTransducerModelConfig(
                encoder: encoder.path,
                decoder: asrDir.appendingPathComponent("decoder-epoch-99-avg-1.int8.onnx").path,
                joiner: asrDir.appendingPathComponent("joiner-epoch-99-avg-1.int8.onnx").path),
            numThreads: 2,
            modelType: "zipformer")
        let featConfig = sherpaOnnxFeatureConfig(sampleRate: 16000, featureDim: 80)
        var config = sherpaOnnxOnlineRecognizerConfig(
            featConfig: featConfig, modelConfig: modelConfig,
            enableEndpoint: true, rule1MinTrailingSilence: 2.4,
            rule2MinTrailingSilence: 0.8, rule3MinUtteranceLength: 30,
            decodingMethod: "greedy_search", maxActivePaths: 4)
        recognizer = SherpaOnnxRecognizer(config: &config)
        asrStatus = String(
            format: "已加载 · streaming zipformer zh 14M · 初始化 %.2f 秒 · 内存 %.0f MB",
            Date().timeIntervalSince(loadStart), footprintMB())
    }

    func recognizeTestFile() {
        loadASR()
        guard let recognizer else { return }
        let wavURL = asrDir.appendingPathComponent("test_wavs/0.wav")
        guard exists(wavURL) else { asrStatus = "缺测试音频：\(wavURL.path)"; return }
        let wave = SherpaOnnxWaveWrapper.readWave(filename: wavURL.path)
        let samples = wave.samples
        guard !samples.isEmpty else { asrStatus = "测试音频为空"; return }
        recognizer.reset()
        recognizer.acceptWaveform(samples: samples, sampleRate: wave.sampleRate)
        recognizer.inputFinished()
        while recognizer.isReady() { recognizer.decode() }
        let text = recognizer.getResult().text
        transcript = text
        asrStatus = String(
            format: "文件识别完成 · %d samples · %d Hz · 内存 %.0f MB",
            samples.count, wave.sampleRate, footprintMB())
    }

    func toggleRecording() {
        if isRecording {
            stopRecording()
        } else {
            AVAudioApplication.requestRecordPermission { granted in
                Task { @MainActor in
                    if granted {
                        self.startRecording()
                    } else {
                        self.asrStatus = "麦克风权限被拒"
                    }
                }
            }
        }
    }

    private func startRecording() {
        configureSession()
        loadASR()
        guard recognizer != nil else { return }
        transcript = ""
        let engine = AVAudioEngine()
        let input = engine.inputNode
        let inputFormat = input.outputFormat(forBus: 0)
        let outputFormat = AVAudioFormat(
            commonFormat: .pcmFormatFloat32, sampleRate: 16000,
            channels: 1, interleaved: false)!
        guard let converter = AVAudioConverter(from: inputFormat, to: outputFormat) else {
            asrStatus = "音频格式转换失败"
            return
        }
        input.installTap(onBus: 0, bufferSize: 1024, format: inputFormat) { [weak self] buffer, _ in
            guard let self else { return }
            var available = true
            let callback: AVAudioConverterInputBlock = { _, status in
                if available {
                    available = false
                    status.pointee = .haveData
                    return buffer
                }
                status.pointee = .noDataNow
                return nil
            }
            let frames = AVAudioFrameCount(
                outputFormat.sampleRate * Double(buffer.frameLength) / buffer.format.sampleRate)
            guard let converted = AVAudioPCMBuffer(pcmFormat: outputFormat, frameCapacity: frames) else { return }
            var error: NSError?
            converter.convert(to: converted, error: &error, withInputFrom: callback)
            guard let channel = converted.floatChannelData?[0] else { return }
            let samples = Array(UnsafeBufferPointer(start: channel, count: Int(converted.frameLength)))
            guard !samples.isEmpty else { return }
            self.recognizer?.acceptWaveform(samples: samples)
            while self.recognizer?.isReady() == true { self.recognizer?.decode() }
            let text = self.recognizer?.getResult().text ?? ""
            let endpoint = self.recognizer?.isEndpoint() == true
            Task { @MainActor in
                if !text.isEmpty { self.transcript = text }
                if endpoint {
                    self.recognizer?.reset()
                }
            }
        }
        audioEngine = engine
        do {
            try engine.start()
            isRecording = true
            asrStatus = "录音中…"
        } catch {
            asrStatus = "启动录音失败：\(error.localizedDescription)"
        }
    }

    private func stopRecording() {
        audioEngine?.stop()
        audioEngine?.inputNode.removeTap(onBus: 0)
        audioEngine = nil
        isRecording = false
        asrStatus = "已停止"
    }
}

struct VoicePOCView: View {
    @StateObject private var model = VoicePOCModel()

    var body: some View {
        NavigationStack {
            List {
                Section("TTS · Kokoro int8 multi-lang v1_1") {
                    Text(model.ttsStatus).font(.footnote).foregroundStyle(.secondary)
                    Button("生成并播放「你好，我是本地 Agent」") {
                        model.speakSample()
                    }
                    if !model.ttsInfo.isEmpty {
                        Text(model.ttsInfo).font(.caption.monospaced()).textSelection(.enabled)
                    }
                }

                Section("ASR · streaming Zipformer zh 14M") {
                    Text(model.asrStatus).font(.footnote).foregroundStyle(.secondary)
                    Button("识别内置测试音频") {
                        model.recognizeTestFile()
                    }
                    Button(model.isRecording ? "停止麦克风" : "开始麦克风") {
                        model.toggleRecording()
                    }
                    if !model.transcript.isEmpty {
                        Text(model.transcript).font(.body.monospaced()).textSelection(.enabled)
                    }
                }

                Section("运行信息") {
                    Text(VoicePOC.versionLine).font(.caption.monospaced()).textSelection(.enabled)
                    Text("App 占用内存约 \(Int(model.currentMemoryMB())) MB")
                        .font(.caption.monospaced())
                    Text("模型目录：Documents（POC 临时布局）").font(.caption).foregroundStyle(.secondary)
                }
            }
            .navigationTitle("语音 POC")
        }
        .task {
            let args = ProcessInfo.processInfo.arguments
            if args.contains("-voicePOCTTS") { model.speakSample() }
            if args.contains("-voicePOCASRFile") { model.recognizeTestFile() }
        }
    }
}
