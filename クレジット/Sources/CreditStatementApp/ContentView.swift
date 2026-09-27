import AppKit
import CreditStatementCore
import SwiftUI
import UniformTypeIdentifiers

struct ContentView: View {
    @ObservedObject var model: AppModel

    var body: some View {
        VStack(spacing: 0) {
            AppHeader(model: model)
            Divider()
            HStack(spacing: 0) {
                MonthSidebar(model: model)
                    .frame(width: 210)
                Divider()
                Group {
                    if let statement = model.selectedStatement {
                        MonthDashboard(model: model, statement: statement)
                    } else {
                        EmptyDashboard(model: model)
                    }
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
        }
        .background(AppColors.canvas)
        .fileImporter(
            isPresented: $model.isShowingFileImporter,
            allowedContentTypes: [.commaSeparatedText, .plainText],
            allowsMultipleSelection: false
        ) { result in
            model.beginImport(from: result)
        }
        .sheet(item: $model.pendingImport) { result in
            ImportPreviewSheet(model: model, result: result)
        }
        .alert(item: $model.alert) { alert in
            Alert(
                title: Text(alert.title),
                message: Text(alert.message),
                dismissButton: .default(Text("閉じる"))
            )
        }
    }
}

private struct AppHeader: View {
    @ObservedObject var model: AppModel

    var body: some View {
        HStack(spacing: 12) {
            ZStack {
                RoundedRectangle(cornerRadius: 9)
                    .fill(AppColors.accent)
                    .frame(width: 34, height: 34)
                Text("¥")
                    .font(.system(size: 18, weight: .medium))
                    .foregroundColor(.white)
            }
            Text("クレジット明細")
                .font(.system(size: 17, weight: .medium))
            Spacer()
            if model.isImporting {
                ProgressView()
                    .controlSize(.small)
                Text("読込中")
                    .font(.caption)
                    .foregroundColor(.secondary)
            }
            Button {
                model.isShowingFileImporter = true
            } label: {
                Label("CSVを読み込む", systemImage: "square.and.arrow.down")
            }
            .buttonStyle(PrimaryButtonStyle())
        }
        .padding(.horizontal, 18)
        .frame(height: 60)
        .background(AppColors.surface)
    }
}

private struct MonthSidebar: View {
    @ObservedObject var model: AppModel
    @State private var hoveredMonthID: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("保存済みの月")
                .font(.caption)
                .foregroundColor(.secondary)
                .padding(.horizontal, 12)
                .padding(.top, 16)

            ScrollView {
                LazyVStack(spacing: 5) {
                    ForEach(model.statements) { statement in
                        Button {
                            model.selectedMonthID = statement.month
                            model.selectedTab = .summary
                        } label: {
                            VStack(alignment: .leading, spacing: 4) {
                                Text(model.displayMonth(statement.month))
                                    .font(.system(size: 14, weight: .medium))
                                HStack {
                                    Text(MoneyText.format(statement.currentTotal))
                                    Spacer()
                                    Text("\(statement.includedEntries.count)件")
                                }
                                .font(.caption)
                                .foregroundColor(.secondary)
                            }
                            .padding(.horizontal, 11)
                            .padding(.vertical, 10)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .contentShape(RoundedRectangle(cornerRadius: 9))
                            .background(
                                RoundedRectangle(cornerRadius: 9)
                                    .fill(
                                        model.selectedMonthID == statement.month
                                            ? AppColors.selection
                                            : hoveredMonthID == statement.month ? AppColors.hover : Color.clear
                                    )
                            )
                            .overlay(
                                RoundedRectangle(cornerRadius: 9)
                                    .stroke(model.selectedMonthID == statement.month ? AppColors.selectionBorder : Color.clear)
                            )
                        }
                        .buttonStyle(.plain)
                        .onHover { isHovering in
                            if isHovering {
                                hoveredMonthID = statement.month
                            } else if hoveredMonthID == statement.month {
                                hoveredMonthID = nil
                            }
                        }
                    }
                }
                .frame(maxWidth: .infinity)
                .padding(.horizontal, 8)
            }

            Spacer(minLength: 0)
            if let statement = model.selectedStatement {
                VStack(alignment: .leading, spacing: 3) {
                    Text("取込元")
                        .font(.caption2)
                        .foregroundColor(.secondary)
                    Text(statement.sourceFileName)
                        .font(.caption)
                        .lineLimit(2)
                        .help(statement.sourceFileName)
                }
                .padding(12)
            }
        }
        .background(AppColors.sidebar)
    }
}

