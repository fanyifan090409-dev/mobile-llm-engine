/// 内存档位：low/standard/high 对应 0.6B / 1.7B / 4B 模型档（落地计划 v0.1 契约）
/// M1 只定义枚举，M3 用于内存预算自动选档
public enum MemoryTier: CaseIterable {
    case low
    case standard
    case high
}
