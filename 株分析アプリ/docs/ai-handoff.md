# Stock Compass 再作成用ハンドオフ資料

## 1. この資料の目的

本資料は、現在のコードと設計を別のAI・開発者が同等のデスクトップアプリとして再構築するための仕様書です。`docs/requirements.md` はプロダクト要件、本文書は「現在の実装」と「将来の推奨」を分離した実装引き継ぎ資料です。

## 2. プロダクト概要

- 名称: Stock Compass（日本語UI: 株分析アプリ）
- 対象: 株式投資初心者
- 対象市場: 日本株、東証プライムを想定
- 目的: 株価の傾向・出来高・リスクをやさしく可視化し、売買判断を支援する
- 現在の注文: 紙上（仮想）運用のみ。実資金・証券口座には接続しない
- 現在のデータ: UI確認用のインメモリサンプル。リアルタイム価格ではない
- 重要な表示: 「利益を保証しない」「元本割れの可能性」「仮想運用」を常に明示

## 3. 現在のリポジトリ構成

```text
株分析アプリ/
├─ docs/
│  ├─ requirements.md                 # 詳細要件定義
│  ├─ ai-handoff.md                    # 本資料
│  └─ ui-concepts/*.png                # UI案の参考画像
└─ web/
   ├─ app/
   │  ├─ page.tsx                      # 画面、状態、サンプルデータ（主要実装）
   │  ├─ globals.css                   # UI全体のスタイル
   │  └─ layout.tsx                    # メタデータ、lang=ja
   ├─ desktop/
   │  ├─ main.cjs                      # Electronメインプロセス
   │  ├─ preload.cjs                   # contextBridge公開API
   │  ├─ renderer.tsx                   # Reactエントリ
   │  ├─ index.html                     # Electron用HTML
   │  └─ desktop.css                    # ドラッグ領域等
   ├─ vite.desktop.config.ts            # Electron向けVite設定
   ├─ build/app-icon.png                # macOSアプリアイコン
   ├─ public/og.png                     # OGP画像
   ├─ package.json
   └─ .openai/hosting.json              # Sites公開用設定（任意）
```

## 4. 技術スタックと実行環境

- Node.js `>=22.13.0`
- React `19.2.6`、TypeScript `5.9.3`
- Vite `8.0.13`、Electron `^44.1.1`
- electron-builder `^26.15.3`（macOS arm64、dmg/zip）
- lucide-react（アイコン）、CSS（Tailwindではなく主に`globals.css`）
- `web/package.json` は `type: module`。Electronの`.cjs`だけCommonJS。

## 5. 画面と操作仕様

### 共通レイアウト

左サイドバー、上部ヘッダー、中央コンテンツの3領域。モバイル幅では左メニューを開閉式にする。ヘッダーには「仮想運用中」、通知、ユーザーアイコンを表示する。

### ナビゲーション

「今日の分析」「銘柄を探す」「仮想運用」「ポートフォリオ」「取引履歴」「学ぶ」「設定」「ヘルプ」。クリックで`activeNav`を変更し、画面を切り替える。通知ベルは「通知」画面へ遷移する。モバイルメニュー選択後は閉じる。

### 今日の分析

選択中銘柄の名称・コード・市場・価格・騰落率、判定（買い候補/様子を見る）、0〜100分析スコア、株価チャート、判定理由（トレンド・出来高・リスク）、注意書きを表示する。期間ボタンは1か月/3か月/1年。星ボタンでウォッチリストを切り替える。「注文案を見る」で仮想注文モーダルを開く。

### 銘柄を探す

会社名・4桁コード・市場を部分一致検索する。入力中に結果を絞り込み、Enterまたは検索ボタンで件数をトースト表示する。結果行をクリックすると今日の分析へ戻り、その銘柄を選択する。0件時は検索条件クリアを提供する。

### 仮想運用

仮想資産、現金、保有銘柄数を表示し、選択中銘柄の注文案を確認できる。注文保存は現在トースト表示のみで、サーバー保存は未実装。

### ポートフォリオ / 取引履歴 / 学ぶ / 設定 / ヘルプ / 通知

各画面は初心者向けの説明カード・テーブル・FAQ・通知リストを表示する。設定では許容損失率、注文前確認、1銘柄投資上限を変更できる（現状は画面内stateのみ）。

## 6. データ仕様（現状）

`page.tsx` の`Stock`型:

```ts
{ code, name, market, price, change, score, verdict,
  tone: 'buy'|'watch', trend, volume, risk, color }
```

