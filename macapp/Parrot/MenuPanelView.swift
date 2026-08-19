// macapp/Parrot/MenuPanelView.swift
import SwiftUI

struct MenuPanelView: View {
    @EnvironmentObject var server: ServerManager
    @EnvironmentObject var poller: StatusPoller
    @Environment(\.openWindow) private var openWindow

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Circle().fill(stateColor).frame(width: 10, height: 10)
                Text(stateLabel).font(.headline)
                Spacer()
            }

            if let s = poller.status {
                Group {
                    if let job = s.currentJob {
                        Text("생성 중: \(job.refId) (\(Int(job.elapsedSec))초 경과)")
                    } else {
                        Text("대기 중")
                    }
                    Text("큐 대기 \(s.queueLen)건 · 성공 \(s.totals.ok) · 실패 \(s.totals.error)")
                    Text("메모리 \(s.memoryMb)MB · 모델 \(s.modelResident ? "상주" : "언로드됨")")
                }
                .font(.caption)
                .foregroundStyle(.secondary)
            }

            if case .failed(let message) = server.state {
                Text(message).font(.caption).foregroundStyle(.red)
            }

            Divider()

            HStack {
                if server.state == .stopped || isFailed {
                    Button("서버 시작") { server.start() }
                } else if server.state != .attached {
                    Button("서버 중지") { server.stop() }
                } else {
                    Text("외부 실행 서버에 연결됨").font(.caption)
                }
                Spacer()
                Button("대시보드") {
                    openWindow(id: "dashboard")
                    NSApp.activate(ignoringOtherApps: true)
                }
            }

            Divider()
            LoginItemToggle()
            Button("종료") { NSApp.terminate(nil) }
        }
        .padding(12)
        .frame(width: 280)
    }

    private var isFailed: Bool {
        if case .failed = server.state { return true }
        return false
    }

    private var stateColor: Color {
        switch server.state {
        case .running, .attached: return poller.reachable ? .green : .orange
        case .starting: return .yellow
        case .stopped: return .gray
        case .failed: return .red
        }
    }

    private var stateLabel: String {
        switch server.state {
        case .running: return poller.reachable ? "실행 중" : "응답 없음"
        case .attached: return "연결됨 (외부 실행)"
        case .starting: return "시작 중…"
        case .stopped: return "중지됨"
        case .failed: return "오류"
        }
    }
}
