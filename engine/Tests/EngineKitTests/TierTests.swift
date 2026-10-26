import Testing
@testable import EngineKit

@Suite struct TierTests {
    // 速度档位必须恒为四档——契约冻结，改档数属破坏性变更
    @Test func speedTierHasFourCases() {
        #expect(SpeedTier.allCases.count == 4)
    }

    @Test func memoryTierOrder() {
        #expect(MemoryTier.allCases == [.low, .standard, .high])
    }
}
