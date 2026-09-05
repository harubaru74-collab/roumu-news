# roumu-news：月次まとめ Gemini API（GAS駆動）移行用プロンプト仕様

`ROUTINE.md`の「月次まとめ」ルーティン（Claude Code版）をGemini API向けに翻訳したもの。日次の`ROUTINE-GEMINI.md`と姉妹版・同じ設計思想。**GAS側の実装は既存の「AIコンシェルジュ計画」GAS、または新設した`news-gas-collector`のいずれかで行う想定。**

## 0. 全体アーキテクチャ

```
GAS 時間主導トリガー（毎月15日 と 月末日、深夜2:00 JST）
  ├─ 今日が「対象日」かどうかをGAS側で判定（後述）
  │   対象日でなければ何もせず終了（Gemini API呼び出し自体を発生させない＝コストゼロ）
  ├─ GitHub Contents APIで対象期間の news/YYYY-MM-DD.md を全て取得
  ├─ GitHub Contents APIで前回の月次まとめ（news/monthly/*.md、参考フォーマット用）を取得
  ├─ Gemini API呼び出し（1回、集計〜文章化まで一括）
  ├─ news/monthly/YYYY-MM-first-half.md または -second-half.md を組み立て
  └─ GitHub Contents API（PUT）でコミット・push
```

日次版と違い、月2回しか動かないルーティンなので、**GAS側の日付判定ロジックが正確であることが最重要**。ここを間違えると「不要な日にGemini APIを呼んでコストを無駄にする」「必要な日に呼ばれず月次まとめが欠落する」の両方のリスクがある。

## 1. GAS側での対象日判定（Gemini呼び出し前に必ず行う）

```javascript
function getMonthlyMode_() {
  var today = Utilities.formatDate(new Date(), "Asia/Tokyo", "yyyy-MM-dd");
  var day = parseInt(Utilities.formatDate(new Date(), "Asia/Tokyo", "dd"), 10);

  if (day === 15) {
    return { mode: "first-half", targetStart: 1, targetEnd: 15 };
  }
  if (day >= 28 && day <= 31) {
    var tomorrow = new Date();
    tomorrow.setDate(tomorrow.getDate() + 1);
    var tomorrowDay = parseInt(Utilities.formatDate(tomorrow, "Asia/Tokyo", "dd"), 10);
    if (tomorrowDay === 1) {
      // 今日が本当の月末日
      return { mode: "second-half", targetStart: 16, targetEnd: day };
    }
    return null; // まだ月末ではない
  }
  return null; // 対象日ではない
}
```

- **毎月15日** → 「前半まとめ」（1日〜15日分）
- **月末日のみ**（28〜31日のうち「翌日が1日」になる日）→ 「後半まとめ」（16日〜月末日分）
- それ以外の日は`null`を返し、**Gemini APIを呼ばずに即終了**する。ここがコスト管理の肝。

Claude Code版はこの判定をトリガーのcron（UTC基準で14日・27〜30日に発火）と組み合わせて実行時に行っていたが、GAS版は`ScriptApp`のトリガーを**JSTベースの日次トリガー（毎日1回）**にして、上記関数で「今日は対象日か」を判定する方式が最もシンプル。

## 2. GAS側で事前に用意してプロンプトに埋め込むコンテキスト

| プレースホルダ | 取得方法 |
|---|---|
| `{{TARGET_MONTH}}` | 対象月（例：`2026-09`） |
| `{{TARGET_RANGE}}` | 対象期間の表記（例：`9/1〜9/15`） |
| `{{MODE_LABEL}}` | `前半`または`後半` |
| `{{DAILY_ARTICLES}}` | 対象期間に該当する`news/YYYY-MM-DD.md`を**全て**GitHub Contents APIで取得し、日付順に連結したもの（各ファイルの本文をそのまま含める。要約は渡さず、生の記事を渡してGemini自身に集計させる） |
| `{{ISSUE_COUNT}}` | 対象期間の号数（ファイル数） |
| `{{PREVIOUS_SUMMARY_EXAMPLE}}` | `news/monthly/2026-08-summary.md`の内容（フォーマット見本として毎回埋め込む） |

## 3. プロンプト（1回で完結）

