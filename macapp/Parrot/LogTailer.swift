// macapp/Parrot/LogTailer.swift
import Foundation

@MainActor
final class LogTailer: ObservableObject {
    @Published private(set) var text = ""
    private var task: Task<Void, Never>?
    private let maxBytes = 8 * 1024

    func start(path: String, interval: TimeInterval = 2.0) {
        stop()
        task = Task { [weak self] in
            while !Task.isCancelled {
                self?.read(path: path)
                try? await Task.sleep(for: .seconds(interval))
            }
        }
    }

    func stop() { task?.cancel(); task = nil }

    private func read(path: String) {
        guard let handle = FileHandle(forReadingAtPath: path) else {
            text = "(로그 파일 없음: \(path))"
            return
        }
        defer { try? handle.close() }
        let size = handle.seekToEndOfFile()
        let offset = size > UInt64(maxBytes) ? size - UInt64(maxBytes) : 0
        handle.seek(toFileOffset: offset)
        var data = handle.readDataToEndOfFile()
        // 중간부터 읽었으면 잘린 첫 줄(멀티바이트 경계 포함)을 버린다
        if offset > 0, let nl = data.firstIndex(of: UInt8(ascii: "\n")) {
            data = data[data.index(after: nl)...]
        }
        // 유효하지 않은 UTF-8 시퀀스는 U+FFFD로 대체 — 절대 빈 화면이 되지 않는다
        text = String(decoding: data, as: UTF8.self)
    }
}