private struct EmptyDashboard: View {
    @ObservedObject var model: AppModel

    var body: some View {
        VStack(spacing: 16) {
            Image(systemName: "doc.text.magnifyingglass")
                .font(.system(size: 44))
                .foregroundColor(AppColors.accent)
            Text("CSVを読み込んで始めましょう")
                .font(.title2.weight(.medium))
            Text("明細は月ごとにMac内へ保存され、外部には送信されません。")
                .foregroundColor(.secondary)
            Button("CSVを選択") {
                model.isShowingFileImporter = true
            }
            .buttonStyle(PrimaryButtonStyle())
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}

private struct MonthDashboard: View {
    @ObservedObject var model: AppModel
    let statement: StatementMonth

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack(alignment: .bottom) {
                VStack(alignment: .leading, spacing: 3) {
                    Text("月別集計")
                        .font(.caption)
                        .foregroundColor(.secondary)
                    Text(model.displayMonth(statement.month))
                        .font(.system(size: 25, weight: .medium))
                }
                Spacer()
                Picker("表示", selection: $model.selectedTab) {
                    ForEach(DashboardTab.allCases) { tab in
                        Text(tab.rawValue).tag(tab)
                    }
                }
                .labelsHidden()
                .pickerStyle(.segmented)
                .frame(width: 310)
            }

            HStack(spacing: 12) {
                MetricCard(title: "現在の合計", value: MoneyText.format(statement.currentTotal), emphasis: true)
                MetricCard(title: "集計対象", value: "\(statement.includedEntries.count)件")
                MetricCard(
                    title: "集計から除外",
                    value: "\(statement.excludedEntries.count)件・\(MoneyText.format(statement.excludedTotal))"
                )
            }

            switch model.selectedTab {
            case .summary:
                SummaryDashboard(model: model, statement: statement)
            case .details:
                EntryManagementView(model: model, statement: statement)
            case .excluded:
                ExcludedEntriesView(model: model, statement: statement)
            }
        }
        .padding(22)
    }
}

private struct MetricCard: View {
    let title: String
    let value: String
    var emphasis = false

    var body: some View {
        VStack(alignment: .leading, spacing: 7) {
            Text(title)
                .font(.caption)
                .foregroundColor(.secondary)
            Text(value)
                .font(.system(size: emphasis ? 21 : 18, weight: .medium, design: .rounded))
                .lineLimit(1)
                .minimumScaleFactor(0.75)
        }
        .padding(15)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(AppColors.surface)
        .overlay(RoundedRectangle(cornerRadius: 10).stroke(AppColors.border))
        .clipShape(RoundedRectangle(cornerRadius: 10))
    }
}

private struct UserTotalsStrip: View {
    let totals: [UserTotal]

    var body: some View {
        VStack(alignment: .leading, spacing: 9) {
            HStack {
                Text("利用者別合計")
                    .font(.system(size: 15, weight: .medium))
                Spacer()
                Text("集計から除外した明細は含みません")
                    .font(.caption)
                    .foregroundColor(.secondary)
            }
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 9) {
                    ForEach(totals) { total in
                        HStack(spacing: 16) {
                            Text(total.user)
                                .lineLimit(1)
                            Text(MoneyText.format(total.amount))
                                .font(.system(size: 16, weight: .medium, design: .rounded))
                                .monospacedDigit()
                        }
                        .padding(.horizontal, 13)
                        .frame(minWidth: 210, minHeight: 42)
                        .background(AppColors.subtotal)
                        .overlay(RoundedRectangle(cornerRadius: 8).stroke(AppColors.selectionBorder))
                        .clipShape(RoundedRectangle(cornerRadius: 8))
                    }
                }
            }
        }
        .padding(13)
        .background(AppColors.surface)
        .overlay(RoundedRectangle(cornerRadius: 10).stroke(AppColors.border))
        .clipShape(RoundedRectangle(cornerRadius: 10))
    }
}

private struct SummaryDashboard: View {
    @ObservedObject var model: AppModel
    let statement: StatementMonth

