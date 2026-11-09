#if DEBUG
import Darwin
import UIKit

// 真机自检入口：启动参数 --formula-ocr-selftest 时跑两次公式 OCR（冷/热），
// 不依赖相册 UI，结果写进 engine-shell.log，可用 devicectl 取证。
enum FormulaOCRProbe {
    static func runIfRequested() {
        guard ProcessInfo.processInfo.arguments.contains("--formula-ocr-selftest") else { return }
        DispatchQueue.global(qos: .userInitiated).async {
            guard let url = Bundle.main.url(forResource: "formula-selftest", withExtension: "png"),
                  let image = UIImage(contentsOfFile: url.path) else {
                AppLog.shared.log("OCR 自检：缺少 formula-selftest.png")
                return
            }
            for pass in 1...2 {
                let begin = Date()
                do {
                    let result = try TexoOCR.problem(from: image)
                    let ms = Int(Date().timeIntervalSince(begin) * 1000)
                    AppLog.shared.log("OCR 自检 \(pass == 1 ? "冷启动" : "热"): \(ms)ms | \(result.latex) | \(result.problem)")
                } catch {
                    AppLog.shared.log("OCR 自检 \(pass) 失败：\(error)")
                }
            }
            AppLog.shared.log("OCR 自检：常驻内存 \(residentMB())MB")
        }
    }

    private static func residentMB() -> Int {
        var info = mach_task_basic_info()
        var count = mach_msg_type_number_t(MemoryLayout<mach_task_basic_info>.size / MemoryLayout<integer_t>.size)
        let status = withUnsafeMutablePointer(to: &info) { pointer in
            pointer.withMemoryRebound(to: integer_t.self, capacity: Int(count)) {
                task_info(mach_task_self_, task_flavor_t(MACH_TASK_BASIC_INFO), $0, &count)
            }
        }
        guard status == KERN_SUCCESS else { return -1 }
        return Int(info.resident_size / 1024 / 1024)
    }
}
#endif
