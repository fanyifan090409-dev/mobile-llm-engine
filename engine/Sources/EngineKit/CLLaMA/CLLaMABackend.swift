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
public enum CLLaMABackend {
    private static var initialized = false

    // llama.cpp 日志出口：真机无控制台，宿主演进取证全靠它（如 vocab 初始化打印的 EOG 列表）。
    // 生命周期约定：仅启动早期（任何 llama 活动前）写入一次；回调在 llama 内部线程读
    public static var logHook: ((String) -> Void)?

    static func ensureInitialized() {
        guard !initialized else { return }
        llama_log_set(llamaCLogCallback, nil)
        llama_backend_init()
        initialized = true
    }
}

// C 回调载体：文件级函数无捕获，天然可转 C 函数指针；日志内容转发给宿主 logHook
private func llamaCLogCallback(_ level: ggml_log_level, _ text: UnsafePointer<CChar>?, _ userData: UnsafeMutableRawPointer?) {
    guard let text else { return }
    CLLaMABackend.logHook?(String(cString: text))
}