    var body: some View {
        VStack(spacing: 12) {
            UserTotalsStrip(totals: statement.userTotals)
            HStack(alignment: .top, spacing: 12) {
                VStack(spacing: 0) {
                    PanelHeader(title: "利用者・利用店別", detail: "金額の高い順")
                    SummaryTable(model: model, statement: statement)
                }
                .background(AppColors.surface)
                .overlay(RoundedRectangle(cornerRadius: 10).stroke(AppColors.border))
                .clipShape(RoundedRectangle(cornerRadius: 10))

                ReconciliationPanel(model: model, statement: statement)
                    .frame(width: 250)
            }
        }
        .frame(maxHeight: .infinity, alignment: .top)
    }
}

private struct PanelHeader: View {
    let title: String
    var detail: String? = nil

    var body: some View {
        HStack {
            Text(title).font(.system(size: 15, weight: .medium))
            Spacer()
            if let detail {
                Text(detail).font(.caption).foregroundColor(.secondary)
            }
        }
        .padding(.horizontal, 14)
        .frame(height: 48)
    }
}

private struct SummaryTable: View {
    @ObservedObject var model: AppModel
    let statement: StatementMonth

    var body: some View {
        VStack(spacing: 0) {
            SummaryRow(user: "利用者", merchant: "利用店名", amount: "金額", header: true)
            ScrollView {
                LazyVStack(spacing: 0) {
                    ForEach(statement.userTotals) { total in
                        let summaries = statement.merchantSummaries.filter { $0.user == total.user }
                        ForEach(summaries) { summary in
                            SummaryRow(
                                user: summary.user,
                                merchant: summary.merchant,
                                amount: MoneyText.format(summary.amount)
                            )
                            .contentShape(Rectangle())
                            .onTapGesture { model.selectedTab = .details }
                        }
                        SummaryRow(
                            user: total.user,
                            merchant: "合計",
                            amount: MoneyText.format(total.amount),
                            subtotal: true
                        )
                    }
                }
            }
        }
    }
}

private struct SummaryRow: View {
    let user: String
    let merchant: String
    let amount: String
    var header = false
    var subtotal = false

    var body: some View {
        HStack(spacing: 12) {
            Text(user).frame(width: 150, alignment: .leading)
            Text(merchant).frame(maxWidth: .infinity, alignment: .leading)
            Text(amount).frame(width: 120, alignment: .trailing)
                .monospacedDigit()
        }
        .font(header ? .caption.weight(.medium) : .body)
        .foregroundColor(header ? .secondary : .primary)
        .padding(.horizontal, 14)
        .frame(minHeight: 42)
        .background(subtotal ? AppColors.subtotal : (header ? AppColors.tableHeader : Color.clear))
        .overlay(alignment: .bottom) { Divider() }
    }
}

private struct ReconciliationPanel: View {
    @ObservedObject var model: AppModel
    let statement: StatementMonth

    var body: some View {
        VStack(spacing: 0) {
            PanelHeader(title: "金額の確認")
            VStack(spacing: 12) {
                ReconciliationRow(label: "取込時合計", amount: statement.importedTotal)
                ReconciliationRow(label: "除外した金額", amount: -statement.excludedTotal)
                Divider()
                ReconciliationRow(label: "現在の合計", amount: statement.currentTotal, emphasis: true)
                Button("除外した明細を見る") {
                    model.selectedTab = .excluded
                }
                .buttonStyle(SecondaryButtonStyle())
                .disabled(statement.excludedEntries.isEmpty)
                if !statement.importWarnings.isEmpty {
                    Label("取込時の警告 \(statement.importWarnings.count)件", systemImage: "exclamationmark.triangle")
                        .font(.caption)
                        .foregroundColor(.orange)
                }
            }
            .padding(14)
        }
        .background(AppColors.surface)
        .overlay(RoundedRectangle(cornerRadius: 10).stroke(AppColors.border))
        .clipShape(RoundedRectangle(cornerRadius: 10))
    }
}

private struct ReconciliationRow: View {
    let label: String
    let amount: Int64
    var emphasis = false

    var body: some View {
        HStack {
            Text(label)
            Spacer()
            Text(MoneyText.format(amount))
                .fontWeight(emphasis ? .medium : .regular)
                .monospacedDigit()
        }
    }
}

