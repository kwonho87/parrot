// macapp/Parrot/LoginItemToggle.swift
import SwiftUI
import ServiceManagement

struct LoginItemToggle: View {
    @State private var enabled = SMAppService.mainApp.status == .enabled

    var body: some View {
        Toggle("로그인 시 자동 시작", isOn: $enabled)
            .onChange(of: enabled) { _, newValue in
                do {
                    if newValue { try SMAppService.mainApp.register() }
                    else { try SMAppService.mainApp.unregister() }
                } catch {
                    enabled = SMAppService.mainApp.status == .enabled
                }
            }
    }
}
