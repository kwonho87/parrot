import XCTest
@testable import Parrot

final class LogTailerTests: XCTestCase {
    @MainActor
    func testTailSurvivesMultibyteBoundary() async throws {
        // 8KB 초과 한글 로그 파일: 임의 오프셋이 한글 중간에 떨어지는 상황 재현
        let dir = FileManager.default.temporaryDirectory
        let path = dir.appendingPathComponent("tailtest-\(UUID().uuidString).log").path
        let line = "한글로그라인 가나다라마바사아자차카타파하\n"
        var content = ""
        while content.utf8.count < 20 * 1024 { content += line }
        try content.write(toFile: path, atomically: true, encoding: .utf8)
        defer { try? FileManager.default.removeItem(atPath: path) }

        let tailer = LogTailer()
        tailer.start(path: path, interval: 60)   // 첫 read만 사용
        try await Task.sleep(for: .milliseconds(200))
        tailer.stop()

        XCTAssertFalse(tailer.text.isEmpty, "잘린 UTF-8 경계에서 로그가 비면 안 된다")
        XCTAssertFalse(tailer.text.contains("\u{FFFD}"), "첫 줄 드랍으로 대체문자 없이 깨끗해야 한다")
        XCTAssertTrue(tailer.text.hasSuffix(line) || tailer.text.hasSuffix(line.trimmingCharacters(in: .newlines)), "마지막 줄이 온전해야 한다")
    }
}
