import Foundation

// 引擎协议（落地计划 v0.1 的 M1 子集）：resolveTier 只做雏形，M3 完整
public protocol LocalEngine {
    // 内存预算 → 可用档位（雏形：物理内存查表；M3 接入热控与真机预算）
    func resolveTier(deviceMemory: Int) -> MemoryTier?
    func load(_ spec: ModelSpec) async throws
    func generate(_ req: GenerationRequest) -> AsyncThrowingStream<TokenEvent, Error>
    // 内存墙：用后即卸，模型权重全部释放
    func unload()
}