サンプル銘柄は7203トヨタ、6758ソニー、6861キーエンス、8306三菱UFJ FG、9434ソフトバンク。銘柄コードは文字列として扱い、先頭ゼロを失わないこと。

ウォッチリストは`localStorage`のキー`stock-compass-watchlist`にコード配列JSONで保存する。破損JSONは削除して初期値へ戻す。その他の価格・注文・設定は永続化されない。

## 7. 主要コンポーネントと状態

- `Sparkline`: SVGの小型折れ線
- `PriceChart`: 期間に応じた疑似時系列SVG
- `SecondaryView`: ナビゲーション各画面、検索state、設定state
- `Home`: `selectedCode`, `activeNav`, `watchlist`, `menuOpen`, `toast`, `orderOpen`, `chartPeriod`, `infoOpen`
- モーダルは背景クリックまたは閉じるボタンで閉じる。注文保存・説明確認はトースト/クローズ。

## 8. Electronの挙動

`desktop/main.cjs` はBrowserWindow（初期1440x960、最小920x680、contextIsolation有効）を作る。開発時は`http://localhost:4173`、パッケージ時は`desktop-dist/desktop/index.html`を読み込む。`preload.cjs` は`window.stockCompassDesktop`にplatform/versionだけを公開する。Node APIや外部通信をrendererへ直接公開しない。

## 9. コマンド

```bash
cd web
npm install
npm run desktop:dev      # Vite + Electron開発起動
npm run desktop:build    # desktop-distへ静的ビルド
npm run desktop:start    # ビルド後にElectron起動
npm run desktop:package  # macOS arm64のdmg/zip作成
npm run lint
```

パッケージのアイコンは`build/app-icon.png`。別OS対応時はelectron-builderのtarget/icon設定を追加する。コード署名・公証は未設定。

## 10. 別AIに再作成させる手順（推奨）

1. `docs/requirements.md` と本資料を読み、MVPの範囲を固定する。
2. React + TypeScript + Vite + Electronを初期化し、上記ファイル構成を作る。
3. まずサンプルデータと`Home`の画面遷移を実装する。
4. 検索（9434を含む）、銘柄選択、星の永続化、期間切替、モーダル、トーストを実装する。
5. `globals.css`でデスクトップ/モバイルのレイアウトとアクセシビリティを整える。
6. `desktop:build`、`desktop:start`、`desktop:package`の順で検証する。
7. 実データを接続する場合はUIとデータ取得層を分離し、APIキーをrendererやリポジトリに置かない。

## 11. 受け入れ条件

- Electronウィンドウが白画面にならず起動する
- 左メニュー全項目が対応画面へ遷移する
- `9434`、`ソフトバンク`で検索結果が表示される
- 検索結果選択で今日の分析の銘柄が切り替わる
- 星の追加/解除を再起動後も復元できる
- 期間ボタン、注文モーダル、設定保存、FAQ開閉、通知操作が反応する
- 実注文が発生しないことが画面上で明示される
- `npm run desktop:build`が成功する

## 12. 現在の制約と推奨改善

現状はフロントエンド試作であり、株価API、認証、DB、バックテスト計算、実注文、注文履歴の永続化は未実装。次の段階では、(1)データ取得アダプター、(2)分析エンジン（SMA/RSI/出来高/リスクの純粋関数）、(3)SQLite等のローカルDB、(4)バックテスト、(5)テスト（検索・状態・Electron起動）、(6)API障害時のキャッシュとレート制限を追加することを推奨する。金融情報は免責・データ時刻・遅延表示を必須とする。

最新ソース変更後に作成済みdmgが古い場合があるため、配布前には必ず`npm run desktop:package`を再実行する。

## 13. 再作成用プロンプト（そのまま別AIへ渡せる）

```text
docs/requirements.md と docs/ai-handoff.md を仕様の一次資料として、Stock Compassを再実装してください。
日本株初心者向け、Electronデスクトップアプリ、React/TypeScript/Vite構成、仮想運用のみです。
左メニューの全画面、9434を含む銘柄検索、銘柄選択、ウォッチリストlocalStorage保存、期間切替チャート、判定説明、注文案モーダル、設定・FAQ・通知を動作させてください。
実データ/API/実注文は追加せず、サンプルデータで完成させてください。白画面を避けるためElectronの開発URLとパッケージ時の静的HTMLパスを分け、npm run desktop:buildで検証してください。
未確定事項は本資料の推奨に従い、実装済みと将来拡張を混同しないでください。
```
