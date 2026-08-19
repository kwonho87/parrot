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
