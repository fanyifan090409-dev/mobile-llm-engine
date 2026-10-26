import Foundation

// 真机无 Xcode 控制台：运行痕迹全量落盘 Documents/engine-shell.log（证据链），UI 同步滚动
final class AppLog: ObservableObject {
    static let shared = AppLog()

    @Published var lines: [String] = []

    private let handle: FileHandle
    private let stamp: DateFormatter

    private init() {
        let docs = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
        let url = docs.appendingPathComponent("engine-shell.log")
        if !FileManager.default.fileExists(atPath: url.path) {
            FileManager.default.createFile(atPath: url.path, contents: nil)
        }
        handle = try! FileHandle(forWritingTo: url)
        handle.seekToEndOfFile()
        stamp = DateFormatter()
        stamp.dateFormat = "yyyy-MM-dd HH:mm:ss.SSS"
    }

    func log(_ message: String) {
        let line = "[\(stamp.string(from: Date()))] \(message)"
        Task { @MainActor in self.lines.append(line) }
        if let data = (line + "\n").data(using: .utf8) {
            handle.write(data)
        }
    }
}
