import CLLaMA
import Foundation

// llama_model 所有权封装：C 指针不出此层，释放顺序由 Swift deinit 保证
internal final class ModelHandle {
    let model: OpaquePointer      // llama_model *
    let vocab: OpaquePointer      // llama_vocab *（随 model 释放，不单独 free）

    private init(model: OpaquePointer) {
        self.model = model
        self.vocab = llama_model_get_vocab(model)
    }

    static func load(fileURL: URL, nGPU: Int32 = -1) throws -> ModelHandle {
        var params = llama_model_default_params()
        // nGPU=-1 表示全部层上 GPU（Metal）；n_ctx 属于 context 参数，不在这里
        params.n_gpu_layers = nGPU
        let path = fileURL.path
        guard let m = path.withCString({ llama_model_load_from_file($0, params) }) else {
            throw CLLaMAError.modelLoadFailed(path)
        }
        return ModelHandle(model: m)
    }

    func makeContext(context: Int32, batch: Int32 = 2048, threads: Int32 = 4, threadsBatch: Int32 = 4) throws -> ContextHandle {
        try ContextHandle(modelHandle: self, context: context, batch: batch, threads: threads, threadsBatch: threadsBatch)
    }

    // 分词：两段式调用。首调用 NULL buffer 时 API 返回负数（= 所需 token 数的相反数），
    // 按 |n| 分配后二调用；INT32_MIN 才是真溢出失败
    func tokenize(_ text: String, addSpecial: Bool = true) throws -> [llama_token] {
        let cText = Array(text.utf8CString)
        let byteCount = Int32(cText.count - 1)
        var n = llama_tokenize(vocab, cText, byteCount, nil, 0, addSpecial, false)
        guard n != Int32.min else { throw CLLaMAError.tokenizeFailed }
        if n < 0 { n = -n }
        var tokens = [llama_token](repeating: 0, count: Int(n))
        let rc = llama_tokenize(vocab, cText, byteCount, &tokens, Int32(tokens.count), addSpecial, false)
        guard rc >= 0 else { throw CLLaMAError.tokenizeFailed }
        return Array(tokens.prefix(Int(rc)))
    }

    // token 还原文本：API 不写结尾 \0，按返回字节数截取
    func piece(_ token: llama_token) -> String {
        var buf = [CChar](repeating: 0, count: 256)
        let n = llama_token_to_piece(vocab, token, &buf, Int32(buf.count), 0, false)
        guard n > 0 else { return "" }
        let bytes = buf.prefix(Int(n)).map { UInt8(bitPattern: $0) }
        return String(bytes: bytes, encoding: .utf8) ?? ""
    }

    func isEog(_ token: llama_token) -> Bool {
        llama_vocab_is_eog(vocab, token)
    }

    var eosToken: llama_token { llama_vocab_eos(vocab) }

    deinit {
        llama_model_free(model)
    }
}
