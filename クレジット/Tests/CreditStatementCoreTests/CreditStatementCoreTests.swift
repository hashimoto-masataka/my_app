import XCTest
@testable import CreditStatementCore

final class CreditStatementCoreTests: XCTestCase {
    func testParsesStatementAndExcludesFooterSections() throws {
        let url = try XCTUnwrap(Bundle.module.url(
            forResource: "sample_statement",
            withExtension: "csv",
            subdirectory: "Fixtures"
        ))
        var data = Data([0xEF, 0xBB, 0xBF])
        data.append(try Data(contentsOf: url))

        let result = try CreditCSVImporter().parse(
            data: data,
            fileName: "statement_20260710.csv"
        )

        XCTAssertEqual(result.entries.count, 5)
        XCTAssertEqual(result.importedTotal, 730)
        XCTAssertEqual(result.suggestedMonth, "2026-07")
        XCTAssertTrue(result.warnings.isEmpty)

        let statement = makeStatement(from: result, month: "2026-07")
        XCTAssertEqual(statement.merchantSummaries.count, 4)
        XCTAssertEqual(statement.userTotals.map(\.amount).reduce(0, +), 730)
        XCTAssertEqual(statement.merchantSummaries.first(where: { $0.user == "利用者A" && $0.merchant == "店舗X" })?.amount, 300)
    }

    func testInvalidAmountIsReportedAsWarning() throws {
        let csv = """
        名前,利用店名,利用金額
        利用者A,店舗A,"1,000"
        利用者A,店舗B,不明
        """
        let result = try CreditCSVImporter().parse(data: Data(csv.utf8), fileName: "20260810.csv")
        XCTAssertEqual(result.entries.count, 1)
        XCTAssertEqual(result.entries[0].amount, 1_000)
        XCTAssertEqual(result.warnings.count, 1)
        XCTAssertEqual(result.warnings[0].recordNumber, 3)
    }

    func testQuotedCommaAndEscapedQuote() throws {
        let csv = """
        "名前","利用店名","利用金額"
        "利用者A","店名, \"\"特別\"\"","1,200"
        """
        let result = try CreditCSVImporter().parse(data: Data(csv.utf8), fileName: "20260810.csv")
        XCTAssertEqual(result.entries[0].merchant, "店名, \"特別\"")
        XCTAssertEqual(result.entries[0].amount, 1_200)
    }

    func testMalformedCSVFails() {
        let csv = "\"名前\",\"利用店名\",\"利用金額\"\n\"利用者A\",\"店舗A,\"100\""
        XCTAssertThrowsError(try CreditCSVImporter().parse(data: Data(csv.utf8), fileName: "bad.csv")) { error in
            XCTAssertEqual(error as? CSVImportError, .malformedCSV)
        }
    }

    func testRepositoryRoundTripAndExclusion() throws {
        let temporary = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: temporary) }
        let repository = StatementRepository(baseDirectory: temporary)
        var statement = StatementMonth(
            month: "2026-07",
            sourceFileName: "sample.csv",
            sourceHash: "abc",
            entries: [
                CreditEntry(statementMonth: "2026-07", usageDate: "2026/07/01", user: "利用者A", merchant: "店舗A", amount: 500, sourceRecordNumber: 2),
                CreditEntry(statementMonth: "2026-07", usageDate: "2026/07/02", user: "利用者A", merchant: "店舗A", amount: 300, sourceRecordNumber: 3)
            ]
        )
        statement.entries[0].status = .excluded
        statement.entries[0].excludedAt = Date()

        try repository.save([statement])
        let loaded = try repository.load()
        XCTAssertEqual(loaded.count, 1)
        XCTAssertEqual(loaded[0].entries.count, 2)
        XCTAssertEqual(loaded[0].entries.filter { $0.status == .excluded }.count, 1)
        XCTAssertEqual(loaded[0].currentTotal, 300)
        XCTAssertEqual(loaded[0].excludedTotal, 500)
        XCTAssertEqual(loaded[0].merchantSummaries.first?.amount, 300)
        XCTAssertEqual(loaded[0].userTotals.first?.amount, 300)
    }

    func testUserTotalRemainsVisibleAtZeroWhenAllEntriesAreExcluded() {
        var entry = CreditEntry(
            statementMonth: "2026-07",
            usageDate: "2026/07/01",
            user: "利用者A",
            merchant: "店舗A",
            amount: 500,
            sourceRecordNumber: 2
        )
        entry.status = .excluded
        let statement = StatementMonth(
            month: "2026-07",
            sourceFileName: "sample.csv",
            sourceHash: "zero-total",
            entries: [entry]
        )

        XCTAssertEqual(statement.userTotals.count, 1)
        XCTAssertEqual(statement.userTotals[0].user, "利用者A")
        XCTAssertEqual(statement.userTotals[0].amount, 0)
    }

    func testAttachedCSVWhenAvailable() throws {
        guard let path = ProcessInfo.processInfo.environment["CREDIT_TEST_CSV"] else {
            throw XCTSkip("CREDIT_TEST_CSV is not set")
        }
        let url = URL(fileURLWithPath: path)
        let result = try CreditCSVImporter().parse(data: Data(contentsOf: url), fileName: url.lastPathComponent)
        let statement = makeStatement(from: result, month: result.suggestedMonth)

        XCTAssertEqual(result.entries.count, 85)
        XCTAssertEqual(Set(result.entries.map(\.user)).count, 2)
        XCTAssertEqual(Set(result.entries.map(\.merchant)).count, 31)
        XCTAssertEqual(statement.merchantSummaries.count, 35)
        XCTAssertEqual(statement.userTotals.count, 2)
        XCTAssertEqual(statement.currentTotal, result.importedTotal)
    }

    private func makeStatement(from result: ImportResult, month: String) -> StatementMonth {
        StatementMonth(
            month: month,
            sourceFileName: result.sourceFileName,
            sourceHash: result.sourceHash,
            importWarnings: result.warnings,
            entries: result.entries.map {
                CreditEntry(
                    id: $0.id,
                    statementMonth: month,
                    usageDate: $0.usageDate,
                    user: $0.user,
                    merchant: $0.merchant,
                    amount: $0.amount,
                    sourceRecordNumber: $0.sourceRecordNumber
                )
            }
        )
    }
}
