// 生成请求：速度档四档全支持（M1 映射线程数；ngl/投机解码映射 M3 热控再做）
public struct GenerationRequest {
    public let messages: [Message]
    public let maxTokens: Int
    public let temperature: Double
    public let speed: SpeedTier
    /// 本次启用的工具白名单子集（nil=纯文本模式，M1 行为；[name...]=开启工具循环）
    public let tools: [String]?

    public init(messages: [Message], maxTokens: Int, temperature: Double, speed: SpeedTier = .balanced, tools: [String]? = nil) {
        self.messages = messages
        self.maxTokens = maxTokens
        self.temperature = temperature
        self.speed = speed
        self.tools = tools
    }
}
