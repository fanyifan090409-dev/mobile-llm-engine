// PDF 逐页文本抽取（官方数字排版 PDF 有文本层，比 OCR 保真；数学符号以 Unicode 呈现）
// 用法：swift pdftext.swift input.pdf [页码，如 3 或 2-5，缺省全部]
import Foundation
import PDFKit

let args = CommandLine.arguments
guard args.count >= 2 else {
    print("用法：swift pdftext.swift input.pdf [页码]")
    exit(1)
}
guard let doc = PDFDocument(url: URL(fileURLWithPath: args[1])) else {
    print("无法打开 PDF")
    exit(1)
}
var pages: [Int] = Array(0..<doc.pageCount)
if args.count >= 3 {
    let spec = args[2]
    let parts = spec.split(separator: "-").compactMap { Int($0) }
    if parts.count == 2 {
        pages = Array((parts[0] - 1)..<min(parts[1], doc.pageCount))
    } else if parts.count == 1 {
        pages = [parts[0] - 1]
    }
}
for i in pages {
    guard let page = doc.page(at: i) else { continue }
    print("========== 第 \(i + 1) 页 ==========")
    print(page.string ?? "(无文本)")
}
