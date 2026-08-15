# アーカイブページの再生成手順

「労務ニュース朝刊」アーカイブは、Claude Artifactとして公開されている静的ページ。
毎日の GitHub保存ルーティンの最後に、このページも再生成・再公開する。

**公開URL（固定・変えないこと）**：
https://claude.ai/code/artifact/1b8f2ccc-eaea-4620-bff5-c43a9557a99d

## 手順

1. `archive/shell.html` を読み込む（デザイン部分の土台）。
2. `news/*.md` を**ファイル名（日付）の降順**（新しい日付が先）で全て読み込む。
3. 各ファイルを以下のルールで `<details class="issue">...</details>` ブロックに変換する。
4. 月が変わる境目に `<div class="month-divider">YYYY年M月</div>` を挿入する。
5. 最新（一番上）の号だけ `open` 属性をつける。
6. `shell.html` の `<!-- ISSUES_GO_HERE -->` の位置に、変換した全issueブロックを差し込む。
7. `{{ISSUE_COUNT}}` を号数（ファイル数）に、`{{ISSUE_RANGE}}` を「創刊 YYYY年M月D日」（一番古いファイルの日付）に置換する。
8. 完成したHTMLを一時ファイルに保存し、Artifactツールで `url: "https://claude.ai/code/artifact/1b8f2ccc-eaea-4620-bff5-c43a9557a99d"` を指定して再公開する（favicon: 🗞️、title: "労務ニュース朝刊 — アーカイブ"）。

## Markdown → HTMLの変換ルール

### 新フォーマット（5段構成、2026-08-07以降）

各ファイルの `## 見出し` ごとに1つの記事として扱う：

| Markdown | HTML |
|---|---|
| `## ①見出しテキスト` | `<article class="article"><h3>①見出しテキスト</h3>` |
| `> 📖 **用語解説：...**\n> ...` | `<div class="glossary"><strong>用語解説：...</strong><br />...</div>` |
| `**何が起きた？**\n本文` | `<h4>何が起きた？</h4><p>本文</p>`（`**太字**` は `<strong>` に変換） |
| `**うちの仕事にどう関係する？**\n- [ ] 項目` | `<h4>うちの仕事にどう関係する？</h4><ul class="todo"><li><input type="checkbox" disabled />項目</li>...</ul>` |
| 立場別テーブル | `<h4>立場によって意見が分かれそうなポイント</h4><table class="opinion-table"><tr><th>絵文字 立場</th><td>意見</td></tr>...</table>` |
| `**🔗 情報源**：[サイト名「タイトル」](URL)` | `<p class="source-line">🔗 情報源：<a href="URL" target="_blank" rel="noopener">サイト名「タイトル」</a></p>` |

`<details>` の `summary` 部分：
```html
<summary>
  <span class="issue-badge">第N号 M/D</span>
  <span>
    <span class="issue-headline">（その日を象徴する短いキャッチコピー、20字程度）</span>
    <span class="issue-sub">（各記事見出しを「／」区切りで列挙）　全N本</span>
  </span>
  <span class="issue-toggle" aria-hidden="true">▾</span>
</summary>
```
`issue-headline` はその日で一番インパクトのあるニュースを軸に、新しく短く要約して作ってよい（元記事見出しの丸写しでなくてOK）。

`data-search` 属性には、各記事のキーワードをスペース区切りで詰め込む（検索用）。

`id` 属性は `issue-YYYY-MM-DD` の形式にする。

### 旧フォーマット（3段構成、2026-08-06のみ）

`news/2026-08-06.md` は例外的に旧フォーマット。`archive/shell.html` 相当の過去の公開版（またはこのファイル自身）を直接参照し、`.flat-list` / `.stance-block` クラスを使った構成を踏襲すること。冒頭に以下の注記を入れる：
```html
<p class="old-format-note">※ この号は初期フォーマット（要約／実務影響／賛否両論の3段構成）で配信されたものです。第2号以降、記事ごとに用語解説・実務ToDo・立場別意見表を備えた現在の形式に更新されました。</p>
```

## 月次まとめについて（前半・後半の2回、自動生成）

月次まとめは**月2回、自動生成される**（別トリガー「roumu-news 月次まとめ」が担当。日次のGitHub保存ルーティンとは別物）：

- **毎月15日**：その月の1日〜15日分を集計し「前半まとめ」を作成 → `news/monthly/YYYY-MM-first-half.md`
- **毎月末日**：その月の16日〜末日分を集計し「後半まとめ」を作成 → `news/monthly/YYYY-MM-second-half.md`

作成手順（月次まとめルーティン用）：
1. 対象期間の `news/YYYY-MM-DD.md` を全て読み、記事数・話題を集計する。
2. 8月前半分（`news/monthly/2026-08-summary.md`）の構成を参考に、以下を含める：
   - 冒頭の傾向サマリー（1〜2文）
   - テーマ別セクション（②③④…、各テーマに絵文字見出し＋箇条書き＋一言コメント）
   - 今後の重要締切テーブル（分かっているもののみ）
   - 締めの一言メモ
3. `news/monthly/YYYY-MM-first-half.md` または `news/monthly/YYYY-MM-second-half.md` として保存し、コミット・プッシュする。
4. アーカイブページを再構築する際、`.monthly` ブロックとして該当月の `month-divider` の直前に挿入する。同じ月に前半・後半2つある場合は、**新しい方（後半）を上**にする。CSSクラスはデイリー記事と分ける（`.monthly` / `.monthly-badge` / `.monthly-headline` / `.monthly-sub` / `.monthly-body`。構造は `archive/shell.html` と2026年8月分の実装例を参照）。
5. 左リボン（`.ribbon-panel`）のクイックジャンプ一覧にも、日次記事と同様に月次まとめが表示される（`archive/shell.html` のJSは `.issue, .monthly` の両方を拾う実装済み）。

**日次のGitHub保存ルーティン**は、月次まとめを新規作成しない。アーカイブページ再構築時は、既存の `news/monthly/*.md` があればそのまま反映するだけでよい。

## 注意事項

- HTML特殊文字（`&` `<` `>`）はエスケープすること。
- 既存の号の内容は変更しない（過去のnews/*.mdの中身をそのまま変換するだけ）。
- 再公開が失敗した場合も、GitHubへのpush自体は既に完了しているので、アーカイブ更新の失敗は致命的ではない。失敗した旨だけ通知に含めればよい。
