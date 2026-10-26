import CLLaMA

// 桥接层错误：C 层错误码统一转 Swift Error，不把 llama.cpp 错误语义暴露给上层
internal enum CLLaMAError: Error, CustomStringConvertible {
    case modelLoadFailed(String)
    case contextInitFailed
    case decodeFailed(Int32)
    case tokenizeFailed
    case samplerInitFailed

    var description: String {
        switch self {
        case .modelLoadFailed(let path):
            return "模型加载失败：\(path)"
        case .contextInitFailed:
            return "上下文初始化失败"
        case .decodeFailed(let rc):
            return "解码失败（rc=\(rc)）"
        case .tokenizeFailed:
            return "分词失败"
        case .samplerInitFailed:
            return "采样器初始化失败"
        }
    }
}

// llama.cpp 全局后端（Metal 注册）只需初始化一次；
// M1 生成队列串行调用，无并发竞争
internal enum CLLaMABackend {
    private static var initialized = false

    static func ensureInitialized() {
        guard !initialized else { return }
        llama_backend_init()
        initialized = true
    }
}
