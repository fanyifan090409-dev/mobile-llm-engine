import AVFoundation
import SherpaOnnx

// P1 语音输入/播报：ASR 与 TTS 都走本机 sherpa-onnx，不碰文本推理链路
@MainActor
final class VoiceService: ObservableObject {
    @Published private(set) var isRecording = false
    @Published private(set) var isSpeaking = false
    @Published private(set) var transcript = ""
    @Published private(set) var notice: String?

    private let docs = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
    private var asrDir: URL? {
        findDir("sherpa-onnx-streaming-zipformer-zh-14M-2023-02-23")
    }
    private var ttsDir: URL? {
        findDir("kokoro-int8-multi-lang-v1_1")
    }

    private var recognizer: SherpaOnnxRecognizer?
    private var audioEngine: AVAudioEngine?
    private var playerEngine: AVAudioEngine?
    private var playerNode: AVAudioPlayerNode?
    private var onTranscript: ((String) -> Void)?

    var isASRAvailable: Bool {
        guard let dir = asrDir else { return false }
        return FileManager.default.fileExists(
            atPath: dir.appendingPathComponent("encoder-epoch-99-avg-1.int8.onnx").path)
    }

    var isTTSAvailable: Bool {
        guard let dir = ttsDir else { return false }
        return FileManager.default.fileExists(atPath: dir.appendingPathComponent("model.int8.onnx").path)
    }

    func clearNotice() { notice = nil }

    private func findDir(_ name: String) -> URL? {
        for base in [docs.appendingPathComponent("VoiceModels"), docs] {
            let url = base.appendingPathComponent(name)
            if FileManager.default.fileExists(atPath: url.path) { return url }
        }
        return nil
    }

    private func configureSession() {
        let session = AVAudioSession.sharedInstance()
        try? session.setCategory(.playAndRecord, mode: .default,
                                 options: [.defaultToSpeaker, .allowBluetooth])
        try? session.setActive(true)
    }

    // MARK: ASR

    func startRecording(completion: @escaping (String) -> Void) {
        guard !isRecording else { return }
        guard isASRAvailable else {
            notice = "语音模型未安装：Documents/VoiceModels"
            return
        }
        onTranscript = completion
        transcript = ""
        notice = nil
        AVAudioApplication.requestRecordPermission { granted in
            Task { @MainActor in
                guard granted else {
                    self.notice = "麦克风权限被拒绝，请在系统设置中允许"
                    self.onTranscript = nil
                    return
                }
                self.beginRecording()
            }
        }
    }

    private func beginRecording() {
        configureSession()
        loadASR()
        guard recognizer != nil else { return }
        let engine = AVAudioEngine()
        let input = engine.inputNode
        let inputFormat = input.outputFormat(forBus: 0)
        guard inputFormat.sampleRate > 0,
              let outputFormat = AVAudioFormat(
                commonFormat: .pcmFormatFloat32, sampleRate: 16000,
                channels: 1, interleaved: false),
              let converter = AVAudioConverter(from: inputFormat, to: outputFormat)
        else {
            notice = "音频输入不可用"
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
        } catch {
            notice = "启动录音失败：\(error.localizedDescription)"
            cleanUpRecording()
        }
    }

    func stopRecording() {
        guard isRecording else { return }
        let text = transcript.trimmingCharacters(in: .whitespacesAndNewlines)
        audioEngine?.stop()
        cleanUpRecording()
        let completion = onTranscript
        onTranscript = nil
        completion?(text)
    }

    func cancelRecording() {
        guard isRecording else { return }
        audioEngine?.stop()
        cleanUpRecording()
        onTranscript = nil
    }

    private func cleanUpRecording() {
        audioEngine?.inputNode.removeTap(onBus: 0)
        audioEngine = nil
        recognizer = nil
        isRecording = false
    }