private struct EntryManagementView: View {
    @ObservedObject var model: AppModel
    let statement: StatementMonth
    @State private var searchText = ""
    @State private var selectedUser = "すべて"
    @State private var selectedStatus = "すべて"
    @State private var selectedIDs: Set<UUID> = []
    @State private var pendingExclusion: Set<UUID> = []
    @State private var isConfirmingExclusion = false
    @State private var pendingRestore: Set<UUID> = []
    @State private var isConfirmingRestore = false

    private var users: [String] {
        Array(Set(statement.entries.map(\.user))).sorted {
            $0.localizedStandardCompare($1) == .orderedAscending
        }
    }

    private var visibleEntries: [CreditEntry] {
        statement.entries.filter { entry in
            let matchesUser = selectedUser == "すべて" || entry.user == selectedUser
            let matchesSearch = searchText.isEmpty
                || entry.merchant.localizedCaseInsensitiveContains(searchText)
                || entry.user.localizedCaseInsensitiveContains(searchText)
            let matchesStatus = selectedStatus == "すべて"
                || (selectedStatus == "集計対象" && entry.status == .included)
                || (selectedStatus == "除外済み" && entry.status == .excluded)
            return matchesUser && matchesSearch && matchesStatus
        }
        .sorted {
            if $0.usageDate != $1.usageDate { return $0.usageDate > $1.usageDate }
            return $0.sourceRecordNumber > $1.sourceRecordNumber
        }
    }

    private var pendingTotal: Int64 {
        statement.entries.filter { pendingExclusion.contains($0.id) }.reduce(0) { $0 + $1.amount }
    }

    var body: some View {
        VStack(spacing: 0) {
            UserTotalsStrip(totals: statement.userTotals)
                .padding(12)

            HStack(spacing: 10) {
                Image(systemName: "magnifyingglass").foregroundColor(.secondary)
                TextField("利用店名または利用者を検索", text: $searchText)
                    .textFieldStyle(.plain)
                Divider().frame(height: 22)
                Picker("利用者", selection: $selectedUser) {
                    Text("すべての利用者").tag("すべて")
                    ForEach(users, id: \.self) { Text($0).tag($0) }
                }
                .frame(width: 180)
                Divider().frame(height: 22)
                Picker("状態", selection: $selectedStatus) {
                    Text("すべての状態").tag("すべて")
                    Text("集計対象").tag("集計対象")
                    Text("除外済み").tag("除外済み")
                }
                .frame(width: 145)
            }
            .padding(.horizontal, 13)
            .frame(height: 46)
            .background(AppColors.surface)

            DetailHeader(selectionTitle: "選択", actionTitle: "操作")
            ScrollView {
                LazyVStack(spacing: 0) {
                    ForEach(visibleEntries) { entry in
                        DetailRow(
                            entry: entry,
                            isSelected: Binding(
                                get: { selectedIDs.contains(entry.id) },
                                set: { selected in
                                    if selected { selectedIDs.insert(entry.id) }
                                    else { selectedIDs.remove(entry.id) }
                                }
                            ),
                            selectionEnabled: entry.status == .included,
                            actionTitle: entry.status == .included ? "除外" : "復元"
                        ) {
                            if entry.status == .included {
                                pendingExclusion = [entry.id]
                                isConfirmingExclusion = true
                            } else {
                                pendingRestore = [entry.id]
                                isConfirmingRestore = true
                            }
                        }
                    }
                }
            }

            HStack {
                Text(selectedIDs.isEmpty ? "明細を選択してください" : "\(selectedIDs.count)件を選択")
                    .foregroundColor(.secondary)
                Spacer()
                Button("選択した明細を集計から除外") {
                    pendingExclusion = selectedIDs
                    isConfirmingExclusion = true
                }
                .buttonStyle(DangerButtonStyle())
                .disabled(selectedIDs.isEmpty)
            }
            .padding(.horizontal, 13)
            .frame(height: 52)
            .background(AppColors.tableHeader)
        }
        .background(AppColors.surface)
        .overlay(RoundedRectangle(cornerRadius: 10).stroke(AppColors.border))
        .clipShape(RoundedRectangle(cornerRadius: 10))
        .alert("明細を集計から除外しますか？", isPresented: $isConfirmingExclusion) {
            Button("キャンセル", role: .cancel) { pendingExclusion = [] }
            Button("除外する", role: .destructive) {
                model.excludeEntries(pendingExclusion, in: statement.month)
                selectedIDs.subtract(pendingExclusion)
                pendingExclusion = []
            }
        } message: {
            Text("\(model.displayMonth(statement.month))の\(pendingExclusion.count)件、合計\(MoneyText.format(pendingTotal))を集計対象外にします。後から復元できます。")
        }
        .alert("明細を集計に戻しますか？", isPresented: $isConfirmingRestore) {
            Button("キャンセル", role: .cancel) { pendingRestore = [] }
            Button("復元する") {
                model.restoreEntries(pendingRestore, in: statement.month)
                pendingRestore = []
            }
        } message: {
            Text("\(model.displayMonth(statement.month))の\(pendingRestore.count)件を集計対象に戻します。")
        }
    }
}

