import CryptoKit
import Foundation

public enum CSVImportError: LocalizedError, Equatable {
    case unsupportedEncoding
    case malformedCSV
    case requiredColumnsMissing([String])
    case duplicateRequiredColumn(String)
    case noValidEntries
    case amountOutOfRange(recordNumber: Int)
    case totalOutOfRange

    public var errorDescription: String? {
        switch self {
        case .unsupportedEncoding:
            return "UTF-8形式のCSVを選択してください。"
        case .malformedCSV:
            return "CSVの引用符または改行形式が正しくありません。"
        case .requiredColumnsMissing(let columns):
            return "必須列がありません: \(columns.joined(separator: "、"))"
        case .duplicateRequiredColumn(let column):
            return "必須列「\(column)」が複数あり、一意に特定できません。"
        case .noValidEntries:
            return "集計できる利用明細が見つかりませんでした。"
        case .amountOutOfRange(let recordNumber):
            return "レコード\(recordNumber)の金額が対応範囲を超えています。"
        case .totalOutOfRange:
            return "集計金額が対応範囲を超えています。"
        }
    }
}

public struct CreditCSVImporter {
    public static let maximumSafeAmount: Int64 = 9_007_199_254_740_991

    public init() {}

    public func parse(data: Data, fileName: String) throws -> ImportResult {
        guard var text = String(data: data, encoding: .utf8) else {
            throw CSVImportError.unsupportedEncoding
        }
        if text.unicodeScalars.first?.value == 0xFEFF {
            text.removeFirst()
        }

        let rows = try CSVReader.parse(text)
        let required = ["名前", "利用店名", "利用金額"]
        guard let headerPosition = rows.firstIndex(where: { row in
            let normalized = row.fields.map(cleanField)
            return required.allSatisfy(normalized.contains)
        }) else {
            throw CSVImportError.requiredColumnsMissing(required)
        }

        let header = rows[headerPosition].fields.map(cleanField)
        var indices: [String: Int] = [:]
        for column in required {
            let matches = header.indices.filter { header[$0] == column }
            if matches.count > 1 { throw CSVImportError.duplicateRequiredColumn(column) }
            guard let index = matches.first else {
                throw CSVImportError.requiredColumnsMissing([column])
            }
            indices[column] = index
        }
        let dateIndex = header.firstIndex(of: "ご利用年月日")

        let nameIndex = indices["名前"]!
        let merchantIndex = indices["利用店名"]!
        let amountIndex = indices["利用金額"]!
        var imported: [ImportedEntry] = []
        var warnings: [ImportWarning] = []
        var started = false
        var total: Int64 = 0
        var absoluteTotal: Int64 = 0

        for row in rows.dropFirst(headerPosition + 1) {
            let values = row.fields.map(cleanField)
            if values.allSatisfy(\.isEmpty) { continue }

            if isOtherSectionTitle(values) { break }

            let name = field(values, at: nameIndex)
            let merchant = field(values, at: merchantIndex)
            let amountText = field(values, at: amountIndex)
            let usageDate = dateIndex.map { field(values, at: $0) } ?? ""

            let isFooter = started
                && name.isEmpty
                && merchant.isEmpty
                && (dateIndex == nil || usageDate.isEmpty)
                && values.contains(where: { !$0.isEmpty })
            if isFooter { break }

            if name.isEmpty || merchant.isEmpty || amountText.isEmpty {
                if !name.isEmpty || !merchant.isEmpty || !amountText.isEmpty {
                    var missing: [String] = []
                    if name.isEmpty { missing.append("利用者") }
                    if merchant.isEmpty { missing.append("利用店名") }
                    if amountText.isEmpty { missing.append("利用金額") }
                    warnings.append(ImportWarning(
                        recordNumber: row.number,
                        message: "\(missing.joined(separator: "・"))が空欄のため除外しました。"
                    ))
                }
                continue
            }

            switch parseAmount(amountText) {
            case .success(let amount):
                let (newTotal, overflow) = total.addingReportingOverflow(amount)
                let magnitude = amount < 0 ? -amount : amount
                let (newAbsoluteTotal, absoluteOverflow) = absoluteTotal.addingReportingOverflow(magnitude)
                guard !overflow,
                      !absoluteOverflow,
                      absWithinSafeRange(newTotal),
                      absWithinSafeRange(newAbsoluteTotal) else {
                    throw CSVImportError.totalOutOfRange
                }
                total = newTotal
                absoluteTotal = newAbsoluteTotal
                imported.append(ImportedEntry(
                    usageDate: usageDate,
                    user: sanitizeDisplayText(name),
                    merchant: sanitizeDisplayText(merchant),
                    amount: amount,
                    sourceRecordNumber: row.number
                ))
                started = true
            case .failure(.invalidFormat):
                warnings.append(ImportWarning(
                    recordNumber: row.number,
                    message: "利用金額を整数として解釈できないため除外しました。"
                ))
            case .failure(.outOfRange):
                throw CSVImportError.amountOutOfRange(recordNumber: row.number)
            }
        }

        guard !imported.isEmpty else { throw CSVImportError.noValidEntries }
        let hash = SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
        return ImportResult(
            sourceFileName: fileName,
            sourceHash: hash,
            suggestedMonth: Self.suggestMonth(from: fileName),
            entries: imported,
            warnings: warnings,
            importedTotal: total
        )
    }

