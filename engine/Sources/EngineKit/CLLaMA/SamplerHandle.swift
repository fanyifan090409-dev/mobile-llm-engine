import CLLaMA

// llama_sampler 链所有权封装：temp → top_p → dist（chain 接管子采样器，只 free chain 本体）
internal final class SamplerHandle {
    // llama_sampler 在头文件里有完整定义（非不透明类型），导入为 UnsafeMutablePointer
    let sampler: UnsafeMutablePointer<llama_sampler>

    private init(sampler: UnsafeMutablePointer<llama_sampler>) {
        self.sampler = sampler
    }

    static func chain(temperature: Float, topP: Float = 0.9, seed: UInt32 = 42) throws -> SamplerHandle {
        let sparams = llama_sampler_chain_default_params()
        guard let chain = llama_sampler_chain_init(sparams) else {
            throw CLLaMAError.samplerInitFailed
        }
        llama_sampler_chain_add(chain, llama_sampler_init_temp(temperature))
        llama_sampler_chain_add(chain, llama_sampler_init_top_p(topP, 1))
        llama_sampler_chain_add(chain, llama_sampler_init_dist(seed))
        return SamplerHandle(sampler: chain)
    }

    // idx=-1：对最后一个输出的 logits 采样
    func sample(_ ctx: ContextHandle) -> llama_token {
        llama_sampler_sample(sampler, ctx.ctx, -1)
    }

    deinit {
        llama_sampler_free(sampler)
    }
}
