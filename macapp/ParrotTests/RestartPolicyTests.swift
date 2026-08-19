import XCTest
@testable import Parrot

final class RestartPolicyTests: XCTestCase {
    func testBackoffDelaysThenGiveUp() {
        var policy = RestartPolicy()
        XCTAssertEqual(policy.recordCrash(uptime: 2), 1)   // 1번째 크래시 → 1초
        XCTAssertEqual(policy.recordCrash(uptime: 2), 5)   // 2번째 → 5초
        XCTAssertEqual(policy.recordCrash(uptime: 2), 15)  // 3번째 → 15초
        XCTAssertNil(policy.recordCrash(uptime: 2))        // 4번째 → 포기
    }

    func testStableRunResetsCounter() {
        var policy = RestartPolicy()
        _ = policy.recordCrash(uptime: 2)
        _ = policy.recordCrash(uptime: 2)
        // 60초 이상 안정 구동 후 크래시 → 카운터 리셋되어 1초부터
        XCTAssertEqual(policy.recordCrash(uptime: 120), 1)
    }

    func testManualResetClears() {
        var policy = RestartPolicy()
        _ = policy.recordCrash(uptime: 2)
        policy.reset()
        XCTAssertEqual(policy.recordCrash(uptime: 2), 1)
    }
}
