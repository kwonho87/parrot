// macapp/Parrot/StatusPoller.swift
import Foundation

@MainActor
final class StatusPoller: ObservableObject {
    @Published private(set) var status: ServerStatus?
    @Published private(set) var reachable = false
    @Published private(set) var refs: [RefEntry] = []

    private let settings: AppSettings
    private var task: Task<Void, Never>?

    init(settings: AppSettings = .shared) {
        self.settings = settings
    }

    func start(interval: TimeInterval = 2.0) {
        stop()
        task = Task { [weak self] in
            while !Task.isCancelled {
                await self?.tick()
                try? await Task.sleep(for: .seconds(interval))
            }
        }
    }

    func stop() {
        task?.cancel()
        task = nil
    }

    private func tick() async {
        var request = URLRequest(url: settings.baseURL.appendingPathComponent("status"))
        // 긴 생성 작업으로 이벤트 루프가 밀릴 수 있어 타임아웃은 넉넉히
        request.timeoutInterval = 5
        do {
            let (data, _) = try await URLSession.shared.data(for: request)
            status = try ServerStatus.decode(from: data)
            let wasReachable = reachable
            reachable = true
            if !wasReachable {
                // 최초 연결/복구 시 refs 자동 갱신 (대시보드가 서버보다 먼저 열린 경우 포함)
                await refreshRefs()
            }
        } catch {
            reachable = false
            status = nil
        }
    }

    func refreshRefs() async {
        let url = settings.baseURL.appendingPathComponent("refs")
        guard let (data, _) = try? await URLSession.shared.data(from: url),
              let decoded = try? RefsResponse.decode(from: data) else { return }
        refs = decoded.refs
    }
}