    public static func suggestMonth(from fileName: String, now: Date = Date()) -> String {
        let pattern = "(?<![0-9])(20[0-9]{2})(0[1-9]|1[0-2])(?:0[1-9]|[12][0-9]|3[01])(?![0-9])"
        if let regex = try? NSRegularExpression(pattern: pattern),
           let match = regex.firstMatch(in: fileName, range: NSRange(fileName.startIndex..., in: fileName)),
           let yearRange = Range(match.range(at: 1), in: fileName),
           let monthRange = Range(match.range(at: 2), in: fileName) {
            return "\(fileName[yearRange])-\(fileName[monthRange])"
        }
        let formatter = DateFormatter()
        formatter.calendar = Calendar(identifier: .gregorian)
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.dateFormat = "yyyy-MM"
        return formatter.string(from: now)
    }

    private func parseAmount(_ raw: String) -> Result<Int64, MoneyParseFailure> {
        var value = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        if value.hasPrefix("¥") || value.hasPrefix("￥") {
            value.removeFirst()
            value = value.trimmingCharacters(in: .whitespacesAndNewlines)
        }
        let pattern = "^[+-]?(?:[0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)$"
        guard value.range(of: pattern, options: .regularExpression) != nil else {
            return .failure(.invalidFormat)
        }
        let digits = value.replacingOccurrences(of: ",", with: "")
        guard let amount = Int64(digits) else { return .failure(.outOfRange) }
        guard absWithinSafeRange(amount) else { return .failure(.outOfRange) }
        return .success(amount)
    }

    private func absWithinSafeRange(_ value: Int64) -> Bool {
        value >= -Self.maximumSafeAmount && value <= Self.maximumSafeAmount
    }

    private func field(_ values: [String], at index: Int) -> String {
        guard values.indices.contains(index) else { return "" }
        return values[index]
    }

    private func cleanField(_ value: String) -> String {
        value.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private func sanitizeDisplayText(_ value: String) -> String {
        let allowed = value.unicodeScalars.filter { scalar in
            !CharacterSet.controlCharacters.contains(scalar) || scalar == "\t"
        }
        return String(String.UnicodeScalarView(allowed)).trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private func isOtherSectionTitle(_ values: [String]) -> Bool {
        let nonEmpty = values.filter { !$0.isEmpty }
        guard nonEmpty.count == 1 else { return false }
        return nonEmpty[0].contains("キャッシングご返済明細")
    }
}

private enum MoneyParseFailure: Error {
    case invalidFormat
    case outOfRange
}

private struct CSVRow {
    let number: Int
    let fields: [String]
}

private enum CSVReader {
    static func parse(_ text: String) throws -> [CSVRow] {
        let scalars = Array(text.unicodeScalars)
        var rows: [CSVRow] = []
        var fields: [String] = []
        var fieldScalars: [UnicodeScalar] = []
        var insideQuotes = false
        var justClosedQuote = false
        var index = 0
        var recordNumber = 1

        func finishField() {
            fields.append(String(String.UnicodeScalarView(fieldScalars)))
            fieldScalars.removeAll(keepingCapacity: true)
            justClosedQuote = false
        }

        func finishRow() {
            finishField()
            rows.append(CSVRow(number: recordNumber, fields: fields))
            fields.removeAll(keepingCapacity: true)
            recordNumber += 1
        }

        while index < scalars.count {
            let scalar = scalars[index]
            if insideQuotes {
                if scalar == "\"" {
                    if index + 1 < scalars.count, scalars[index + 1] == "\"" {
                        fieldScalars.append("\"")
                        index += 1
                    } else {
                        insideQuotes = false
                        justClosedQuote = true
                    }
                } else {
                    fieldScalars.append(scalar)
                }
            } else if justClosedQuote {
                switch scalar {
                case ",":
                    finishField()
                case "\n":
                    finishRow()
                case "\r":
                    if index + 1 < scalars.count, scalars[index + 1] == "\n" {
                        index += 1
                    }
                    finishRow()
                default:
                    throw CSVImportError.malformedCSV
                }
            } else {
                switch scalar {
                case "\"" where fieldScalars.isEmpty:
                    insideQuotes = true
                case "\"":
                    throw CSVImportError.malformedCSV
                case ",":
                    finishField()
                case "\n":
                    finishRow()
                case "\r":
                    if index + 1 < scalars.count, scalars[index + 1] == "\n" {
                        index += 1
                    }
                    finishRow()
                default:
                    fieldScalars.append(scalar)
                }
            }
            index += 1
        }

        guard !insideQuotes else { throw CSVImportError.malformedCSV }
        if !fieldScalars.isEmpty || !fields.isEmpty {
            finishRow()
        }
        return rows
    }
}
