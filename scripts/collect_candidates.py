#!/usr/bin/env python3
"""
候補記事の自動収集スクリプト（AI不使用・純粋なPython/RSS収集）。

目的：
  深夜2:00のClaudeルーティンが毎回Web検索で1から探している負荷を減らすため、
  Google News RSS（無料・APIキー不要）を使って候補記事のタイトル・リンク・出典・
  掲載日を先に集めておき、`staging/candidates/YYYY-MM-DD.md` に書き出す。

重要な注意（Claude向け）：
  このファイルはAIを一切使わず機械的に集めた「リード（手がかり）」に過ぎない。
  タイトル・掲載日はRSS由来の情報をそのまま転記しているだけで、正確性・実在性・
  記事の中身は一切検証していない。ROUTINE.mdの非捏造ルール・鮮度チェックは
  従来通りClaude側で必ず行うこと（このスクリプトはその手前の下ごしらえでしかない）。

実行方法：
  python3 scripts/collect_candidates.py
  （標準ライブラリのみで動作。pip install不要）
"""

from __future__ import annotations

import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")
FRESHNESS_DAYS = 7
REQUEST_TIMEOUT = 15
SLEEP_BETWEEN_REQUESTS = 0.6
MAX_ITEMS_PER_QUERY = 6
USER_AGENT = (
    "Mozilla/5.0 (compatible; roumu-news-candidate-collector/1.0; "
    "+https://github.com/harubaru74-collab/roumu-news)"
)

# (表示名, [検索クエリ...], 鮮度チェックが必要か)
# クエリの内容はROUTINE.mdに書かれている検索の切り口をそのまま踏襲している。
CATEGORIES: list[tuple[str, list[str], bool]] = [
    (
        "一般ニュース",
        ["労務 ニュース", "人事労務 最新ニュース", "社会保険 ニュース"],
        True,
    ),
    (
        "官公庁発表",
        ["厚生労働省 報道発表", "都道府県労働局 発表"],
        True,
    ),
    (
        "業種特化",
        [
            "介護 人手不足 ニュース",
            "建設業 労務 ニュース",
            "IT業界 働き方 ニュース",
            "小売 サービス業 労務 ニュース",
        ],
        True,
    ),
    (
        "制度・手続き",
        ["助成金 申請 締切", "労働保険 社会保険 手続き 変更"],
        True,
    ),
    (
        "専門メディア",
        ["労働新聞社", "SmartHR Mag 人事労務", "Manegy 人事", "かいけつ 人事労務"],
        True,
    ),
    (
        "地域トピック",
        ["労働局 発表 労務", "自治体 労務 ニュース"],
        True,
    ),
    (
        "コラム候補（判例解説・実務コラム等、鮮度不問）",
        [
            "労働判例 解説 わかりやすく",
            "社労士コラム 実務",
            "人事労務 あるある",
            "働き方 コラム 話題",
            "労務 勘違い よくある",
            "職場 トラブル 相談",
            "退職金 判決 地裁",
        ],
        False,
    ),
    (
        "スカッと判例候補（労働紛争・訴訟、鮮度不問・勝敗不問）",
        [
            "労働審判 訴訟 話題",
            "解雇 裁判 係争中",
            "未払い残業代 訴訟 最新",
            "パワハラ 訴訟 判決",
            "労働組合 団体交渉 争い",
        ],
        False,
    ),
]


@dataclass
class Candidate:
    title: str
    source: str
    link: str
    pub_date: datetime | None

    def dedup_key(self) -> str:
        # タイトル末尾の " - 出典名" を落とし、空白を除去して大まかに正規化する
        base = re.sub(r"\s*-\s*[^-]+$", "", self.title)
        return re.sub(r"\s+", "", base).lower()


def fetch_rss(query: str) -> list[Candidate]:
    url = "https://news.google.com/rss/search?" + urllib.parse.urlencode(
        {"q": query, "hl": "ja", "gl": "JP", "ceid": "JP:ja"}
    )
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            body = resp.read()
    except (urllib.error.URLError, TimeoutError) as e:
        print(f"  [警告] 取得失敗: {query!r} ({e})", file=sys.stderr)
        return []

    try:
        root = ET.fromstring(body)
    except ET.ParseError as e:
        print(f"  [警告] XMLパース失敗: {query!r} ({e})", file=sys.stderr)
        return []

    out: list[Candidate] = []
    for item in root.findall("./channel/item")[:MAX_ITEMS_PER_QUERY]:
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        if not title or not link:
            continue
        source_el = item.find("source")
        source = (source_el.text or "").strip() if source_el is not None else ""
        pub_date_raw = item.findtext("pubDate")
        pub_date = None
        if pub_date_raw:
            try:
                pub_date = parsedate_to_datetime(pub_date_raw)
                if pub_date.tzinfo is None:
                    pub_date = pub_date.replace(tzinfo=timezone.utc)
            except (TypeError, ValueError):
                pub_date = None
        out.append(Candidate(title=title, source=source, link=link, pub_date=pub_date))
    return out


def collect_category(queries: list[str], need_fresh: bool, now_utc: datetime) -> list[Candidate]:
    cutoff = now_utc - timedelta(days=FRESHNESS_DAYS)
    seen: set[str] = set()
    results: list[Candidate] = []
    for q in queries:
        print(f"  検索中: {q}")
        for c in fetch_rss(q):
            key = c.dedup_key()
            if not key or key in seen:
                continue
            if need_fresh and c.pub_date is not None and c.pub_date < cutoff:
                continue
            seen.add(key)
            results.append(c)
        time.sleep(SLEEP_BETWEEN_REQUESTS)
    return results


def format_candidate(c: Candidate) -> str:
    date_str = c.pub_date.astimezone(JST).strftime("%Y-%m-%d %H:%M") if c.pub_date else "掲載日不明"
    source = c.source or "出典不明"
    return f"- **{c.title}**（{source}, {date_str}）\n  {c.link}"


def main() -> None:
    now_utc = datetime.now(timezone.utc)
    today_jst = datetime.now(JST).strftime("%Y-%m-%d")

    lines: list[str] = []
    lines.append(f"# 候補記事リスト（自動収集・AI不使用） {today_jst}")
    lines.append("")
    lines.append(
        "> ⚠️ これはGitHub ActionsがGoogle News RSSから機械的に集めた**未検証のリード一覧**です。"
        "タイトル・掲載日・出典はRSSの情報をそのまま転記しており、内容の正確性・実在性は一切保証されていません。"
        "採用する場合は必ず実際の記事を確認（WebFetch等）してから執筆すること。"
        "非捏造ルール・鮮度チェック（直近1週間以内）はこれまで通りClaude側の責任で行うこと。"
        "ここに載っていない・不十分な場合は、従来通りWeb検索で補ってよい。"
    )
    lines.append("")

    total = 0
    for name, queries, need_fresh in CATEGORIES:
        print(f"[{name}]")
        items = collect_category(queries, need_fresh, now_utc)
        total += len(items)
        lines.append(f"## {name}")
        lines.append("")
        if not items:
            lines.append("（今回は候補が見つかりませんでした。Web検索でのフォールバックが必要です。）")
        else:
            for c in items:
                lines.append(format_candidate(c))
        lines.append("")

    out_dir = Path("staging/candidates")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{today_jst}.md"
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n書き出し完了: {out_path}（候補{total}件）")


if __name__ == "__main__":
    main()
