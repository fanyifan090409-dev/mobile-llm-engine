import CoreGraphics
import Foundation
import UIKit

// 公式照片 → LaTeX：Texo（20M 蒸馏版）走 ONNX Runtime 本机推理。
// 预处理必须和训练/导出脚本逐像素对齐：去白边 → 等比缩放到长边 384 → 黑边 pad 384×384
// → PIL 同款灰度 → (v/255-0.7931)/0.1738 → 灰度复制 3 通道。
// 中文题干仍交给 Vision（见 PhotoOCR）；这里只负责数学排版。
enum TexoOCR {
    struct Failure: LocalizedError {
        let message: String
        var errorDescription: String? { message }
    }

    private static let inputSize = 384
    private static let mean: Float = 0.7931
    private static let std: Float = 0.1738
    // 与 PIL ImageOps.grayscale 阈值一致；留 8px 边距避免笔画贴边影响缩放
    private static let darkThreshold = 200.0
    private static let cropPadding = 8

    private static let lock = NSLock()
    private static var runner: TexoRunner?
    private static var runnerError: String?
    private static var vocabulary: [Int: String]?

    static func latex(from image: UIImage, maxLength: Int = 256) throws -> String {
        guard let prepared = preparedImage(image),
              let cropped = cropMargin(prepared) else {
            throw Failure(message: "图片读取失败，换一张试试")
        }
        let pixels = try inputTensor(cropped)
        lock.lock()
        defer { lock.unlock() }
        let engine = try sharedRunner()
        let ids = try engine.generateTokens(withPixels: pixels, maxLength: maxLength)
        let vocab = try sharedVocabulary()
        var latex = ""
        for number in ids {
            guard let token = vocab[number.intValue], !token.hasPrefix("<") else { continue }
            latex += token
        }
        return latex
    }

    static func problem(from image: UIImage) throws -> (latex: String, problem: String) {
        let latex = try latex(from: image)
        guard !latex.isEmpty else { throw Failure(message: "没认出公式，尽量拍正、只拍题目") }
        return (latex, FormulaText.problem(from: latex))
    }

    // MARK: - 资源加载

    private static func sharedRunner() throws -> TexoRunner {
        if let runner { return runner }
        if let runnerError { throw Failure(message: runnerError) }
        guard let encoder = Bundle.main.url(forResource: "encoder_model", withExtension: "onnx",
                                            subdirectory: "FormulaOCR"),
              let decoder = Bundle.main.url(forResource: "decoder_model", withExtension: "onnx",
                                            subdirectory: "FormulaOCR") else {
            let message = "缺少 Texo 模型（FormulaOCR/encoder_model.onnx、decoder_model.onnx）"
            runnerError = message
            throw Failure(message: message)
        }
        do {
            let engine = try TexoRunner(encoderPath: encoder.path, decoderPath: decoder.path)
            runner = engine
            return engine
        } catch {
            let message = "Texo 加载失败：\(error.localizedDescription)"
            runnerError = message
            throw Failure(message: message)
        }
    }

    private static func sharedVocabulary() throws -> [Int: String] {
        if let vocabulary { return vocabulary }
        guard let url = Bundle.main.url(forResource: "tokenizer", withExtension: "json",
                                        subdirectory: "FormulaOCR") else {
            throw Failure(message: "缺少 FormulaOCR/tokenizer.json")
        }
        let data = try Data(contentsOf: url)
        guard let root = try JSONSerialization.jsonObject(with: data) as? [String: Any],
              let model = root["model"] as? [String: Any],
              let vocab = model["vocab"] as? [String: Int] else {
            throw Failure(message: "tokenizer.json 格式异常")
        }
        var result: [Int: String] = [:]
        for (token, id) in vocab { result[id] = token }
        vocabulary = result
        return result
    }

    // MARK: - 图像预处理

    // 顺手修掉 EXIF 方向；限制长边 1600 省内存（原图 12MP 处理一次约 50MB）
    private static func preparedImage(_ image: UIImage, maxSide: CGFloat = 1600) -> CGImage? {
        let size = image.size
        guard size.width > 0, size.height > 0 else { return nil }
        let scale = min(1, maxSide / max(size.width, size.height))
        let target = CGSize(width: max(1, (size.width * scale).rounded()),
                            height: max(1, (size.height * scale).rounded()))
        let format = UIGraphicsImageRendererFormat.default()
        format.scale = 1
        format.opaque = true
        let rendered = UIGraphicsImageRenderer(size: target, format: format).image { context in
            UIColor.white.setFill()
            context.fill(CGRect(origin: .zero, size: target))
            image.draw(in: CGRect(origin: .zero, size: target))
        }
        return rendered.cgImage
    }

