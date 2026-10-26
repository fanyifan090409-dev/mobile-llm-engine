/// 速度/功耗档：四档用户可调（开工要求①），与内存档位正交
/// M1 映射到 ngl/线程数，M3 加热感知降档
/// 中文名（用户指南 docs/模型量化档位用户指南.md 同源）：节能 / 均衡 / 高性能 / 极速
/// 实测（M1.5 双 Mac）：解码速度四档几乎无差（带宽瓶颈），差异在预填充首响与功耗
public enum SpeedTier: Int, CaseIterable {
    case powerSaver
    case balanced
    case performance
    case turbo
}
