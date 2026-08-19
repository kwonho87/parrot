// macapp/Parrot/AppSettings.swift
import Foundation

final class AppSettings: ObservableObject {
    static let shared = AppSettings()

    @Published var repoDir: String {
        didSet { UserDefaults.standard.set(repoDir, forKey: "repoDir") }
    }
    @Published var refsDir: String {
        didSet { UserDefaults.standard.set(refsDir, forKey: "refsDir") }
    }
    @Published var modelPath: String {
        didSet { UserDefaults.standard.set(modelPath, forKey: "modelPath") }
    }
    @Published var port: Int {
        didSet {
            let clamped = min(max(port, 1), 65535)
            if clamped != port { port = clamped; return }
            UserDefaults.standard.set(port, forKey: "port")
        }
    }
    @Published var modelTTLSec: Int {
        didSet { UserDefaults.standard.set(modelTTLSec, forKey: "modelTTLSec") }
    }
    @Published var keepServerOnQuit: Bool {
        didSet { UserDefaults.standard.set(keepServerOnQuit, forKey: "keepServerOnQuit") }
    }
    /// "worker"(격리 자식 프로세스에 모델 상주, 빠르면서도 크래시 격리 — 기본값),
    /// "api"(모델 상주, 빠름) 또는 "cli"(요청마다 별도 프로세스, MLX/GPU 크래시가 나도
    /// 그 요청만 실패하고 서버 본체는 유지됨)
    @Published var engineMode: String {
        didSet {
            let allowed = ["worker", "api", "cli"]
            let normalized = allowed.contains(engineMode) ? engineMode : "worker"
            if normalized != engineMode { engineMode = normalized; return }
            UserDefaults.standard.set(engineMode, forKey: "engineMode")
        }
    }

    var venvPython: String { repoDir + "/.venv/bin/python" }
    /// 서버가 직접 쓰는 롤링 로그 (1시간 회전, 7일 보관) — 대시보드가 tail
    var logPath: String { repoDir + "/logs/tts.log" }
    /// stdout/stderr 안전망 (크래시 등 로깅 시스템 밖 출력) — 프로세스 리다이렉트용
    var crashLogPath: String { repoDir + "/tts.log" }
    var baseURL: URL {
        URL(string: "http://127.0.0.1:\(port)") ?? URL(string: "http://127.0.0.1:8010")!
    }

    static func detectRepoDir() -> String {
        // 앱이 저장소 안({repo}/macapp/dist/Parrot.app)에서 실행 중이면 그 저장소를 최우선.
        // /Applications 등으로 복사된 경우에는 후보 목록으로 폴백.
        // 앱이 저장소 안({repo}/macapp/dist/Parrot.app)에서 실행되면 그 저장소를 사용.
        // /Applications 등으로 복사된 경우엔 설정 화면에서 저장소 경로를 직접 지정한다.
        let bundleRepo = URL(fileURLWithPath: Bundle.main.bundlePath)
            .deletingLastPathComponent()   // dist
            .deletingLastPathComponent()   // macapp
            .deletingLastPathComponent()   // repo
            .path
        return bundleRepo
    }

    static func detectRefsDir(repoDir: String) -> String {
        // 저장소 refs/를 기본으로 사용. 외부 폴더는 설정 화면에서 지정한다.
        return repoDir + "/refs"
    }

    private init() {
        let d = UserDefaults.standard
        let repo = d.string(forKey: "repoDir") ?? Self.detectRepoDir()
        repoDir = repo
        refsDir = d.string(forKey: "refsDir") ?? Self.detectRefsDir(repoDir: repo)
        modelPath = d.string(forKey: "modelPath") ?? repo + "/fishaudio-s2-pro-8bit-mlx"
        let storedPort = d.object(forKey: "port") as? Int ?? 8010
        port = min(max(storedPort, 1), 65535)
        modelTTLSec = d.object(forKey: "modelTTLSec") as? Int ?? 600
        keepServerOnQuit = d.object(forKey: "keepServerOnQuit") as? Bool ?? false
        // 격리 워커(worker)를 기본값으로 — 모델 상주 속도 + 크래시 격리.
        let storedEngine = d.string(forKey: "engineMode") ?? "worker"
        engineMode = ["worker", "api", "cli"].contains(storedEngine) ? storedEngine : "worker"
    }

    /// venv/모델 경로 유효성 검사. 문제 없으면 nil, 있으면 안내 문구 반환.
    func validationError() -> String? {
        if !FileManager.default.isExecutableFile(atPath: venvPython) {
            return "venv를 찾을 수 없습니다: \(venvPython)\nREADME의 최초 세팅 절차를 진행해주세요."
        }
        if !FileManager.default.fileExists(atPath: modelPath) {
            return "모델 폴더가 없습니다: \(modelPath)\nhf download로 모델을 받아주세요."
        }
        return nil
    }
}
