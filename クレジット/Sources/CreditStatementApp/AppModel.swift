import CreditStatementCore
import Foundation

enum DashboardTab: String, CaseIterable, Identifiable {
    case summary = "集計"
    case details = "個別明細"
    case excluded = "削除済み"

    var id: String { rawValue }
}

struct AppAlert: Identifiable {
    let id = UUID()
    let title: String
    let message: String
}

enum ImportSaveOutcome {
    case saved
    case duplicate(existingMonth: String)
    case replacementRequired(existingCount: Int)
    case failed(String)
}

@MainActor
final class AppModel: ObservableObject {
    @Published private(set) var statements: [StatementMonth] = []
    @Published var selectedMonthID: String?
    @Published var selectedTab: DashboardTab = .summary
    @Published var isShowingFileImporter = false
    @Published var pendingImport: ImportResult?
    @Published var alert: AppAlert?
    @Published var isImporting = false

    private let repository: StatementRepository
    private let importer = CreditCSVImporter()

    init(repository: StatementRepository = StatementRepository()) {
        self.repository = repository
        do {
            statements = try repository.load().sorted { $0.month > $1.month }
            selectedMonthID = statements.first?.month
        } catch {
            statements = []
            alert = AppAlert(
                title: "保存データを読み込めませんでした",
                message: "データは変更していません。\n\(error.localizedDescription)"
            )
        }
    }

    var selectedStatement: StatementMonth? {
        guard let selectedMonthID else { return nil }
        return statements.first { $0.month == selectedMonthID }
    }

    func statement(for month: String) -> StatementMonth? {
        statements.first { $0.month == month }
    }

    func beginImport(from result: Result<[URL], Error>) {
        switch result {
        case .success(let urls):
            guard let url = urls.first else { return }
            isImporting = true
            let accessed = url.startAccessingSecurityScopedResource()
            defer {
                if accessed { url.stopAccessingSecurityScopedResource() }
                isImporting = false
            }

            do {
                guard url.pathExtension.lowercased() == "csv" else {
                    throw ImportPreparationError.unsupportedExtension
                }
                let data = try Data(contentsOf: url)
                guard data.count <= 10 * 1024 * 1024 else {
                    throw ImportPreparationError.fileTooLarge
                }
                let parsed = try importer.parse(data: data, fileName: url.lastPathComponent)
                guard parsed.entries.count <= 100_000 else {
                    throw ImportPreparationError.tooManyEntries
                }
                pendingImport = parsed
            } catch {
                alert = AppAlert(title: "CSVを読み込めませんでした", message: error.localizedDescription)
            }
        case .failure(let error):
            if (error as NSError).code != NSUserCancelledError {
                alert = AppAlert(title: "ファイルを選択できませんでした", message: error.localizedDescription)
            }
        }
    }

    func saveImport(_ result: ImportResult, targetMonth: String, replacing: Bool) -> ImportSaveOutcome {
        if let duplicate = statements.first(where: { $0.sourceHash == result.sourceHash }) {
            return .duplicate(existingMonth: duplicate.month)
        }

        let existingIndex = statements.firstIndex(where: { $0.month == targetMonth })
        if let existingIndex, !replacing {
            return .replacementRequired(existingCount: statements[existingIndex].entries.count)
        }

        let entries = result.entries.map {
            CreditEntry(
                id: $0.id,
                statementMonth: targetMonth,
                usageDate: $0.usageDate,
                user: $0.user,
                merchant: $0.merchant,
                amount: $0.amount,
                sourceRecordNumber: $0.sourceRecordNumber
            )
        }
        let statement = StatementMonth(
            month: targetMonth,
            sourceFileName: result.sourceFileName,
            sourceHash: result.sourceHash,
            importWarnings: result.warnings,
            entries: entries
        )

        let previous = statements
        if let existingIndex {
            statements[existingIndex] = statement
        } else {
            statements.append(statement)
        }
        statements.sort { $0.month > $1.month }

        do {
            try repository.save(statements)
            selectedMonthID = targetMonth
            selectedTab = .summary
            pendingImport = nil
            return .saved
        } catch {
            statements = previous
            return .failed(error.localizedDescription)
        }
    }

    func excludeEntries(_ ids: Set<UUID>, in month: String) {
        updateEntries(ids, in: month, status: .excluded)
    }

    func restoreEntries(_ ids: Set<UUID>, in month: String) {
        updateEntries(ids, in: month, status: .included)
    }

    private func updateEntries(_ ids: Set<UUID>, in month: String, status: EntryStatus) {
        guard !ids.isEmpty, let statementIndex = statements.firstIndex(where: { $0.month == month }) else { return }
        let previous = statements
        let operationDate = Date()
        for index in statements[statementIndex].entries.indices where ids.contains(statements[statementIndex].entries[index].id) {
            statements[statementIndex].entries[index].status = status
            statements[statementIndex].entries[index].excludedAt = status == .excluded ? operationDate : nil
        }

        do {
            try repository.save(statements)
        } catch {
            statements = previous
            alert = AppAlert(
                title: status == .excluded ? "明細を除外できませんでした" : "明細を復元できませんでした",
                message: "操作前の状態を維持しています。\n\(error.localizedDescription)"
            )
        }
    }

    func displayMonth(_ month: String) -> String {
        let parts = month.split(separator: "-")
        guard parts.count == 2, let monthNumber = Int(parts[1]) else { return month }
        return "\(parts[0])年\(monthNumber)月"
    }
}

private enum ImportPreparationError: LocalizedError {
    case unsupportedExtension
    case fileTooLarge
    case tooManyEntries

    var errorDescription: String? {
        switch self {
        case .unsupportedExtension:
            return "拡張子が.csvのファイルを選択してください。"
        case .fileTooLarge:
            return "10MB以下のCSVを選択してください。"
        case .tooManyEntries:
            return "明細数が10万件を超えています。"
        }
    }
}
