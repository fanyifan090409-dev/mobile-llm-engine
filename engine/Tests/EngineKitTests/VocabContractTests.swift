import Testing
import Foundation
import CLLaMA
@testable import EngineKit

// GGUF 词表契约回归：EOT 存在且 is_eog 生效是生成停止正确性的前提。
// 背景：训练机自转 GGUF 缺 added_tokens 元数据（字符串→特殊 token 映射退化），
// 但词表 ID 与 EOG 标志必须完好——本测试钉住这条底线
@Suite("GGUF 词表契约")
struct VocabContractTests {

    private static var hasModel: Bool {
        guard let path = ProcessInfo.processInfo.environment["ENGINEKIT_TEST_MODEL"] else { return false }
        return FileManager.default.fileExists(atPath: path)
    }

    @Test("Qwen3 词表：151645 为 EOT 且 is_eog 生效", .enabled(if: hasModel))
    func eotContract() throws {
        let path = ProcessInfo.processInfo.environment["ENGINEKIT_TEST_MODEL"]!
        CLLaMABackend.ensureInitialized()
        let model = try ModelHandle.load(fileURL: URL(fileURLWithPath: path), nGPU: 0)

        #expect(llama_vocab_n_tokens(model.vocab) == 151936, "Qwen3 词表应为 151936")
        #expect(model.isEog(151645), "<|im_end|> 必须标记 EOG")
        #expect(model.isEog(151643), "<|endoftext|> 必须标记 EOG")
        #expect(model.piece(151645).isEmpty, "EOG 特殊 token 不应渲染为可见文本")
    }
}
