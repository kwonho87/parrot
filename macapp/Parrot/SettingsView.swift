// macapp/Parrot/SettingsView.swift
import SwiftUI

struct SettingsView: View {
    @EnvironmentObject var settings: AppSettings
    @EnvironmentObject var server: ServerManager

    var body: some View {
        Form {
            Section("경로") {
                TextField("저장소 경로 (server.py 위치)", text: $settings.repoDir)
                TextField("refs 폴더", text: $settings.refsDir)
                TextField("모델 폴더", text: $settings.modelPath)
            }
            Section("서버") {
                TextField("포트", value: $settings.port, format: .number)
                Picker("생성 엔진", selection: $settings.engineMode) {
                    Text("worker (권장)").tag("worker")
                    Text("api (in-process 상주)").tag("api")
                    Text("cli (요청마다 프로세스)").tag("cli")
                }
                .pickerStyle(.segmented)
                Text(engineHelp)
                    .font(.caption).foregroundStyle(.secondary)
                TextField("모델 idle TTL (초, worker·api)", value: $settings.modelTTLSec, format: .number)
                Toggle("앱 종료 시 서버 유지", isOn: $settings.keepServerOnQuit)
            }
            Section {
                Text("경로/포트 변경은 서버 재시작 후 반영됩니다.")
                    .font(.caption).foregroundStyle(.secondary)
                if server.state == .attached {
                    Text("외부에서 실행된 서버는 앱에서 재시작할 수 없습니다. tts.sh로 재시작해주세요.")
                        .font(.caption).foregroundStyle(.orange)
                } else {
                    Button("서버 재시작") {
                        Task { await server.restart() }
                    }
                }
            }
        }
        .formStyle(.grouped)
        .frame(width: 480)
        .padding()
    }

    private var engineHelp: String {
        switch settings.engineMode {
        case "api":
            return "모델을 서버 프로세스에 상주시킵니다. 빠르지만 GPU/MLX 크래시 시 서버 전체가 재시작됩니다."
        case "cli":
            return "요청마다 별도 프로세스에서 생성합니다. 가장 안정적이지만 매번 모델을 다시 로드해 느립니다."
        default:  // worker
            return "모델을 격리된 자식 프로세스에 상주시킵니다. 빠르면서도 GPU/MLX 크래시가 나면 그 요청만 실패하고 서버는 유지됩니다."
        }
    }
}
