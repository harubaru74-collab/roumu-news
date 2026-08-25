#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
roumu-news アーカイブページ自動ビルドスクリプト

news/*.md（日次）と news/monthly/*.md（月次まとめ）を読み込み、
archive/shell.html を土台にして、静的なアーカイブHTML（docs/index.html）を組み立てる。

このスクリプトはClaudeを一切使わない。GitHub Actionsから毎晩自動実行され、
GitHub Pagesがそのままdocs/を公開する（詳しくは archive/AUTOBUILD.md 参照）。

変換ルールは archive/BUILD.md（旧・Claude手動運用時代の仕様書）に準拠。
"""
import glob
import html
import os
import re
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NEWS_DIR = os.path.join(REPO_ROOT, "news")
MONTHLY_DIR = os.path.join(NEWS_DIR, "monthly")
SHELL_PATH = os.path.join(REPO_ROOT, "archive", "shell.html")
OUT_PATH = os.path.join(REPO_ROOT, "docs", "index.html")

OLD_FORMAT_DATE = "2026-08-06"

MONTH_NAMES_JA = "月"


def esc(s):
    return html.escape(s or "", quote=False)


def inline_md(s):
    """HTMLエスケープした上で、**bold** だけ <strong> に変換する。"""
    s = esc(s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    return s


def strip_number_prefix(heading):
    """見出し先頭の丸数字・空白を取り除く（issue-headline/issue-sub用）。"""
    return re.sub(r"^[①-⑳〇0-9]+\s*", "", heading).strip()


# ---------------------------------------------------------------------------
# 日次記事（news/YYYY-MM-DD.md）のパース
# ---------------------------------------------------------------------------

def parse_glossary(rest):
    m = re.match(r"^\s*>\s*📖\s*\*\*用語解説：(.+?)\*\*\s*\n((?:>.*(?:\n|$))*)", rest)
    if not m:
        return "", rest
    title = m.group(1).strip()
    body_lines = []
    for line in m.group(2).split("\n"):
        line = line.strip()
        if line.startswith(">"):
            line = line[1:].strip()
        if line:
            body_lines.append(line)
    body = " ".join(body_lines)
    html_out = (
        f'<div class="glossary"><strong>用語解説：{inline_md(title)}</strong>'
        f'<br />{inline_md(body)}</div>'
    )
    return html_out, rest[m.end():].lstrip("\n")


def parse_body(rest):
    m = re.match(
        r"^\*\*(何が起きた？|どういう話？)\*\*\s*\n(.*?)"
        r"(?=\n\*\*うちの仕事にどう関係する？\*\*|\Z)",
        rest,
        re.DOTALL,
    )
    if not m:
        return "", rest
    heading, para = m.group(1), m.group(2).strip()
    html_out = f"<h4>{heading}</h4><p>{inline_md(para)}</p>"
    return html_out, rest[m.end():].lstrip("\n")


def parse_todo(rest):
    m = re.match(
        r"^\*\*うちの仕事にどう関係する？\*\*\s*\n((?:- \[ \].*(?:\n|$))+)", rest
    )
    if not m:
        return "", rest
    items = re.findall(r"- \[ \]\s*(.+)", m.group(1))
    lis = "".join(
        f"<li><input type=\"checkbox\" disabled />{inline_md(i)}</li>" for i in items
    )
    html_out = f'<h4>うちの仕事にどう関係する？</h4><ul class="todo">{lis}</ul>'
    return html_out, rest[m.end():].lstrip("\n")


def parse_opinion_table(rest):
    m = re.match(
        r"^\*\*立場によって意見が分かれそうなポイント\*\*\s*\n\n?"
        r"\|.*\|\s*\n\|[-\s|]+\|\s*\n"
        r"((?:\|.*\|\s*(?:\n|$))+)",
        rest,
    )
    if not m:
        return "", rest
    rows = []
    for line in m.group(1).strip("\n").split("\n"):
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) >= 2:
            rows.append((cells[0], cells[1]))
    trs = "".join(
        f"<tr><th>{inline_md(a)}</th><td>{inline_md(b)}</td></tr>" for a, b in rows
    )
    html_out = (
        f'<h4>立場によって意見が分かれそうなポイント</h4>'
        f'<table class="opinion-table">{trs}</table>'
    )
    return html_out, rest[m.end():].lstrip("\n")


def parse_source(rest):
    m = re.search(
        r"\*\*🔗\s*(情報源|参考)\*\*\s*[：:]\s*\[(.+?)\]\((\S+?)\)", rest
    )
    if not m:
        return ""
    label, link_text, url = m.group(1), m.group(2), m.group(3)
    return (
        f'<p class="source-line">🔗 {label}：'
        f'<a href="{esc(url)}" target="_blank" rel="noopener">{inline_md(link_text)}</a></p>'
    )


def build_article_html(block):
    lines = block.strip("\n").split("\n")
    heading = lines[0].strip()
    rest = "\n".join(lines[1:]).strip("\n")

    glossary_html, rest = parse_glossary(rest)
    body_html, rest = parse_body(rest)
    todo_html, rest = parse_todo(rest)
    table_html, rest = parse_opinion_table(rest)
    source_html = parse_source(rest)

    parts = [f"<h3>{inline_md(heading)}</h3>", glossary_html, body_html, todo_html, table_html, source_html]
    return '<article class="article">' + "".join(p for p in parts if p) + "</article>", heading


def extract_article_blocks(text):
    # H1タイトル行と直後の --- を除去
    body = re.sub(r"^#[^\n]*\n+---\n+", "", text, count=1)
    # 末尾の --- と斜体注記を除去
    body = re.sub(r"\n+---\s*\n+\*[^\n]*\*\s*$", "", body, flags=re.DOTALL).strip()
    parts = re.split(r"\n##\s+", "\n" + body)
    parts = [p for p in parts if p.strip()]
    blocks = []
    for p in parts:
        p = re.sub(r"\n+---\s*$", "", p.strip())
        blocks.append(p)
    return blocks


def parse_day_file(path):
    text = open(path, encoding="utf-8").read()
    blocks = extract_article_blocks(text)
    articles = []
    for b in blocks:
        try:
            article_html, heading = build_article_html(b)
        except Exception as e:  # noqa: BLE001 - ビルドを止めないためのフォールバック
            print(f"  [WARN] {os.path.basename(path)}: 記事のパースに失敗しました ({e})", file=sys.stderr)
            heading = b.split("\n", 1)[0].strip()
            article_html = f'<article class="article"><h3>{inline_md(heading)}</h3><p class="source-line">（自動変換に失敗した記事です。手動確認が必要）</p></article>'
        articles.append((heading, article_html))
    return articles


# ---------------------------------------------------------------------------
# 旧フォーマット（2026-08-06のみ）
# ---------------------------------------------------------------------------

OLD_FORMAT_ISSUE_BODY = """
        <p class="old-format-note">※ この号は初期フォーマット（要約／実務影響／賛否両論の3段構成）で配信されたものです。第2号以降、記事ごとに用語解説・実務ToDo・立場別意見表を備えた現在の形式に更新されました。</p>

        <article class="article">
          <h3>① ニュースの要約</h3>
          <ul class="flat-list">
            <li><strong>技能実習生への監督指導、違反率71.7%に</strong><br />東北6労働局が令和6年に実施した技能実習実施機関への監督指導結果を公表。実施事業場数836件（令和元年以降で最多）のうち71.7%（599事業場）で労働基準関係法令違反を確認。</li>
            <li><strong>派遣の同一労働同一賃金、労使協定の"結び直し忘れ"が急増</strong><br />派遣元事業主が労使協定方式を採用する際に必要な協定の更新（結び直し）を失念するケースが相次ぎ、愛知労働局の是正指導件数は前年比6割増。</li>
            <li><strong>社会保険労務士会の会費引き上げが決定</strong><br />月額300円の値上げが決定（報道ベース。適用開始時期は原典で要確認）。</li>
            <li><strong>社会保険の適用要件、2026年10月に賃金要件撤廃</strong><br />短時間労働者への社会保険適用拡大に関し、2026年10月から「賃金月額8.8万円以上」の要件が撤廃される予定。企業規模要件・週所定労働時間要件は残る見込み。</li>
            <li><strong>最低賃金1500円、政府が「2030年代前半」の早期達成方針を明確化</strong></li>
            <li><strong>労働基準法の抜本改正、2026年通常国会への提出は見送り</strong><br />改正の方向性自体は維持されているが、法案提出時期は未定。2027年以降を見据えた検討が続く。</li>
            <li><strong>高年齢労働者の労災防止対策、2026年4月より努力義務化</strong>（施行済み・継続対応事項として記載）</li>
          </ul>
        </article>

        <article class="article">
          <h3>② 現職（社労士・行政書士業務）への影響と対応</h3>
          <p><strong>技能実習・特定技能関連の監督指導強化</strong><br />外国人材受入れ企業を顧問先に持つ場合、実習実施状況・36協定・賃金台帳の整備状況を年内に点検しておく必要性が高まっている。技能実習法から育成就労制度への移行期でもあり、監督指導の重点は「移行後も変わらない」と見て、顧問先への注意喚起（労働時間管理・割増賃金・寮費控除の適正性）を早めに行うのが望ましい。</p>
          <p><strong>派遣先・派遣元双方の労使協定チェック</strong><br />労使協定方式を採用する派遣元の顧問先がある場合、協定の有効期間・改定タイミングを顧問先任せにせず、事務所側でリマインド管理する仕組み（更新月のカレンダー化）を持つと差別化になる。派遣先均等・均衡方式との使い分けの再説明も需要が見込める。</p>
          <p><strong>社会保険適用拡大（2026年10月）への対応</strong><br />賃金要件撤廃により新たに加入対象となるパート・アルバイトが発生する顧問先が想定される。対象者洗い出し・被扶養者からの切替え説明・保険料試算は8〜9月中に前倒しで着手すべき業務。</p>
          <p><strong>会費値上げは事務所運営コストの微増要因</strong><br />経営への影響は軽微だが、他の法定費用改定と合わせて年次の顧問料改定タイミングで説明材料として活用できる。</p>
          <p><strong>労基法改正の見送りは「様子見」で正解</strong><br />2026年通常国会への提出見送りにより、就業規則・36協定の抜本的な様式変更は当面不要。ただし方向性は継続審議中のため、顧問先への「今すぐ対応不要、ただし動向は継続ウォッチ」という説明が適切。</p>
        </article>

        <article class="article">
          <h3>③ 賛否両論の視点</h3>
          <div class="stance-block">
            <h5>技能実習の監督強化について</h5>
            <ul>
              <li>賛成側：違反率7割超という実態を踏まえれば、監督強化は労働者保護の観点で妥当。</li>
              <li>慎重・反対側：人手不足に悩む中小事業者からは「摘発偏重で、労務管理体制構築への行政支援が不足している」との声も。</li>
            </ul>
          </div>
          <div class="stance-block">
            <h5>最低賃金1500円・2030年代前半達成方針</h5>
            <ul>
              <li>賛成側：物価上昇や地方の人材流出対策として、賃上げの道筋を早期に示すことは労働者・地方経済双方にプラス。</li>
              <li>慎重・反対側：中小企業・小規模事業者からは急激な人件費上昇への対応力への懸念が根強い。</li>
            </ul>
          </div>
          <div class="stance-block">
            <h5>社会保険適用拡大（賃金要件撤廃）</h5>
            <ul>
              <li>賛成側：非正規雇用者の将来的な年金・医療保障の充実につながる。</li>
              <li>慎重・反対側：手取り減を懸念する労働者本人の就業調整行動がむしろ強まる可能性も。</li>
            </ul>
          </div>
        </article>
""".strip("\n")


# ---------------------------------------------------------------------------
# 月次まとめ（news/monthly/*.md）のパース（簡易マークダウン変換）
# ---------------------------------------------------------------------------

def monthly_table_to_html(lines):
    rows = [l for l in lines if l.strip().startswith("|")]
    if len(rows) < 2:
        return ""
    data_rows = rows[2:]  # ヘッダー行・区切り行を捨てる（既存デザインに合わせる）
    trs = []
    for r in data_rows:
        cells = [c.strip() for c in r.strip().strip("|").split("|")]
        if len(cells) >= 2:
            trs.append(f"<tr><th>{inline_md(cells[0])}</th><td>{inline_md(cells[1])}</td></tr>")
    if not trs:
        return ""
    return "<table>" + "".join(trs) + "</table>"


def monthly_body_to_html(text):
    # H1見出し行を除去（headline用に別途使う）
    text = re.sub(r"^#[^\n]*\n+", "", text, count=1).strip()
    lines = text.split("\n")
    out = []
    buf_list = []
    i = 0

    def flush_list():
        if buf_list:
            lis = "".join(f"<li>{inline_md(x)}</li>" for x in buf_list)
            out.append(f"<ul>{lis}</ul>")
            buf_list.clear()

    while i < len(lines):
        line = lines[i].rstrip()
        stripped = line.strip()

        if not stripped:
            flush_list()
            i += 1
            continue

        if stripped == "---":
            flush_list()
            i += 1
            continue

        if re.match(r"^#{2,4}\s+", stripped):
            flush_list()
            heading = re.sub(r"^#{2,4}\s+", "", stripped)
            out.append(f"<h4>{inline_md(heading)}</h4>")
            i += 1
            continue

        if stripped.startswith("|"):
            flush_list()
            table_lines = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                table_lines.append(lines[i])
                i += 1
            out.append(monthly_table_to_html(table_lines))
            continue

        if stripped.startswith("- "):
            buf_list.append(stripped[2:].strip())
            i += 1
            continue

        if stripped.startswith("*") and stripped.endswith("*") and len(stripped) > 1:
            flush_list()
            note = stripped.strip("*").strip()
            out.append(f'<p class="monthly-note">{inline_md(note)}</p>')
            i += 1
            continue

        # 通常の段落（連続する行は1つの段落としてまとめる）
        flush_list()
        para_lines = [stripped]
        i += 1
        while i < len(lines) and lines[i].strip() and not re.match(r"^(#{2,4}\s+|\||- |---$)", lines[i].strip()):
            para_lines.append(lines[i].strip())
            i += 1
        out.append(f"<p>{inline_md(' '.join(para_lines))}</p>")

    flush_list()
    return "".join(out)


def parse_monthly_file(path):
    text = open(path, encoding="utf-8").read()
    first_line = text.split("\n", 1)[0]
    headline = re.sub(r"^#\s*", "", first_line).strip()

    m = re.search(r"全(\d+)号", text)
    issue_n = m.group(1) if m else "?"
    m2 = re.search(r"のべ(\d+)記事", text)
    article_n = m2.group(1) if m2 else None
    sub = f"全{issue_n}号" + (f"・のべ{article_n}記事から傾向を分析" if article_n else "")

    body_html = monthly_body_to_html(text)

    fname = os.path.basename(path)
    slug = re.sub(r"\.md$", "", fname)

    return f'''<details class="monthly" id="monthly-{esc(slug)}">
      <summary>
        <span class="monthly-badge">📊 月次まとめ</span>
        <span>
          <span class="monthly-headline">{inline_md(headline)}</span>
          <span class="monthly-sub">{inline_md(sub)}</span>
        </span>
        <span class="issue-toggle" aria-hidden="true">▾</span>
      </summary>
      <div class="monthly-body">
{body_html}
      </div>
    </details>'''


# ---------------------------------------------------------------------------
# メイン
# ---------------------------------------------------------------------------

def month_label(y, mo):
    return f"{y}年{int(mo)}{MONTH_NAMES_JA}"


def main():
    day_files = sorted(
        f for f in glob.glob(os.path.join(NEWS_DIR, "*.md"))
        if re.match(r"\d{4}-\d{2}-\d{2}\.md$", os.path.basename(f))
    )
    if not day_files:
        print("news/*.md が見つかりません。中断します。", file=sys.stderr)
        sys.exit(1)

    # 号数は日付の昇順（古い方が第1号）で採番する
    numbered = []
    for idx, path in enumerate(day_files, start=1):
        fname = os.path.basename(path)
        date_str = fname[:10]
        numbered.append((idx, date_str, path))

    oldest_date = numbered[0][1]
    y0, mo0, d0 = oldest_date.split("-")
    issue_range_label = f"創刊 {y0}年{int(mo0)}月{int(d0)}日"
    issue_count = len(numbered)

    # 月次まとめを month_key ("YYYY-MM") ごとに集めておく（新しい方を上に）
    monthly_by_month = {}
    if os.path.isdir(MONTHLY_DIR):
        for path in sorted(glob.glob(os.path.join(MONTHLY_DIR, "*.md")), reverse=True):
            fname = os.path.basename(path)
            m = re.match(r"(\d{4})-(\d{2})", fname)
            if not m:
                continue
            key = f"{m.group(1)}-{m.group(2)}"
            monthly_by_month.setdefault(key, []).append(parse_monthly_file(path))

    # 新しい日付が先に来るよう降順に並べ直して出力する
    numbered_desc = list(reversed(numbered))

    out_blocks = []
    prev_month_key = None
    for i, (issue_no, date_str, path) in enumerate(numbered_desc):
        y, mo, d = date_str.split("-")
        month_key = f"{y}-{mo}"

        if month_key != prev_month_key:
            # この月の月次まとめを月区切りの直前に挿入
            for monthly_html in monthly_by_month.get(month_key, []):
                out_blocks.append(monthly_html)
            out_blocks.append(f'<div class="month-divider">{month_label(y, mo)}</div>')
            prev_month_key = month_key

        is_open = " open" if i == 0 else ""

        if date_str == OLD_FORMAT_DATE:
            headline = "創刊号：技能実習の監督強化から最低賃金1500円方針まで、7つの動き"
            sub = "旧フォーマット（3段構成）での初回配信　全7項目"
            search_kw = "技能実習 監督指導 違反 東北 派遣 同一労働同一賃金 労使協定 社会保険労務士会 会費 社会保険適用拡大 賃金要件撤廃 最低賃金1500円 労働基準法改正 高年齢労働者 労災防止"
            body_html = OLD_FORMAT_ISSUE_BODY
            badge = f"創刊号 {int(mo)}/{int(d)}"
        else:
            articles = parse_day_file(path)
            n = len(articles)
            headline = strip_number_prefix(articles[0][0]) if articles else "（記事なし）"
            sub = "／".join(strip_number_prefix(h) for h, _ in articles) + f"　全{n}本"
            search_kw = " ".join(strip_number_prefix(h) for h, _ in articles)
            body_html = "\n".join(a_html for _, a_html in articles)
            badge = f"第{issue_no}号 {int(mo)}/{int(d)}"

        out_blocks.append(
            f'<details class="issue" id="issue-{date_str}"{is_open} data-search="{esc(search_kw)}">\n'
            f'      <summary>\n'
            f'        <span class="issue-badge">{esc(badge)}</span>\n'
            f'        <span>\n'
            f'          <span class="issue-headline">{inline_md(headline)}</span>\n'
            f'          <span class="issue-sub">{inline_md(sub)}</span>\n'
            f'        </span>\n'
            f'        <span class="issue-toggle" aria-hidden="true">▾</span>\n'
            f'      </summary>\n'
            f'      <div class="issue-body">\n'
            f'{body_html}\n'
            f'      </div>\n'
            f'    </details>'
        )

    issues_html = "\n\n    ".join(out_blocks)

    shell = open(SHELL_PATH, encoding="utf-8").read()
    # shell.html先頭のドキュメント用HTMLコメント（人間向けの説明。中に
    # "ISSUES_GO_HERE" という文字列が例示として出てくるため、置換前に必ず除去する）
    shell = re.sub(r"^\s*<!--.*?-->\s*\n", "", shell, count=1, flags=re.DOTALL)
    shell = shell.replace("<!-- ISSUES_GO_HERE -->", issues_html)
    shell = shell.replace("{{ISSUE_RANGE}}", issue_range_label)
    shell = shell.replace("全{{ISSUE_COUNT}}号", f"全{issue_count}号")
    shell = shell.replace("{{ISSUE_COUNT}}", str(issue_count))

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        f.write(shell)

    print(f"OK: {issue_count}号を {OUT_PATH} に出力しました（創刊={issue_range_label}）")


if __name__ == "__main__":
    main()
