// macapp/Parrot/AppDelegate.swift
import AppKit

final class AppDelegate: NSObject, NSApplicationDelegate {
    static weak var serverManager: ServerManager?

    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
        // attach 모드이거나 "서버 유지" 설정이면 그대로 종료
        if AppSettings.shared.keepServerOnQuit { return .terminateNow }
        guard let manager = Self.serverManager, manager.isManagedProcess else {
            return .terminateNow
        }
        Task { @MainActor in
            manager.stop()
            try? await Task.sleep(for: .seconds(1))
            NSApp.reply(toApplicationShouldTerminate: true)
        }
        return .terminateLater
    }
}
