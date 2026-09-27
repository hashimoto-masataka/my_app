import Foundation

public final class StatementRepository {
    private let fileManager: FileManager
    public let fileURL: URL

    public init(baseDirectory: URL? = nil, fileManager: FileManager = .default) {
        self.fileManager = fileManager
        if let baseDirectory {
            self.fileURL = baseDirectory.appendingPathComponent("statements.json")
        } else {
            let applicationSupport = fileManager.urls(for: .applicationSupportDirectory, in: .userDomainMask).first!
            self.fileURL = applicationSupport
                .appendingPathComponent("CreditStatementApp", isDirectory: true)
                .appendingPathComponent("statements.json")
        }
    }

    public func load() throws -> [StatementMonth] {
        guard fileManager.fileExists(atPath: fileURL.path) else { return [] }
        let data = try Data(contentsOf: fileURL)
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        return try decoder.decode([StatementMonth].self, from: data)
    }

    public func save(_ statements: [StatementMonth]) throws {
        let directory = fileURL.deletingLastPathComponent()
        try fileManager.createDirectory(at: directory, withIntermediateDirectories: true)
        let encoder = JSONEncoder()
        encoder.dateEncodingStrategy = .iso8601
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        let data = try encoder.encode(statements)
        try data.write(to: fileURL, options: .atomic)
    }
}
