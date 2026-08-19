import Foundation

struct CurrentJob: Decodable, Equatable {
    let refId: String
    let textLen: Int
    let elapsedSec: Double
}

struct RecentJob: Decodable, Equatable, Identifiable {
    let refId: String
    let textLen: Int
    let ok: Bool
    let error: String?
    let durationSec: Double
    let finishedAt: String
    var id: String { finishedAt + refId }
}

struct Totals: Decodable, Equatable {
    let ok: Int
    let error: Int
}

struct ServerStatus: Decodable, Equatable {
    let server: String
    let uptimeSec: Int
    let queueLen: Int
    let currentJob: CurrentJob?
    let recent: [RecentJob]
    let totals: Totals
    let engine: String
    let modelResident: Bool
    let memoryMb: Int

    static func decode(from data: Data) throws -> ServerStatus {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(ServerStatus.self, from: data)
    }
}

struct RefEntry: Decodable, Identifiable {
    let refId: String
    let hasTxt: Bool
    var id: String { refId }
}

struct RefsResponse: Decodable {
    let refs: [RefEntry]

    static func decode(from data: Data) throws -> RefsResponse {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(RefsResponse.self, from: data)
    }
}