private struct ExcludedEntriesView: View {
    @ObservedObject var model: AppModel
    let statement: StatementMonth
    @State private var selectedIDs: Set<UUID> = []
    @State private var pendingRestore: Set<UUID> = []
    @State private var isConfirmingRestore = false

    var body: some View {
        Group {
            if statement.excludedEntries.isEmpty {
                VStack(spacing: 12) {
                    Image(systemName: "checkmark.circle")
                        .font(.system(size: 38))
                        .foregroundColor(.green)
                    Text("削除済みの明細はありません")
                        .font(.headline)
                    Text("集計から除外した明細はここから復元できます。")
                        .foregroundColor(.secondary)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .background(AppColors.surface)
                .overlay(RoundedRectangle(cornerRadius: 10).stroke(AppColors.border))
                .clipShape(RoundedRectangle(cornerRadius: 10))
            } else {
                VStack(spacing: 0) {
                    DetailHeader(selectionTitle: "選択", actionTitle: "操作")
                    ScrollView {
                        LazyVStack(spacing: 0) {
                            ForEach(statement.excludedEntries.sorted { $0.sourceRecordNumber < $1.sourceRecordNumber }) { entry in
                                DetailRow(
                                    entry: entry,
                                    isSelected: Binding(
                                        get: { selectedIDs.contains(entry.id) },
                                        set: { selected in
                                            if selected { selectedIDs.insert(entry.id) }
                                            else { selectedIDs.remove(entry.id) }
                                        }
                                    ),
                                    selectionEnabled: true,
                                    actionTitle: "復元"
                                ) {
                                    pendingRestore = [entry.id]
                                    isConfirmingRestore = true
                                }
                            }
                        }
                    }
                    HStack {
                        Text("削除済み \(statement.excludedEntries.count)件・\(MoneyText.format(statement.excludedTotal))")
                            .foregroundColor(.secondary)
                        Spacer()
                        Button("選択した明細を復元") {
                            pendingRestore = selectedIDs
                            isConfirmingRestore = true
                        }
                        .buttonStyle(SecondaryButtonStyle())
                        .disabled(selectedIDs.isEmpty)
                    }
                    .padding(.horizontal, 13)
                    .frame(height: 52)
                    .background(AppColors.tableHeader)
                }
                .background(AppColors.surface)
                .overlay(RoundedRectangle(cornerRadius: 10).stroke(AppColors.border))
                .clipShape(RoundedRectangle(cornerRadius: 10))
            }
        }
        .alert("明細を集計に戻しますか？", isPresented: $isConfirmingRestore) {
            Button("キャンセル", role: .cancel) { pendingRestore = [] }
            Button("復元する") {
                model.restoreEntries(pendingRestore, in: statement.month)
                selectedIDs.subtract(pendingRestore)
                pendingRestore = []
            }
        } message: {
            Text("\(model.displayMonth(statement.month))の\(pendingRestore.count)件を集計対象に戻します。")
        }
    }
}

private struct DetailHeader: View {
    let selectionTitle: String
    let actionTitle: String

