import Testing
import Foundation
@testable import EngineKit

// M1.1 冒烟：真实模型走通「加载 → 分词 → 解码 → 采样 → 卸载」全链路
// 模型路径经环境变量 ENGINEKIT_TEST_MODEL 注入（gate.sh 在本机训练产物存在时自动设置）；
// 该版本 swift-testing 无 Skip 类型，改用 .enabled(if:) 条件跳过
@Suite("CLLaMA 桥接冒烟")
struct CLLaMASmokeTests {

    private static var hasModel: Bool {
        guard let path = ProcessInfo.processInfo.environment["ENGINEKIT_TEST_MODEL"] else { return false }
        return FileManager.default.fileExists(atPath: path)
    }

    static var hasModelEnabled: Bool { hasModel }

    @Test("加载模型 → 生成 1 token → 卸载不崩", .enabled(if: hasModel))
    func generateOneToken() throws {
        let path = ProcessInfo.processInfo.environment["ENGINEKIT_TEST_MODEL"]!

        CLLaMABackend.ensureInitialized()
        // 局部变量析构顺序与声明顺序相反：sampler → ctx → model，满足 llama.cpp 释放次序
        let model = try ModelHandle.load(fileURL: URL(fileURLWithPath: path), nGPU: -1)
        let ctx = try model.makeContext(context: 512, batch: 512, threads: 2, threadsBatch: 2)
        // 温度 0 = 贪心采样：同模型同机器结果确定，可做强断言
        let sampler = try SamplerHandle.chain(temperature: 0, seed: 42)

        let prompt = try model.tokenize("你好")
        #expect(!prompt.isEmpty, "tokenize 结果不应为空")
        try ctx.decode(tokens: prompt)

        let token = sampler.sample(ctx)
        // LLAMA_TOKEN_NULL == -1，桥接层不导出 C 常量，直接判负
        #expect(token >= 0, "采样应返回有效 token")
        if !model.isEog(token) {
            #expect(!model.piece(token).isEmpty, "贪心采样 token 应还原出可见文本")
        }
    }
}
