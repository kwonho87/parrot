// macapp/Parrot/DashboardView.swift
import SwiftUI
import UniformTypeIdentifiers

struct DashboardView: View {
    @EnvironmentObject var server: ServerManager
    @EnvironmentObject var poller: StatusPoller
    @EnvironmentObject var settings: AppSettings
    @StateObject private var log = LogTailer()
    @State private var showingModelPicker = false

    // 최근 요청 테이블: 3행 정도만 보이고 내부 스크롤 (서버가 최근 20건 제공)
    private let recentTableHeight: CGFloat = 124

    // 로그 자동 스크롤 (수동 스크롤 시 자동 해제)
    @State private var autoScrollLog = false
    @State private var lastAutoScrollAt = Date.distantPast
    private let logViewportHeight: CGFloat = 200

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                statusCard
                modelSection
                if let s = poller.status {
                    queueSection(s)
                    recentSection(s)
                }
                refsSection
                logSection
            }
            .padding()
        }
        .task {
            log.start(path: settings.logPath)
            await poller.refreshRefs()
        }
        .onDisappear { log.stop() }
    }

    private var modelSection: some View {
        GroupBox("모델 폴더") {
            VStack(alignment: .leading, spacing: 6) {
                HStack {
                    Image(systemName: modelPathExists ? "checkmark.circle.fill" : "exclamationmark.triangle.fill")
                        .foregroundStyle(modelPathExists ? .green : .orange)
                    Text(settings.modelPath)
                        .font(.caption)
                        .lineLimit(1)
                        .truncationMode(.middle)
                        .textSelection(.enabled)
                    Spacer()
                    Button("폴더 선택…") { showingModelPicker = true }
                }
                if !modelPathExists {
                    Text("폴더가 없습니다. hf download로 모델을 받거나 다른 폴더를 지정해주세요.")
                        .font(.caption).foregroundStyle(.orange)
                }
                HStack {
                    Text("변경은 서버 재시작 후 반영됩니다.")
                        .font(.caption).foregroundStyle(.secondary)
                    if server.state == .attached {
                        Text("(외부 실행 서버는 tts.sh로 재시작)")
                            .font(.caption).foregroundStyle(.orange)
                    } else {
                        Button("서버 재시작") { Task { await server.restart() } }
                            .font(.caption)
                    }
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .fileImporter(isPresented: $showingModelPicker, allowedContentTypes: [.folder]) { result in
            if case .success(let url) = result {
                settings.modelPath = url.path
            }
        }
    }

    private var modelPathExists: Bool {
        var isDir: ObjCBool = false
        return FileManager.default.fileExists(atPath: settings.modelPath, isDirectory: &isDir) && isDir.boolValue
    }

    private var statusCard: some View {
        GroupBox("서버 상태") {
            if let s = poller.status {
                Grid(alignment: .leading, horizontalSpacing: 24) {
                    GridRow {
                        Text("Uptime"); Text(formatUptime(s.uptimeSec))
                        Text("메모리"); Text("\(s.memoryMb) MB")
                    }
                    GridRow {
                        Text("엔진"); Text(s.engine)
                        Text("모델"); Text(s.modelResident ? "상주 중" : "언로드됨")
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            } else {
                Text("서버에 연결할 수 없습니다.")
                    .foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
        }
    }

    private func queueSection(_ s: ServerStatus) -> some View {
        GroupBox("큐") {
            VStack(alignment: .leading) {
                if let job = s.currentJob {
                    Text("생성 중: \(job.refId) — 텍스트 \(job.textLen)자, \(Int(job.elapsedSec))초 경과")
                } else {
                    Text("현재 작업 없음").foregroundStyle(.secondary)
                }
                Text("대기 \(s.queueLen)건 · 누적 성공 \(s.totals.ok) / 실패 \(s.totals.error)")
                    .font(.caption).foregroundStyle(.secondary)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    private func recentSection(_ s: ServerStatus) -> some View {
        GroupBox("최근 요청 (최근 20건)") {
            if s.recent.isEmpty {
                Text("아직 처리한 요청이 없습니다.")
                    .foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity, minHeight: 60, alignment: .center)
            } else {
                Table(s.recent) {
                    TableColumn("ref_id") { Text($0.refId) }
                    TableColumn("결과") { Text($0.ok ? "성공" : ($0.error ?? "실패")) }
                    TableColumn("소요(초)") { Text(String(format: "%.1f", $0.durationSec)) }
                    TableColumn("완료 시각") { Text($0.finishedAt) }
                }
                .frame(height: recentTableHeight)  // 3행 정도 표시, 나머지는 내부 스크롤
            }
        }
    }

    private var refsSection: some View {
        GroupBox("레퍼런스 음원") {
            VStack(alignment: .leading) {
                if poller.refs.isEmpty {
                    Text(poller.reachable ? "레퍼런스 음원이 없습니다." : "서버 연결 대기 중…")
                        .font(.caption).foregroundStyle(.secondary)
                } else {
                    ForEach(poller.refs) { ref in
                        HStack {
                            Text(ref.refId)
                            if !ref.hasTxt {
                                Text("txt 없음").font(.caption).foregroundStyle(.red)
                            }
                        }
                    }
                }
                Button("새로고침") { Task { await poller.refreshRefs() } }
                    .font(.caption)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    private var logSection: some View {
        GroupBox {
            VStack(alignment: .leading, spacing: 6) {
                HStack {
                    Button {
                        autoScrollLog.toggle()
                    } label: {
                        Label("자동 스크롤", systemImage: "arrow.down.to.line")
                            .font(.caption)
                    }
                    .buttonStyle(.bordered)
                    .tint(autoScrollLog ? .accentColor : .secondary)
                    .help(autoScrollLog
                          ? "자동 스크롤 켜짐 — 클릭해서 끄기 (스크롤을 직접 움직여도 꺼집니다)"
                          : "클릭하면 로그가 항상 맨 아래로 스크롤됩니다")
                    Spacer()
                }
                ScrollViewReader { proxy in
                    ScrollView {
                        VStack(alignment: .leading, spacing: 0) {
                            Text(log.text)
                                .font(.system(.caption, design: .monospaced))
                                .frame(maxWidth: .infinity, alignment: .leading)
                                .textSelection(.enabled)
                            Color.clear
                                .frame(height: 1)
                                .id("logBottom")
                                .background(GeometryReader { geo in
                                    Color.clear.preference(
                                        key: LogBottomYKey.self,
                                        value: geo.frame(in: .named("logScroll")).maxY
                                    )
                                })
                        }
                    }
                    .coordinateSpace(name: "logScroll")
                    .frame(height: logViewportHeight)
                    .onPreferenceChange(LogBottomYKey.self) { bottomY in
                        let atBottom = bottomY <= logViewportHeight + 24
                        // 자동 스크롤 중인데 바닥에서 벗어났고, 방금 우리가 스크롤한 게 아니면
                        // → 사용자가 직접 움직인 것이므로 자동 스크롤 해제
                        if autoScrollLog && !atBottom
                            && Date().timeIntervalSince(lastAutoScrollAt) > 0.6 {
                            autoScrollLog = false
                        }
                    }
                    .onChange(of: log.text) { _, _ in
                        if autoScrollLog { scrollLogToBottom(proxy) }
                    }
                    .onChange(of: autoScrollLog) { _, enabled in
                        if enabled { scrollLogToBottom(proxy) }
                    }
                }
            }
        } label: {
            Text("로그 (logs/tts.log — 1시간 롤링, 7일 보관)")
        }
    }

    private func scrollLogToBottom(_ proxy: ScrollViewProxy) {
        lastAutoScrollAt = Date()
        proxy.scrollTo("logBottom", anchor: .bottom)
    }

    private func formatUptime(_ sec: Int) -> String {
        let h = sec / 3600, m = (sec % 3600) / 60
        return h > 0 ? "\(h)시간 \(m)분" : "\(m)분 \(sec % 60)초"
    }
}

/// 로그 하단 마커의 스크롤 뷰포트 기준 Y 좌표 (자동 스크롤 해제 감지용)
private struct LogBottomYKey: PreferenceKey {
    static var defaultValue: CGFloat = 0
    static func reduce(value: inout CGFloat, nextValue: () -> CGFloat) {
        value = nextValue()
    }
}
