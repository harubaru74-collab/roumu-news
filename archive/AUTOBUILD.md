# アーカイブページの自動ビルド（2026-08-25〜、Claude不使用）

**このドキュメントが現在の正式な仕組みです。** `BUILD.md` は、Claudeが毎晩手作業でHTMLを組み立てて
Artifactツールに再公開していた旧方式（〜2026-08-25）の記録として残していますが、
Markdown→HTMLの変換ルール自体は`scripts/build_archive.py`に完全に引き継がれています。

## 仕組み

はるかちゃんの「できたこと日記」プロジェクトと同じ構造：

```
news/*.md が git push される
        ↓
GitHub Actions（.github/workflows/build-archive.yml）が起動
        ↓
scripts/build_archive.py（Pythonスクリプト・AI不使用）が
  news/*.md + news/monthly/*.md + archive/shell.html を読み込んで
  docs/index.html を組み立てる
        ↓
GitHub Pagesが docs/ を自動公開
```

**Claudeが関与するのは「news/*.md を書いてgit pushするところ」まで。** そこから先（アーカイブHTMLの組み立て・公開）は完全にGitHub側で完結し、トークンを一切消費しない。

## 公開URL

`https://harubaru74-collab.github.io/roumu-news/`
（リポジトリの Settings → Pages で「GitHub Actions」をソースに設定した後、初回のワークフロー実行後に有効になる）

## 日次ルーティンが変わったこと

深夜2:00の「roumu-news GitHub保存」ルーティンから、以下の作業が**不要になった**：
- アーカイブHTML全体の読み込み・組み立て直し
- Artifactツールでの再公開

代わりに必要なのは、従来通り `news/YYYY-MM-DD.md` を書いて `git push` するだけ。それだけで
GitHub Actionsが自動的にアーカイブページを更新する（pushから数十秒〜1分程度で反映される想定）。

## `scripts/build_archive.py` の変換ルール

`archive/BUILD.md` に記載されている変換ルール（Markdown → HTML）をそのままPythonで実装したもの。
新しい記事フォーマットが増えた場合は、このスクリプトも合わせて更新が必要。

### 既知のトレードオフ（正直な記録）

Claudeが手作業で組み立てていた頃と比べて、以下の点は自動化により**わずかに簡素化**されている：

1. **`issue-headline`（号の見出しキャッチコピー）**：以前はClaudeがその日で一番インパクトのある話題を軸に短く要約し直していたが、自動化後は**その日の①番目の記事の見出しをそのまま使う**（強調を外しただけ）。多少長くなる・地味になることがある。
2. **`data-search`（検索用キーワード）**：以前は記事内容から関連キーワードを手で拾って詰め込んでいたが、自動化後は**各記事の見出しをそのまま連結**したものになる。見出しに出てこない固有名詞・数値では検索にヒットしないことがある。
3. **表示崩れの監視**：以前は毎晩Claudeが目視で確認していたが、自動化後は無人。`scripts/build_archive.py`はパースに失敗した記事があっても処理を止めず、警告ログを出しつつ簡易表示にフォールバックする設計にしてあるが、完璧な保証ではない。

いずれも実害は小さいと判断して自動化を優先した。気になる崩れ・表記が見つかったら、`scripts/build_archive.py`の該当パーサーを直すか、教えてもらえれば都度調整する。

## セットアップに必要な一回限りの手動作業

Claude側のツールにはGitHub Pagesを有効化するAPIがないため、これだけは人の手（またはGitHub上での操作）が必要：

1. リポジトリの **Settings → Pages** を開く
2. **Build and deployment → Source** を「**GitHub Actions**」に変更する
3. 保存すれば、次に`news/`が更新された時（＝次回の深夜2:00ルーティン、または`workflow_dispatch`での手動実行）から自動的に公開される

## ロールバック

もし何か問題が起きた場合、旧来のArtifact方式（`archive/BUILD.md`の手順）にいつでも戻せる。
`news/*.md`自体の保存場所・フォーマットは変わっていないので、データが失われることはない。
