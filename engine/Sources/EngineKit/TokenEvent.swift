// 流式事件：增量文本流 + 工具调用事件 + 收尾统计（tok/s、峰值 RSS、pp_ts）
public enum TokenEvent {
    case token(String)
    case toolCall(ToolCallEvent)
    case stats(Stats)

    public struct Stats {
        public let tokensPerSecond: Double        // 解码速度（生成阶段）
        public let peakMemoryMB: Int              // 进程峰值常驻内存
        public let promptTokensPerSecond: Double  // 预填充速度（prompt 阶段）

        public init(tokensPerSecond: Double, peakMemoryMB: Int, promptTokensPerSecond: Double) {
            self.tokensPerSecond = tokensPerSecond
            self.peakMemoryMB = peakMemoryMB
            self.promptTokensPerSecond = promptTokensPerSecond
        }
    }
}
