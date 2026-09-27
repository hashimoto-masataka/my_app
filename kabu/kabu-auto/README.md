# kabu-auto —— 『Claude Codeで作る株の自動売買入門』配布物

本書（ぜろわん 著）で作るものを、そのまま置いてあります。**教育用のコードです。利益を保証しません。実際の発注とその結果は、名義人であるあなたの責任です。**

## 中身

| フォルダ | 何か | 本のどこ |
|---|---|---|
| [`kabu-auto/`](kabu-auto/) | **完成パッケージ（本体）**。このフォルダを丸ごと作業フォルダにすれば、データ収集（16:00 自動）→ シグナル判定 → 発注しないモード → 実発注（スイッチは既定で無効）まで動く。使い方は [`kabu-auto/README.md`](kabu-auto/README.md) | 第2〜7章、付録A |
| [`chapters/`](chapters/) | 章ごとの完成サンプル（その章を終えた時点の作業フォルダ。前の章のファイルも入っている） | 第2・3・4・6章 |
| [`claude_md/`](claude_md/) | `CLAUDE.md` の段階版（章を終えた時点のスナップショット） | 第3章〜 |
| [`ERRATA.md`](ERRATA.md) | 正誤表。仕様変更で本文が古くなった箇所もここに | — |

第5章・第7章の章別サンプルは、完成パッケージ `kabu-auto/` に統合しています（章別フォルダはありません）。

## 使い方（最短）

1. このページ右上の **Code → Download ZIP** で取る（git は要りません）
2. 展開して、`kabu-auto` フォルダを `ドキュメント\kabu-auto` に置く（パスに OneDrive が入っていないこと）
3. Claude Code のデスクトップアプリで、そのフォルダを開く（第2章 2-2）
4. あとは [`kabu-auto/README.md`](kabu-auto/README.md) の「最初にやること」へ

あなたの環境で Claude Code が生成するコードは、ここにあるものと細部が違って当然です（本書「本書の読み方」）。**動かなくなったときの逃げ道**として使ってください。

## 前提

- Windows 11、三菱UFJ eスマート証券の口座と kabuステーションAPI（第1章）
- Python は `py` ランチャーで動かします
- APIパスワードは環境変数 `KABU_API_PASSWORD` から読みます。**ファイルにもチャットにも書きません**

## 安全について

- 発注は既定で無効（`ORDER_MODE = "paper"`）。実発注は本書 7-1b・7-1c の順番を踏んでから
- 注文の市場は SOR（`ORDER_EXCHANGE = 9`）。東証（1）を指定した現物の新規注文は 100378 で拒否されます
- 証券会社の仕様は変わります。動かなくなったら `docs/` を取り直し、Claude Code に「仕様書を正として直して」と頼んでください

## ライセンス・連絡先

- コード：MIT License（[LICENSE](LICENSE)）。`docs/` の仕様書は [kabusapi](https://github.com/kabucom/kabusapi)（MIT）から
- 連絡先：zerowan042@gmail.com ／ X: [@01_kabubot](https://x.com/01_kabubot)
- 誤りの指摘：[ERRATA.md](ERRATA.md) か Issues へ
