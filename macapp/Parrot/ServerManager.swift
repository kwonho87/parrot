// macapp/Parrot/ServerManager.swift
import Foundation

@MainActor
final class ServerManager: ObservableObject {
    enum State: Equatable {
        case stopped
        case starting
        case running        // 앱이 띄운 서버
        case attached       // 외부(tts.sh 등)에서 띄운 서버에 attach
        case failed(String)
    }

    @Published private(set) var state: State = .stopped

    private let settings: AppSettings
    private var process: Process?
    private var policy = RestartPolicy()
    private var launchedAt: Date?
    private var intentionalStop = false

    init(settings: AppSettings = .shared) {
        self.settings = settings
    }

    var isManagedProcess: Bool { process != nil }

    /// 앱 시작 시 호출: 포트에 이미 서버가 있으면 attach, 없으면 기동.
    func startOrAttach() async {
        if await Self.isHealthy(baseURL: settings.baseURL) {
            state = .attached
            return
        }
        if let error = settings.validationError() {
            state = .failed(error)
            return
        }
        launch()
    }

    func start() {
        guard state == .stopped || isFailed else { return }
        if let error = settings.validationError() {
            state = .failed(error)
            return
        }
        policy.reset()
        intentionalStop = false
        launch()
    }

    func stop() {
        guard let p = process else {
            // 크래시 백오프 대기 중이면 재시작 예약을 취소
            if state == .starting { state = .stopped }
            return
        }
        intentionalStop = true
        p.terminate()  // SIGTERM
        DispatchQueue.global().asyncAfter(deadline: .now() + 5) { [weak p] in
            if let p, p.isRunning { kill(p.processIdentifier, SIGKILL) }
        }
    }

    /// 관리 중인 서버를 재시작한다. 종료 완료를 기다린 뒤 시작하므로
    /// 고정 sleep 기반 재시작의 레이스(종료 전 start 무시)가 없다.
    func restart() async {
        guard state != .attached else { return }  // 외부 서버는 재시작 대상 아님
        stop()
        // stop()의 SIGKILL 유예(5초)보다 넉넉히 대기 (최대 8초)
        for _ in 0..<80 {
            if state == .stopped || isFailed { break }
            try? await Task.sleep(for: .milliseconds(100))
        }
        start()
    }

    private var isFailed: Bool {
        if case .failed = state { return true }
        return false
    }

    private func launch() {
        state = .starting
        let p = Process()
        p.executableURL = URL(fileURLWithPath: settings.venvPython)
        p.arguments = [
            "-m", "uvicorn", "server:app",
            "--host", "0.0.0.0",
            "--port", String(settings.port),
            "--app-dir", settings.repoDir,
        ]
        var env = ProcessInfo.processInfo.environment
        // GUI 앱은 Homebrew PATH를 상속받지 못한다 — ffmpeg 등 외부 도구 탐색용으로 보강
        env["PATH"] = "/opt/homebrew/bin:/usr/local/bin:" + (env["PATH"] ?? "/usr/bin:/bin")
        env["TTS_REFS_DIR"] = settings.refsDir
        env["FISH_S2_MODEL_PATH"] = settings.modelPath
        env["TTS_MODEL_TTL_SEC"] = String(settings.modelTTLSec)
        env["TTS_TEMP_DIR"] = "/tmp/fish_tts_temp"
        env["TTS_ENGINE"] = settings.engineMode
        p.environment = env

        let fd = open(settings.crashLogPath, O_WRONLY | O_CREAT | O_APPEND, 0o644)
        if fd >= 0 {
            // Process가 이 핸들을 자기 수명 동안 retain한다 (누수 아님)
            let log = FileHandle(fileDescriptor: fd, closeOnDealloc: true)
            p.standardOutput = log
            p.standardError = log
        }
        p.terminationHandler = { [weak self] proc in
            Task { @MainActor in self?.handleTermination(proc) }
        }
        do {
            try p.run()
            process = p
            launchedAt = Date()
            state = .running
        } catch {
            process = nil
            state = .failed("서버 실행 실패: \(error.localizedDescription)")
        }
    }

    private func handleTermination(_ proc: Process) {
        process = nil
        if intentionalStop {
            intentionalStop = false
            state = .stopped
            return
        }
        let uptime = launchedAt.map { Date().timeIntervalSince($0) } ?? 0
        if let delay = policy.recordCrash(uptime: uptime) {
            state = .starting
            Task { [weak self] in
                try? await Task.sleep(for: .seconds(delay))
                guard let self, self.state == .starting else { return }
                self.launch()
            }
        } else {
            state = .failed("서버가 반복 종료되어 재시작을 중단했습니다. 로그를 확인해주세요: \(settings.logPath) 및 \(settings.crashLogPath)")
        }
    }

    static func isHealthy(baseURL: URL, timeout: TimeInterval = 1.5) async -> Bool {
        var request = URLRequest(url: baseURL.appendingPathComponent("health"))
        request.timeoutInterval = timeout
        guard let (_, response) = try? await URLSession.shared.data(for: request),
              let http = response as? HTTPURLResponse else { return false }
        return http.statusCode == 200
    }
}