    private func makeRecognizer() -> SherpaOnnxRecognizer? {
        guard let dir = asrDir else { return nil }
        let encoder = dir.appendingPathComponent("encoder-epoch-99-avg-1.int8.onnx")
        let modelConfig = sherpaOnnxOnlineModelConfig(
            tokens: dir.appendingPathComponent("tokens.txt").path,
            transducer: sherpaOnnxOnlineTransducerModelConfig(
                encoder: encoder.path,
                decoder: dir.appendingPathComponent("decoder-epoch-99-avg-1.int8.onnx").path,
                joiner: dir.appendingPathComponent("joiner-epoch-99-avg-1.int8.onnx").path),
            numThreads: 2,
            modelType: "zipformer")
        let featConfig = sherpaOnnxFeatureConfig(sampleRate: 16000, featureDim: 80)
        var config = sherpaOnnxOnlineRecognizerConfig(
            featConfig: featConfig, modelConfig: modelConfig,
            enableEndpoint: true, rule1MinTrailingSilence: 2.4,
            rule2MinTrailingSilence: 0.8, rule3MinUtteranceLength: 30,
            decodingMethod: "greedy_search", maxActivePaths: 4)
        return SherpaOnnxRecognizer(config: &config)
    }

    private func loadASR() {
        guard recognizer == nil else { return }
        recognizer = makeRecognizer()
    }

    // 文件/合成音频识别：不经过麦克风，供 harness 回归和 POC 复用
    func transcribe(samples: [Float], sampleRate: Int) -> String? {
        guard !samples.isEmpty, let rec = makeRecognizer() else {
            notice = "语音模型未安装：Documents/VoiceModels"
            return nil
        }
        let input = sampleRate == 16000
            ? samples
            : Self.resample(samples, from: sampleRate, to: 16000)
        rec.acceptWaveform(samples: input, sampleRate: 16000)
        rec.inputFinished()
        while rec.isReady() { rec.decode() }
        return rec.getResult().text
    }

    // 24k TTS 音频转 16k 给 Zipformer；线性插值对短句识别足够
    private static func resample(_ samples: [Float], from source: Int, to target: Int) -> [Float] {
        guard source > 0, target > 0, source != target, samples.count > 1 else { return samples }
        let ratio = Double(source) / Double(target)
        let count = max(1, Int(Double(samples.count) / ratio))
        var output = [Float](repeating: 0, count: count)
        for i in 0..<count {
            let position = Double(i) * ratio
            let index = min(Int(position), samples.count - 1)
            let next = min(index + 1, samples.count - 1)
            let fraction = Float(position - Double(index))
            output[i] = samples[index] * (1 - fraction) + samples[next] * fraction
        }
        return output
    }

    // MARK: TTS

    struct SynthResult {
        let samples: [Float]
        let sampleRate: Int
    }

    // 只合成不播放，harness 用它验证 TTS 并做回环识别
    func synthesize(_ text: String) -> SynthResult? {
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return nil }
        guard isTTSAvailable, let dir = ttsDir else {
            notice = "语音模型未安装：Documents/VoiceModels"
            return nil
        }
        let kokoro = sherpaOnnxOfflineTtsKokoroModelConfig(
            model: dir.appendingPathComponent("model.int8.onnx").path,
            voices: dir.appendingPathComponent("voices.bin").path,
            tokens: dir.appendingPathComponent("tokens.txt").path,
            lexicon: [
                dir.appendingPathComponent("lexicon-us-en.txt").path,
                dir.appendingPathComponent("lexicon-zh.txt").path,
            ].joined(separator: ","))
        let modelConfig = sherpaOnnxOfflineTtsModelConfig(kokoro: kokoro, numThreads: 2, debug: 0)
        var config = sherpaOnnxOfflineTtsConfig(
            model: modelConfig,
            ruleFsts: [
                dir.appendingPathComponent("date-zh.fst").path,
                dir.appendingPathComponent("phone-zh.fst").path,
                dir.appendingPathComponent("number-zh.fst").path,
            ].joined(separator: ","))
        let wrapper = SherpaOnnxOfflineTtsWrapper(config: &config)
        let audio = wrapper.generate(text: trimmed, sid: 0, speed: 1.0)
        guard !audio.samples.isEmpty else {
            notice = "语音生成失败"
            return nil
        }
        return SynthResult(samples: audio.samples, sampleRate: Int(audio.sampleRate))
    }

    func speak(_ text: String) {
        stopSpeaking()
        guard let audio = synthesize(text) else { return }
        configureSession()
        play(samples: audio.samples, sampleRate: Double(audio.sampleRate))
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
            self.isSpeaking = false
        }
    }

    func stopSpeaking() {
        playerNode?.stop()
        isSpeaking = false
    }
}
