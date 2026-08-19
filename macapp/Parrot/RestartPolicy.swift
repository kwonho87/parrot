import Foundation

/// 서버 크래시 시 재시작 백오프와 crash loop 중단을 결정하는 순수 로직.
struct RestartPolicy {
    private(set) var consecutiveFailures = 0
    private let delays: [TimeInterval] = [1, 5, 15]
    private var maxFailures: Int { delays.count }
    private let stableInterval: TimeInterval = 60

    /// 크래시 발생 기록. 재시작까지 기다릴 초를 반환하고, 포기해야 하면 nil.
    mutating func recordCrash(uptime: TimeInterval) -> TimeInterval? {
        if uptime >= stableInterval { consecutiveFailures = 0 }
        consecutiveFailures += 1
        guard consecutiveFailures <= maxFailures else { return nil }
        return delays[consecutiveFailures - 1]
    }

    mutating func reset() { consecutiveFailures = 0 }
}
