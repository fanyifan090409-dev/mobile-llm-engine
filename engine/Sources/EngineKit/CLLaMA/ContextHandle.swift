import CLLaMA

// llama_context 所有权封装：KV 上限、batch 大小、线程数在此层定
internal final class ContextHandle {
    let ctx: OpaquePointer      // llama_context *
    let memory: OpaquePointer   // llama_memory_t（KV 管理入口）
    private let modelHandle: ModelHandle   // 保证释放顺序：ctx 先于 model（Swift deinit 顺序与成员声明顺序相反）

    init(modelHandle: ModelHandle, context: Int32, batch: Int32, threads: Int32, threadsBatch: Int32) throws {
        var params = llama_context_default_params()
        params.n_ctx = UInt32(context)
        params.n_batch = UInt32(batch)
        params.n_ubatch = UInt32(batch)   // 物理 batch 上限，与逻辑 batch 一致即可
        params.n_threads = threads
        params.n_threads_batch = threadsBatch
        guard let c = llama_init_from_model(modelHandle.model, params) else {
            throw CLLaMAError.contextInitFailed
        }
        self.ctx = c
        self.memory = llama_get_memory(c)
        self.modelHandle = modelHandle
    }

    var nVocab: Int32 { llama_vocab_n_tokens(modelHandle.vocab) }

    // 实际 KV 上限（可能被 llama.cpp 对齐调整，取实际值而非请求值）
    var nCtx: UInt32 { llama_n_ctx(ctx) }

    // 解码一批 token；batch_get_one 的 logits 为 NULL → 只输出最后一个 token 的 logits
    func decode(tokens: [llama_token]) throws {
        var toks = tokens
        let batch = llama_batch_get_one(&toks, Int32(toks.count))
        let rc = llama_decode(ctx, batch)
        guard rc == 0 else { throw CLLaMAError.decodeFailed(rc) }
    }

    // 最后一个 token 的 logits（-1 = 倒序第一个）；无输出时为 nil
    func lastLogits() -> UnsafeMutablePointer<Float>? {
        llama_get_logits_ith(ctx, -1)
    }

    // 清空 KV：新一轮对话/卸载前释放上下文内存
    func clearMemory() {
        llama_memory_clear(memory, true)
    }

    deinit {
        llama_free(ctx)
    }
}