```
あなたは社労士・行政書士向けニュースメディアの編集者です。以下の{{TARGET_RANGE}}（{{MODE_LABEL}}分、全{{ISSUE_COUNT}}号）の日次記事をすべて読み、月次まとめ（{{MODE_LABEL}}まとめ）を作成してください。

【対象月】{{TARGET_MONTH}}（{{MODE_LABEL}}まとめ、対象期間：{{TARGET_RANGE}}）

【対象期間の日次記事（全文）】
{{DAILY_ARTICLES}}

【絶対厳守のルール】
1. **実際にここに含まれる記事の内容だけを根拠にすること。** 憶測で数字・話題・傾向を作らない。件数や割合を書く場合は、実際に上記記事を数えた結果と一致していること。
2. 記事に書かれていない外部の事実（ここに含まれない別の日の記事や、一般的な労務知識）を新たに付け加えない。あくまで「この期間に何が取り上げられたか」の集計・整理に徹する。
3. コラムやスカッと労働判例も含めて集計対象とする（ニュース記事と区別せず、期間全体の傾向として扱ってよい）。

【出力フォーマット（この構成・見出しレベルを厳守。以下は8月前半分の実例）】
{{PREVIOUS_SUMMARY_EXAMPLE}}

上記の実例と同じ構成で、{{TARGET_MONTH}}（{{MODE_LABEL}}）版を作成してください：
- タイトル：`# 月次まとめ：{{TARGET_MONTH}}〇〇（{{TARGET_RANGE}}、全{{ISSUE_COUNT}}号）`
- 冒頭に集計対象の号を明記（`*集計対象：news/{{TARGET_MONTH}}-XX.md 〜 news/{{TARGET_MONTH}}-YY.md（全{{ISSUE_COUNT}}号・のべN記事）*`）
- `## 📊 ざっくり傾向`：1〜2文で全体の傾向をタメ口でまとめる
- `## ①②③...` テーマ別セクション（2〜4個程度）：各テーマに絵文字見出し＋実際に扱った記事の箇条書き（日付付き）＋「顧問先への示唆」という一言コメント
- `## 🗓️ 今後の重要締切`：実際の記事中で言及されていた締切・施行日のみをテーブルにまとめる（無ければこのセクション自体を省略）
- `## 💬 一言メモ`：期間全体を振り返る一言（タメ口、次回への視点も添える）
- 末尾に注記：`*このまとめは news/{{TARGET_MONTH}}-XX.md 〜 news/{{TARGET_MONTH}}-YY.md の内容から作成しています。〜*`（{{MODE_LABEL}}が「前半」なら「後半分は次回の月次まとめに含まれる予定です」、「後半」なら「来月分は次回の月次まとめでお届けします」等、状況に応じた一文にする）

【出力】
上記フォーマットの本文だけを出力してください。前置き・後書きの説明文は不要です。
```

## 4. GitHubへの保存（GAS側の指針）

- 前半：`news/monthly/{{TARGET_MONTH}}-first-half.md`
- 後半：`news/monthly/{{TARGET_MONTH}}-second-half.md`
- GitHub Contents API（`PUT /repos/harubaru74-collab/roumu-news/contents/{path}`、`branch: "claude/routine-djkjlu"`）でコミット。
- コミットメッセージ例：`Add {{TARGET_MONTH}} {{MODE_LABEL}} monthly summary (Gemini/GAS)`
- **アーカイブページへの反映は不要**：既存の`.github/workflows/build-archive.yml`（`news/**`の変更をトリガーに動く）が`news/monthly/*.md`を自動的に拾ってページに組み込む。GAS側は`news/monthly/`配下にファイルを置くだけでよい。

## 5. 移行時に必ず確認すべきこと（品質担保）

日次版（`ROUTINE-GEMINI.md`セクション6）と共通する点に加え、月次まとめ特有の確認項目：

1. **対象日判定の正確性が最優先**：実装後、まず本番トリガーを仕込む前に、過去の日付をハードコードして`getMonthlyMode_()`関数だけを何日か分テストし、15日・月末日（28〜31日いずれか）・それ以外の日で正しく`first-half`/`second-half`/`null`を返すか確認する。ここを間違えると「月次まとめが永遠に作られない」または「毎日Gemini APIを無駄に呼ぶ」という2つの失敗モードがある。
2. **集計の正確性**：Geminiが実際の記事本文を数え間違えていないか（号数・記事数が実際と一致するか）をサンプルで確認する。プロンプトに全文を渡しているとはいえ、長文の集計はLLMが苦手な場合があるので、可能ならGAS側で号数・記事数だけは機械的に事前計算し、プロンプトの`{{ISSUE_COUNT}}`等に正確な値を渡す（Geminiに数えさせない）ようにするとより安全。
3. **入力トークン量**：対象期間が最大15日分（前半）または16日分（後半）の全記事本文をまるごとプロンプトに含めるため、日次版より入力が長くなる。Gemini APIのコンテキストウィンドウ内に収まるか、また料金への影響を事前に試算しておく。
4. **フォーマットの再現度**：`news/monthly/2026-08-summary.md`と読み比べ、見出しレベル・絵文字・テーブル構造が崩れていないか確認する。

## 6. Claude側トリガーの現状（2026-09-05時点）

Claude Code側の「roumu-news 月次まとめ」トリガー（`trig_01FxgKHVTNXLEQMQ7g45hGpy`）は、GAS移行に伴い**無効化済み**（削除はしていないので、GAS側に不具合があった場合はいつでも再有効化して暫定復旧できる）。日次のGitHub保存トリガー・朝刊/夜刊の配信トリガーも同様に無効化済み。GAS側の月次まとめが安定稼働するまでは、`news/monthly/`が更新されない月が発生しうる点に留意すること。
