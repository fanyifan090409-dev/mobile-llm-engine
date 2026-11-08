// 图片 OCR（Vision 框架）：按从上到下输出文本行，用于 PDF 渲染图的公式/图表转写
// 用法：swift ocr.swift image.png
// 注意：Vision 坐标原点在左下角，按 midY 降序排列恢复阅读顺序
import Foundation
import Vision
import AppKit

let args = CommandLine.arguments
guard args.count >= 2, let img = NSImage(contentsOfFile: args[1]),
      let cg = img.cgImage(forProposedRect: nil, context: nil, hints: nil) else {
    print("无法读取图片")
    exit(1)
}
let req = VNRecognizeTextRequest { r, _ in
    guard let obs = r.results as? [VNRecognizedTextObservation] else { return }
    for o in obs.sorted(by: { $0.boundingBox.midY > $1.boundingBox.midY }) {
        if let t = o.topCandidates(1).first {
            print(t.string)
        }
    }
}
req.recognitionLevel = .accurate
req.recognitionLanguages = ["en-US"]
req.usesLanguageCorrection = false
let handler = VNImageRequestHandler(cgImage: cg, options: [:])
try? handler.perform([req])
