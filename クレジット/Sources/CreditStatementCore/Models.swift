import Foundation

public enum EntryStatus: String, Codable, Hashable {
    case included
    case excluded
}

public struct CreditEntry: Identifiable, Codable, Hashable {
    public let id: UUID
    public let statementMonth: String
    public let usageDate: String
    public let user: String
    public let merchant: String
    public let amount: Int64
    public let sourceRecordNumber: Int
    public var status: EntryStatus
    public var excludedAt: Date?

    public init(
        id: UUID = UUID(),
        statementMonth: String,
        usageDate: String,
        user: String,
        merchant: String,
        amount: Int64,
        sourceRecordNumber: Int,
        status: EntryStatus = .included,
        excludedAt: Date? = nil
    ) {
        self.id = id
        self.statementMonth = statementMonth
        self.usageDate = usageDate
        self.user = user
        self.merchant = merchant
        self.amount = amount
        self.sourceRecordNumber = sourceRecordNumber
        self.status = status
        self.excludedAt = excludedAt
    }
}

public struct ImportWarning: Identifiable, Codable, Hashable {
    public var id: String { "\(recordNumber):\(message)" }
    public let recordNumber: Int
    public let message: String

    public init(recordNumber: Int, message: String) {
        self.recordNumber = recordNumber
        self.message = message
    }
}

public struct StatementMonth: Identifiable, Codable, Hashable {
    public var id: String { month }
    public let month: String
    public let sourceFileName: String
    public let sourceHash: String
    public let importedAt: Date
    public let importWarnings: [ImportWarning]
    public var entries: [CreditEntry]

    public init(
        month: String,
        sourceFileName: String,
        sourceHash: String,
        importedAt: Date = Date(),
        importWarnings: [ImportWarning] = [],
        entries: [CreditEntry]
    ) {
        self.month = month
        self.sourceFileName = sourceFileName
        self.sourceHash = sourceHash
        self.importedAt = importedAt
        self.importWarnings = importWarnings
        self.entries = entries
    }

    public var includedEntries: [CreditEntry] {
        entries.filter { $0.status == .included }
    }

    public var excludedEntries: [CreditEntry] {
        entries.filter { $0.status == .excluded }
    }

    public var importedTotal: Int64 {
        entries.reduce(0) { $0 + $1.amount }
    }

    public var currentTotal: Int64 {
        includedEntries.reduce(0) { $0 + $1.amount }
    }

    public var excludedTotal: Int64 {
        excludedEntries.reduce(0) { $0 + $1.amount }
    }

    public var merchantSummaries: [MerchantSummary] {
        var grouped: [MerchantKey: Int64] = [:]
        for entry in includedEntries {
            let key = MerchantKey(user: entry.user, merchant: entry.merchant)
            grouped[key, default: 0] += entry.amount
        }

        return grouped.map {
            MerchantSummary(user: $0.key.user, merchant: $0.key.merchant, amount: $0.value)
        }
        .sorted {
            let userOrder = $0.user.localizedStandardCompare($1.user)
            if userOrder != .orderedSame { return userOrder == .orderedAscending }
            if $0.amount != $1.amount { return $0.amount > $1.amount }
            return $0.merchant.localizedStandardCompare($1.merchant) == .orderedAscending
        }
    }

    public var userTotals: [UserTotal] {
        var totals: [String: Int64] = [:]
        for entry in entries {
            totals[entry.user] = totals[entry.user] ?? 0
        }
        for entry in includedEntries {
            totals[entry.user, default: 0] += entry.amount
        }
        return totals.map { UserTotal(user: $0.key, amount: $0.value) }
            .sorted { $0.user.localizedStandardCompare($1.user) == .orderedAscending }
    }
}

private struct MerchantKey: Hashable {
    let user: String
    let merchant: String
}

public struct MerchantSummary: Identifiable, Hashable {
    public var id: String { "\(user)\u{1F}\(merchant)" }
    public let user: String
    public let merchant: String
    public let amount: Int64

    public init(user: String, merchant: String, amount: Int64) {
        self.user = user
        self.merchant = merchant
        self.amount = amount
    }
}

public struct UserTotal: Identifiable, Hashable {
    public var id: String { user }
    public let user: String
    public let amount: Int64

    public init(user: String, amount: Int64) {
        self.user = user
        self.amount = amount
    }
}

public struct ImportResult: Identifiable, Hashable {
    public var id: String { sourceHash }
    public let sourceFileName: String
    public let sourceHash: String
    public let suggestedMonth: String
    public let entries: [ImportedEntry]
    public let warnings: [ImportWarning]
    public let importedTotal: Int64

    public init(
        sourceFileName: String,
        sourceHash: String,
        suggestedMonth: String,
        entries: [ImportedEntry],
        warnings: [ImportWarning],
        importedTotal: Int64
    ) {
        self.sourceFileName = sourceFileName
        self.sourceHash = sourceHash
        self.suggestedMonth = suggestedMonth
        self.entries = entries
        self.warnings = warnings
        self.importedTotal = importedTotal
    }
}

public struct ImportedEntry: Identifiable, Hashable {
    public let id: UUID
    public let usageDate: String
    public let user: String
    public let merchant: String
    public let amount: Int64
    public let sourceRecordNumber: Int

    public init(
        id: UUID = UUID(),
        usageDate: String,
        user: String,
        merchant: String,
        amount: Int64,
        sourceRecordNumber: Int
    ) {
        self.id = id
        self.usageDate = usageDate
        self.user = user
        self.merchant = merchant
        self.amount = amount
        self.sourceRecordNumber = sourceRecordNumber
    }
}

public enum MoneyText {
    private static let formatter: NumberFormatter = {
        let formatter = NumberFormatter()
        formatter.locale = Locale(identifier: "ja_JP")
        formatter.numberStyle = .decimal
        formatter.maximumFractionDigits = 0
        return formatter
    }()

    public static func format(_ amount: Int64) -> String {
        let value = formatter.string(from: NSNumber(value: amount)) ?? String(amount)
        return "\(value)円"
    }
}
