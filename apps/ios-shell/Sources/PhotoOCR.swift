import UIKit
import Vision

// 数学题照片 → 文本：Apple Vision 本机识别，离线、无第三方依赖、图片不出设备。
// 数学排版的两个坑：
// ① Vision 常把 x² 拆成独立的「2」fragment → 用字号+基线几何还原成 x^2；
// ② 识别器会把 ×、−、√ 等符号换成近形字符 → 统一归一成 math.js 能吃的写法。
enum PhotoOCR {
    enum Failure: LocalizedError {
        case decode
        case noText

        var errorDescription: String? {
            switch self {
            case .decode: return "图片读取失败，换一张试试"
            case .noText: return "没识别到文字，尽量拍正、拍清楚题目"
            }
        }
    }

    static func recognize(_ image: UIImage) async throws -> String {
        let prepared = downscaled(image, maxSide: 1600)
        guard let cgImage = prepared.cgImage else { throw Failure.decode }
        let orientation = cgOrientation(prepared.imageOrientation)
        let box = ImageBox(cgImage: cgImage)
        return try await withCheckedThrowingContinuation { cont in
            DispatchQueue.global(qos: .userInitiated).async {
                do {
                    let request = VNRecognizeTextRequest()
                    request.recognitionLevel = .accurate
                    // 数学符号不能被语言模型「纠正」；中文题干仍可正常识别
                    request.usesLanguageCorrection = false
                    request.recognitionLanguages = ["zh-Hans", "en-US"]
                    let handler = VNImageRequestHandler(cgImage: box.cgImage, orientation: orientation)
                    try handler.perform([request])
                    let text = assemble(request.results ?? [])
                    if text.isEmpty {
                        cont.resume(throwing: Failure.noText)
                    } else {
                        cont.resume(returning: text)
                    }
                } catch {
                    cont.resume(throwing: error)
                }
            }
        }
    }

    // CGImage 跨队列传递：Vision 只读，线程安全
    private struct ImageBox: @unchecked Sendable {
        let cgImage: CGImage
    }

    // UIImage.Orientation 与 EXIF 枚举的 rawValue 不一致，必须显式映射
    private static func cgOrientation(_ orientation: UIImage.Orientation) -> CGImagePropertyOrientation {
        switch orientation {
        case .up: return .up
        case .down: return .down
        case .left: return .left
        case .right: return .right
        case .upMirrored: return .upMirrored
        case .downMirrored: return .downMirrored
        case .leftMirrored: return .leftMirrored
        case .rightMirrored: return .rightMirrored
        @unknown default: return .up
        }
    }

    private struct Fragment {
        let text: String
        let box: CGRect
    }

    // 行分组 + 上下标还原。坐标是 Vision 的归一化坐标（原点左下）
    private static func assemble(_ observations: [VNRecognizedTextObservation]) -> String {
        var fragments: [Fragment] = observations.compactMap { obs in
            guard let candidate = obs.topCandidates(1).first else { return nil }
            return Fragment(text: candidate.string, box: obs.boundingBox)
        }
        guard !fragments.isEmpty else { return "" }
        fragments.sort { $0.box.midY > $1.box.midY }

        var lines: [[Fragment]] = []
        for fragment in fragments {
            if var last = lines.last, let ref = last.first,
               abs(fragment.box.midY - ref.box.midY) < max(fragment.box.height, ref.box.height) * 0.6 {
                last.append(fragment)
                lines[lines.count - 1] = last
            } else {
                lines.append([fragment])
            }
        }

        var output: [String] = []
        for var line in lines {
            line.sort { $0.box.minX < $1.box.minX }
            let heights = line.map(\.box.height).sorted()
            let medianH = heights[heights.count / 2]
            let mids = line.map(\.box.midY).sorted()
            let lineMid = mids[mids.count / 2]
            var parts: [String] = []
            for fragment in line {
                let text = normalize(fragment.text)
                let small = fragment.box.height < medianH * 0.72
                let raised = fragment.box.midY > lineMid + medianH * 0.15
                let lowered = fragment.box.midY < lineMid - medianH * 0.15
                if small, raised, !parts.isEmpty {
                    parts[parts.count - 1] += "^" + text
                } else if small, lowered, !parts.isEmpty {
                    parts[parts.count - 1] += "_" + text
                } else {
                    parts.append(text)
                }
            }
            output.append(parts.joined(separator: " "))
        }
        return output.joined(separator: "\n")
    }

    private static let replacements: [(String, String)] = [
        ("×", "*"), ("·", "*"), ("÷", "/"), ("−", "-"), ("–", "-"), ("—", "-"),
        ("＝", "="), ("（", "("), ("）", ")"), ("，", ","), ("。", "."), ("：", ":"),
        ("√", "sqrt"), ("π", "pi"), ("∞", "inf"),
        ("⁰", "^0"), ("¹", "^1"), ("²", "^2"), ("³", "^3"), ("⁴", "^4"),
        ("⁵", "^5"), ("⁶", "^6"), ("⁷", "^7"), ("⁸", "^8"), ("⁹", "^9"),
    ]

    private static func normalize(_ text: String) -> String {
        var s = text
        for (from, to) in replacements {
            s = s.replacingOccurrences(of: from, with: to)
        }
        // 题目编号（"3." / "(1)"）交给模型忽略，这里不动
        return s.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private static func downscaled(_ image: UIImage, maxSide: CGFloat) -> UIImage {
        let size = image.size
        let scale = min(1, maxSide / max(size.width, size.height))
        guard scale < 1 else { return image }
        let target = CGSize(width: size.width * scale, height: size.height * scale)
        return UIGraphicsImageRenderer(size: target).image { _ in
            image.draw(in: CGRect(origin: .zero, size: target))
        }
    }
}
