// PDF 逐页渲染成 PNG（真题/讲义材料加工用：转图后人工转写或 OCR）
// 用法：swift pdf2png.swift input.pdf outdir [scale，默认2]
import Foundation
import PDFKit
import AppKit

let args = CommandLine.arguments
guard args.count >= 3 else {
    print("用法：swift pdf2png.swift input.pdf outdir [scale]")
    exit(1)
}
let inURL = URL(fileURLWithPath: args[1])
let outDir = URL(fileURLWithPath: args[2])
let scale = CGFloat(args.count >= 4 ? (Double(args[3]) ?? 2.0) : 2.0)
try? FileManager.default.createDirectory(at: outDir, withIntermediateDirectories: true)
guard let doc = PDFDocument(url: inURL) else {
    print("无法打开 PDF")
    exit(1)
}
for i in 0..<doc.pageCount {
    guard let page = doc.page(at: i) else { continue }
    let bounds = page.bounds(for: .mediaBox)
    let w = bounds.width * scale, h = bounds.height * scale
    let img = NSImage(size: NSSize(width: w, height: h))
    img.lockFocus()
    NSColor.white.setFill()
    NSRect(x: 0, y: 0, width: w, height: h).fill()
    if let ctx = NSGraphicsContext.current?.cgContext {
        ctx.scaleBy(x: scale, y: scale)
        page.draw(with: .mediaBox, to: ctx)
    }
    img.unlockFocus()
    guard let tiff = img.tiffRepresentation,
          let rep = NSBitmapImageRep(data: tiff),
          let png = rep.representation(using: .png, properties: [:]) else { continue }
    let name = String(format: "page-%02d.png", i + 1)
    try? png.write(to: outDir.appendingPathComponent(name))
    print(name)
}
print("共渲染 \(doc.pageCount) 页")