    var body: some View {
        HStack(spacing: 10) {
            Text(selectionTitle).frame(width: 46)
            Text("利用日").frame(width: 86, alignment: .leading)
            Text("利用者").frame(width: 145, alignment: .leading)
            Text("利用店名").frame(maxWidth: .infinity, alignment: .leading)
            Text("金額").frame(width: 110, alignment: .trailing)
            Text("状態").frame(width: 78, alignment: .center)
            Text(actionTitle).frame(width: 60, alignment: .trailing)
        }
        .font(.caption.weight(.medium))
        .foregroundColor(.secondary)
        .padding(.horizontal, 12)
        .frame(height: 38)
        .background(AppColors.tableHeader)
        .overlay(alignment: .bottom) { Divider() }
    }
}

private struct DetailRow: View {
    let entry: CreditEntry
    @Binding var isSelected: Bool
    let selectionEnabled: Bool
    let actionTitle: String
    let action: () -> Void

    var body: some View {
        HStack(spacing: 10) {
            Toggle("", isOn: $isSelected)
                .labelsHidden()
                .toggleStyle(.checkbox)
                .frame(width: 46)
                .disabled(!selectionEnabled)
            Text(entry.usageDate.isEmpty ? "—" : entry.usageDate)
                .frame(width: 86, alignment: .leading)
            Text(entry.user).frame(width: 145, alignment: .leading).lineLimit(1)
            Text(entry.merchant).frame(maxWidth: .infinity, alignment: .leading).lineLimit(1)
            Text(MoneyText.format(entry.amount)).frame(width: 110, alignment: .trailing).monospacedDigit()
            Text(entry.status == .included ? "集計対象" : "除外済み")
                .font(.caption.weight(.medium))
                .foregroundColor(entry.status == .included ? .green : .red)
                .frame(width: 78, alignment: .center)
            Button(actionTitle, action: action)
                .buttonStyle(.borderless)
                .foregroundColor(actionTitle == "除外" ? .red : AppColors.accent)
                .frame(width: 60, alignment: .trailing)
        }
        .padding(.horizontal, 12)
        .frame(minHeight: 42)
        .contentShape(Rectangle())
        .background(entry.status == .excluded ? AppColors.excludedRow : Color.clear)
        .foregroundColor(entry.status == .excluded ? .secondary : .primary)
        .overlay(alignment: .bottom) { Divider() }
    }
}

private struct ImportPreviewSheet: View {
    @ObservedObject var model: AppModel
    let result: ImportResult
    @Environment(\.dismiss) private var dismiss
    @State private var year: Int
    @State private var month: Int
    @State private var message: String?
    @State private var isConfirmingReplacement = false
    @State private var replacementCount = 0

    init(model: AppModel, result: ImportResult) {
        self.model = model
        self.result = result
        let parts = result.suggestedMonth.split(separator: "-")
        _year = State(initialValue: Int(parts.first ?? "") ?? Calendar.current.component(.year, from: Date()))
        _month = State(initialValue: Int(parts.dropFirst().first ?? "") ?? Calendar.current.component(.month, from: Date()))
    }

    private var targetMonth: String {
        String(format: "%04d-%02d", year, month)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            HStack {
                VStack(alignment: .leading, spacing: 4) {
                    Text("CSV取込プレビュー")
                        .font(.title2.weight(.medium))
                    Text(result.sourceFileName)
                        .foregroundColor(.secondary)
                        .lineLimit(1)
                        .help(result.sourceFileName)
                }
                Spacer()
            }

            GroupBox("対象月") {
                HStack {
                    Picker("年", selection: $year) {
                        ForEach(2000...(Calendar.current.component(.year, from: Date()) + 2), id: \.self) {
                            Text("\($0)年").tag($0)
                        }
                    }
                    Picker("月", selection: $month) {
                        ForEach(1...12, id: \.self) { Text("\($0)月").tag($0) }
                    }
                    Spacer()
                    Text("ファイル名から候補を設定しました")
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
                .padding(.vertical, 4)
            }

            HStack(spacing: 10) {
                PreviewMetric(title: "明細", value: "\(result.entries.count)件")
                PreviewMetric(title: "利用者", value: "\(Set(result.entries.map(\.user)).count)名")
                PreviewMetric(title: "取込合計", value: MoneyText.format(result.importedTotal))
                PreviewMetric(title: "警告", value: "\(result.warnings.count)件")
            }

            if !result.warnings.isEmpty {
                VStack(alignment: .leading, spacing: 6) {
                    Label("一部のレコードを除外して読み込みます", systemImage: "exclamationmark.triangle.fill")
                        .foregroundColor(.orange)
                    ForEach(result.warnings.prefix(4)) { warning in
                        Text("レコード\(warning.recordNumber): \(warning.message)")
                            .font(.caption)
                    }
                }
                .padding(12)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(Color.orange.opacity(0.1))
                .clipShape(RoundedRectangle(cornerRadius: 9))
            }

            if let message {
                Label(message, systemImage: "exclamationmark.circle")
                    .foregroundColor(.red)
                    .fixedSize(horizontal: false, vertical: true)
            }

            Spacer()
            HStack {
                Text("データはこのMac内だけに保存されます。")
                    .font(.caption)
                    .foregroundColor(.secondary)
                Spacer()
                Button("キャンセル") { dismiss() }
                    .keyboardShortcut(.cancelAction)
                Button("この月に保存") { attemptSave(replacing: false) }
                    .buttonStyle(PrimaryButtonStyle())
                    .keyboardShortcut(.defaultAction)
            }
        }
        .padding(22)
        .frame(width: 680, height: result.warnings.isEmpty ? 410 : 500)
        .alert("既存の月データを置き換えますか？", isPresented: $isConfirmingReplacement) {
            Button("キャンセル", role: .cancel) {}
            Button("置き換える", role: .destructive) { attemptSave(replacing: true) }
        } message: {
            Text("\(model.displayMonth(targetMonth))には\(replacementCount)件の明細があります。置換すると現在の除外状態もリセットされます。")
        }
    }

