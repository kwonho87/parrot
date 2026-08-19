// macapp/Parrot/ParrotApp.swift
import SwiftUI

@main
struct ParrotApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) var appDelegate
    @StateObject private var server = ServerManager()
    @StateObject private var poller = StatusPoller()
    @StateObject private var settings = AppSettings.shared

    var body: some Scene {
        MenuBarExtra {
            MenuPanelView()
                .environmentObject(server)
                .environmentObject(poller)
                .environmentObject(settings)
        } label: {
            Image(systemName: menuIcon)
                .task {
                    // 단위 테스트 호스트로 실행될 때는 서버를 스폰하지 않는다
                    guard ProcessInfo.processInfo.environment["XCTestConfigurationFilePath"] == nil else { return }
                    AppDelegate.serverManager = server
                    await server.startOrAttach()
                    poller.start()
                }
        }
        .menuBarExtraStyle(.window)

        Window("Parrot 대시보드", id: "dashboard") {
            DashboardView()
                .environmentObject(server)
                .environmentObject(poller)
                .environmentObject(settings)
        }
        .defaultSize(width: 640, height: 560)

        Settings {
            SettingsView()
                .environmentObject(settings)
                .environmentObject(server)
        }
    }

    private var menuIcon: String {
        switch server.state {
        case .failed: return "waveform.badge.exclamationmark"
        case .stopped: return "waveform.slash"
        default:
            if poller.status?.currentJob != nil { return "waveform.badge.mic" }
            return "waveform"
        }
    }
}
