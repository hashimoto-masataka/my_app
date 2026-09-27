import SwiftUI

@main
struct CreditStatementDesktopApp: App {
    @StateObject private var model = AppModel()

    var body: some Scene {
        WindowGroup("クレジット明細") {
            ContentView(model: model)
                .frame(minWidth: 960, minHeight: 640)
        }
        .windowStyle(.titleBar)
        .commands {
            CommandGroup(after: .newItem) {
                Button("CSVを読み込む…") {
                    model.isShowingFileImporter = true
                }
                .keyboardShortcut("o", modifiers: .command)
            }
        }
    }
}
