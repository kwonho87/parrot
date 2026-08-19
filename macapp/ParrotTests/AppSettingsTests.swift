import XCTest
@testable import Parrot

final class AppSettingsTests: XCTestCase {
    func testPortClamping() {
        let settings = AppSettings.shared
        let original = settings.port
        defer { settings.port = original }

        settings.port = -5
        XCTAssertEqual(settings.port, 1)
        settings.port = 99999
        XCTAssertEqual(settings.port, 65535)
        settings.port = 8010
        XCTAssertEqual(settings.port, 8010)
        XCTAssertEqual(settings.baseURL.absoluteString, "http://127.0.0.1:8010")
    }

    func testParrotEnvParsesDefaults() throws {
        let dir = NSTemporaryDirectory() + "parrot-env-test-\(UUID().uuidString)"
        try FileManager.default.createDirectory(atPath: dir, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(atPath: dir) }

        let content = """
        # setup.sh generated
        export TTS_PORT="${TTS_PORT:-9000}"
        export TTS_OUTPUT_DIR="${TTS_OUTPUT_DIR:-/tmp/out}"
        export TTS_HOST="${TTS_HOST:-0.0.0.0}"
        """
        try content.write(toFile: dir + "/.parrot.env", atomically: true, encoding: .utf8)

        let env = AppSettings.parrotEnv(repoDir: dir)
        XCTAssertEqual(env["TTS_PORT"], "9000")
        XCTAssertEqual(env["TTS_OUTPUT_DIR"], "/tmp/out")
        XCTAssertEqual(env["TTS_HOST"], "0.0.0.0")
    }

    func testParrotEnvMissingFileIsEmpty() {
        let env = AppSettings.parrotEnv(repoDir: "/no/such/dir")
        XCTAssertTrue(env.isEmpty)
    }

    func testEngineModeAcceptsWorkerApiCli() {
        let settings = AppSettings.shared
        let original = settings.engineMode
        defer { settings.engineMode = original }

        settings.engineMode = "worker"
        XCTAssertEqual(settings.engineMode, "worker")
        settings.engineMode = "api"
        XCTAssertEqual(settings.engineMode, "api")
        settings.engineMode = "cli"
        XCTAssertEqual(settings.engineMode, "cli")
        settings.engineMode = "garbage"
        XCTAssertEqual(settings.engineMode, "worker", "알 수 없는 값은 worker로 정규화")
    }
}