    private func attemptSave(replacing: Bool) {
        message = nil
        switch model.saveImport(result, targetMonth: targetMonth, replacing: replacing) {
        case .saved:
            dismiss()
        case .duplicate(let existingMonth):
            message = "同じCSVは\(model.displayMonth(existingMonth))に保存済みです。"
        case .replacementRequired(let existingCount):
            replacementCount = existingCount
            isConfirmingReplacement = true
        case .failed(let error):
            message = "保存できませんでした。データは変更していません。\n\(error)"
        }
    }
}

private struct PreviewMetric: View {
    let title: String
    let value: String

    var body: some View {
        VStack(alignment: .leading, spacing: 5) {
            Text(title).font(.caption).foregroundColor(.secondary)
            Text(value).font(.system(size: 17, weight: .medium)).monospacedDigit()
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(AppColors.tableHeader)
        .clipShape(RoundedRectangle(cornerRadius: 9))
    }
}

private enum AppColors {
    static let accent = Color(red: 0.14, green: 0.31, blue: 0.73)
    static let canvas = Color(nsColor: .windowBackgroundColor)
    static let surface = Color(nsColor: .controlBackgroundColor)
    static let sidebar = Color(nsColor: .underPageBackgroundColor)
    static let border = Color(nsColor: .separatorColor)
    static let selection = Color.accentColor.opacity(0.12)
    static let selectionBorder = Color.accentColor.opacity(0.35)
    static let hover = Color.primary.opacity(0.06)
    static let tableHeader = Color(nsColor: .textBackgroundColor).opacity(0.6)
    static let subtotal = Color.accentColor.opacity(0.08)
    static let excludedRow = Color.red.opacity(0.10)
}

private struct PrimaryButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.body.weight(.medium))
            .foregroundColor(.white)
            .padding(.horizontal, 14)
            .padding(.vertical, 8)
            .background(AppColors.accent.opacity(configuration.isPressed ? 0.82 : 1))
            .clipShape(RoundedRectangle(cornerRadius: 8))
    }
}

private struct SecondaryButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.body.weight(.medium))
            .padding(.horizontal, 12)
            .padding(.vertical, 7)
            .background(AppColors.tableHeader.opacity(configuration.isPressed ? 0.6 : 1))
            .overlay(RoundedRectangle(cornerRadius: 8).stroke(AppColors.border))
            .clipShape(RoundedRectangle(cornerRadius: 8))
    }
}

private struct DangerButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.body.weight(.medium))
            .foregroundColor(.red)
            .padding(.horizontal, 12)
            .padding(.vertical, 7)
            .background(Color.red.opacity(configuration.isPressed ? 0.14 : 0.08))
            .overlay(RoundedRectangle(cornerRadius: 8).stroke(Color.red.opacity(0.35)))
            .clipShape(RoundedRectangle(cornerRadius: 8))
    }
}
