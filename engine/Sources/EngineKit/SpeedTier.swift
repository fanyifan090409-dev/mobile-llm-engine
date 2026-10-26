/// 速度/功耗档：四档用户可调（开工要求①），与内存档位正交
/// M1 映射到 ngl/线程数，M3 加热感知降档
public enum SpeedTier: Int, CaseIterable {
    case powerSaver
    case balanced
    case performance
    case turbo
}