    private static func cropMargin(_ image: CGImage) -> CGImage? {
        guard let rgba = rgbaBuffer(image) else { return nil }
        let width = image.width
        let height = image.height
        let luma = lumaBuffer(rgba, width: width, height: height)

        var minValue = UInt8.max
        var maxValue = UInt8.min
        for value in luma {
            minValue = min(minValue, value)
            maxValue = max(maxValue, value)
        }
        guard maxValue > minValue else { return image }

        // 与 PIL 一致：先按整图最小/最大归一化，再取 <200 的像素外接框
        let scale = 255.0 / Double(maxValue - minValue)
        var minX = width, minY = height, maxX = -1, maxY = -1
        for y in 0..<height {
            let row = y * width
            for x in 0..<width {
                let value = (Double(luma[row + x]) - Double(minValue)) * scale
                if value < darkThreshold {
                    minX = min(minX, x)
                    maxX = max(maxX, x)
                    minY = min(minY, y)
                    maxY = max(maxY, y)
                }
            }
        }
        guard maxX >= minX, maxY >= minY else { return image }

        let x0 = max(0, minX - cropPadding)
        let y0 = max(0, minY - cropPadding)
        let x1 = min(width, maxX + 1 + cropPadding)
        let y1 = min(height, maxY + 1 + cropPadding)
        // CGImage.cropping 用左上原点，和 luma 缓冲区行序一致
        return image.cropping(to: CGRect(x: x0, y: y0, width: x1 - x0, height: y1 - y0))
    }

    private static func inputTensor(_ image: CGImage) throws -> Data {
        // 与 Python 一致：先按长边缩到 384（小图也放大），再居中黑边 pad
        let scale = CGFloat(inputSize) / CGFloat(max(image.width, image.height))
        let targetWidth = max(1, Int((CGFloat(image.width) * scale).rounded()))
        let targetHeight = max(1, Int((CGFloat(image.height) * scale).rounded()))

        var rgba = [UInt8](repeating: 0, count: inputSize * inputSize * 4)
        guard let context = CGContext(data: &rgba, width: inputSize, height: inputSize,
                                      bitsPerComponent: 8, bytesPerRow: inputSize * 4,
                                      space: CGColorSpaceCreateDeviceRGB(),
                                      bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue) else {
            throw Failure(message: "图像预处理失败")
        }
        context.setFillColor(CGColor(red: 0, green: 0, blue: 0, alpha: 1))
        context.fill(CGRect(x: 0, y: 0, width: inputSize, height: inputSize))
        context.interpolationQuality = .high
        context.draw(image, in: CGRect(x: (inputSize - targetWidth) / 2,
                                       y: (inputSize - targetHeight) / 2,
                                       width: targetWidth, height: targetHeight))

        let luma = lumaBuffer(rgba, width: inputSize, height: inputSize)
        let plane = inputSize * inputSize
        var values = [Float](repeating: 0, count: plane * 3)
        for index in 0..<plane {
            let value = (Float(luma[index]) / 255 - mean) / std
            values[index] = value
            values[plane + index] = value
            values[plane * 2 + index] = value
        }
        return Data(bytes: values, count: values.count * MemoryLayout<Float>.size)
    }

    private static func rgbaBuffer(_ image: CGImage) -> [UInt8]? {
        let width = image.width
        let height = image.height
        var buffer = [UInt8](repeating: 0, count: width * height * 4)
        guard let context = CGContext(data: &buffer, width: width, height: height,
                                      bitsPerComponent: 8, bytesPerRow: width * 4,
                                      space: CGColorSpaceCreateDeviceRGB(),
                                      bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue) else {
            return nil
        }
        context.draw(image, in: CGRect(x: 0, y: 0, width: width, height: height))
        return buffer
    }

    // PIL convert("L") 的 ITU-R 601-2 权重；不能交给 DeviceGray 做（gamma 处理会漂）
    private static func lumaBuffer(_ rgba: [UInt8], width: Int, height: Int) -> [UInt8] {
        var luma = [UInt8](repeating: 0, count: width * height)
        for index in 0..<(width * height) {
            let offset = index * 4
            let value = 0.299 * Double(rgba[offset])
                + 0.587 * Double(rgba[offset + 1])
                + 0.114 * Double(rgba[offset + 2])
            luma[index] = UInt8(clamping: Int(value.rounded()))
        }
        return luma
    }
}
