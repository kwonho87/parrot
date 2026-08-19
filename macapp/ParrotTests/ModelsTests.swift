import XCTest
@testable import Parrot

final class ModelsTests: XCTestCase {
    func testDecodeServerStatus() throws {
        let json = """
        {
          "server": "ok", "uptime_sec": 123, "queue_len": 2,
          "current_job": {"ref_id": "myvoice", "text_len": 42, "elapsed_sec": 3.1},
          "recent": [
            {"ref_id": "myvoice", "text_len": 10, "ok": true, "error": null,
             "duration_sec": 8.2, "finished_at": "2026-07-03T12:00:00"}
          ],
          "totals": {"ok": 120, "error": 3},
          "engine": "api", "model_resident": true, "memory_mb": 3100
        }
        """.data(using: .utf8)!
        let status = try ServerStatus.decode(from: json)
        XCTAssertEqual(status.queueLen, 2)
        XCTAssertEqual(status.currentJob?.refId, "myvoice")
        XCTAssertEqual(status.recent.first?.durationSec, 8.2)
        XCTAssertEqual(status.totals.ok, 120)
        XCTAssertTrue(status.modelResident)
        XCTAssertEqual(status.memoryMb, 3100)
    }

    func testDecodeWithNullCurrentJob() throws {
        let json = """
        {"server":"ok","uptime_sec":1,"queue_len":0,"current_job":null,
         "recent":[],"totals":{"ok":0,"error":0},
         "engine":"cli","model_resident":false,"memory_mb":80}
        """.data(using: .utf8)!
        let status = try ServerStatus.decode(from: json)
        XCTAssertNil(status.currentJob)
        XCTAssertTrue(status.recent.isEmpty)
    }
}
