#!/usr/bin/env python3
"""支部長・支部長代行の本日出走状況と今後予定を機械取得してExcel化する。"""

from __future__ import annotations

import argparse
import concurrent.futures
import datetime as dt
import json
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.request
import zipfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable
from xml.etree import ElementTree as ET

from lxml import html
import xlsxwriter


KEIRIN_PROFILE = "https://www.keirin.jp/pc/racerprofile?snum={reg6}"
KEIRIN_TOP = "https://www.keirin.jp/pc/top"
WINTICKET_PROFILE = "https://www.winticket.jp/keirin/cyclist/{reg6}"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/142 Safari/537.36"

VENUES = {
    "函館", "青森", "いわき平", "弥彦", "前橋", "取手", "宇都宮", "大宮", "西武園", "京王閣", "立川",
    "松戸", "千葉", "川崎", "平塚", "小田原", "伊東", "静岡", "名古屋", "岐阜", "大垣", "豊橋",
    "富山", "松阪", "四日市", "福井", "奈良", "向日町", "和歌山", "岸和田", "玉野", "広島", "防府",
    "高松", "小松島", "高知", "松山", "小倉", "久留米", "武雄", "佐世保", "別府", "熊本",
}

VENUE_ALIASES = {
    "函": "函館", "青": "青森", "平": "いわき平", "弥": "弥彦", "前": "前橋", "取": "取手",
    "宇": "宇都宮", "宇都": "宇都宮", "宮": "大宮", "園": "西武園", "閣": "京王閣", "京王": "京王閣", "立": "立川", "戸": "松戸",
    "千": "千葉", "川": "川崎", "塚": "平塚", "原": "小田原", "伊": "伊東", "静": "静岡",
    "名": "名古屋", "岐": "岐阜", "垣": "大垣", "豊": "豊橋", "富": "富山", "松": "松阪",
    "四": "四日市", "井": "福井", "奈": "奈良", "向": "向日町", "向日": "向日町", "和": "和歌山", "岸": "岸和田", "岸和": "岸和田",
    "玉": "玉野", "広": "広島", "防": "防府", "高": "高松", "小松": "小松島", "知": "高知",
    "松山": "松山", "倉": "小倉", "久": "久留米", "武": "武雄", "佐世": "佐世保", "別": "別府",
    "熊": "熊本",
}

# 常勤役員は出走予定の確認対象外。名簿の変更時にも次回以降の自動更新で除外する。
EXCLUDED_OFFICER_NAMES = {
    "金古将人",
    "市川健太",
    "宮越大",
    "安田光義",
    # 名簿に使われる異体字「髙」も含めて除外する。
    "高田健一",
    "髙田健一",
}
ROLE_OVERRIDES = {"陶器一馬": "支部長"}

NS_MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
NS_REL_DOC = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
NS_REL_PKG = "http://schemas.openxmlformats.org/package/2006/relationships"


@dataclass
class Player:
    branch: str
    name: str
    registration_no: str
    role: str
    order: int
    vacancy: bool = False

    @property
    def reg6(self) -> str:
        return self.registration_no.zfill(6)


@dataclass
class Event:
    venue: str
    grade: str
    start: str
    end: str
    source_url: str


@dataclass
class Result:
    player: Player
    today_status: str = "unverified"
    today_text: str = "取得できず（要確認）"
    meeting: str = ""
    race: str = ""
    meeting_category: str = ""
    meeting_icon_url: str = ""
    upcoming: list[Event] = field(default_factory=list)
    ongoing: list[Event] = field(default_factory=list)
    keirin_url: str = ""
    winticket_url: str = ""
    keirin_updated_at: str = ""
    checked_at: str = ""
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def norm(value: str) -> str:
    return unicodedata.normalize("NFKC", value or "").replace("\u3000", " ").strip()


def compact(value: str) -> str:
    return re.sub(r"\s+", "", norm(value))


def clean_source_label(value: str) -> str:
    value = norm(value)
    value = re.split(r"[ァ-ヶー]", value, maxsplit=1)[0]
    return re.sub(r"\s+", "", value)


def col_index(cell_ref: str) -> int:
    letters = re.match(r"[A-Z]+", cell_ref).group(0)
    n = 0
    for ch in letters:
        n = n * 26 + ord(ch) - 64
    return n - 1


def read_first_sheet(path: Path) -> list[list[str]]:
    """openpyxlに依存せず、xlsx先頭シートを文字列行列として読む。"""
    ns = {"m": NS_MAIN, "r": NS_REL_DOC, "pr": NS_REL_PKG}
    with zipfile.ZipFile(path) as zf:
        strings: list[str] = []
        if "xl/sharedStrings.xml" in zf.namelist():
            root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
            strings = ["".join(si.itertext()) for si in root.findall("m:si", ns)]

        wb = ET.fromstring(zf.read("xl/workbook.xml"))
        first = wb.find("m:sheets", ns)[0]
        rel_id = first.attrib[f"{{{NS_REL_DOC}}}id"]
        rels = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
        target = next(r.attrib["Target"] for r in rels if r.attrib["Id"] == rel_id)
        sheet_path = target.lstrip("/") if target.startswith("/") else f"xl/{target}"
        sheet = ET.fromstring(zf.read(sheet_path))

        matrix: list[list[str]] = []
        for row in sheet.findall(".//m:sheetData/m:row", ns):
            row_num = int(row.attrib["r"])
            while len(matrix) < row_num:
                matrix.append([])
            values: dict[int, str] = {}
            for cell in row.findall("m:c", ns):
                idx = col_index(cell.attrib["r"])
                typ = cell.attrib.get("t")
                v = cell.find("m:v", ns)
                inline = cell.find("m:is", ns)
                text = ""
                if typ == "s" and v is not None:
                    text = strings[int(v.text)]
                elif typ == "inlineStr" and inline is not None:
                    text = "".join(inline.itertext())
                elif v is not None:
                    text = v.text or ""
                values[idx] = text
            width = max(values, default=-1) + 1
            matrix[row_num - 1] = [values.get(i, "") for i in range(width)]
        return matrix


def get_cell(row: list[str], index: int) -> str:
    return row[index] if index < len(row) else ""


def normalize_reg(value: str) -> str:
    value = norm(value).lstrip("'")
    if value.endswith(".0"):
        value = value[:-2]
    digits = re.sub(r"\D", "", value)
    return digits[-5:] if len(digits) >= 5 else digits


def extract_players(path: Path) -> list[Player]:
    rows = read_first_sheet(path)
    header_idx = -1
    indexes: dict[str, int] = {}
    for i, row in enumerate(rows):
        for j, value in enumerate(row):
            label = compact(value)
            if label.startswith("支部名"):
                indexes["branch"] = j
            elif label.startswith("支部長代行"):
                indexes["deputy"] = j
                indexes["deputy_reg"] = j + 1
            elif label.startswith("支部長") and "代行" not in label:
                indexes["chair"] = j
                indexes["chair_reg"] = j + 1
        if {"branch", "chair", "chair_reg", "deputy", "deputy_reg"} <= indexes.keys():
            header_idx = i
            break
    if header_idx < 0:
        raise ValueError("支部名・支部長・支部長代行の見出しを検出できませんでした。")

    players: list[Player] = []
    order = 0
    for row in rows[header_idx + 1 :]:
        branch = clean_source_label(get_cell(row, indexes["branch"]))
        if not branch:
            continue
        chair_name = clean_source_label(get_cell(row, indexes["chair"]))
        chair_reg = normalize_reg(get_cell(row, indexes["chair_reg"]))
        # 大阪支部の支部長行は一覧対象外とする。
        if branch != "大阪":
            if chair_name and len(chair_reg) == 5:
                if chair_name not in EXCLUDED_OFFICER_NAMES:
                    players.append(Player(branch, chair_name, chair_reg, "支部長", order))
                    order += 1
            else:
                players.append(Player(branch, "（支部長欠員）", "－", "支部長", order, True))
                order += 1

        deputy_name = clean_source_label(get_cell(row, indexes["deputy"]))
        deputy_reg = normalize_reg(get_cell(row, indexes["deputy_reg"]))
        if deputy_name and len(deputy_reg) == 5 and deputy_name not in EXCLUDED_OFFICER_NAMES:
            role = ROLE_OVERRIDES.get(deputy_name, "支部長代行")
            players.append(Player(branch, deputy_name, deputy_reg, role, order))
            order += 1
    return players


def fetch(url: str, timeout: int, attempts: int = 2) -> bytes:
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept-Language": "ja,en;q=0.8"})
            with urllib.request.urlopen(req, timeout=timeout) as res:
                return res.read()
        except Exception as exc:  # URL/SSL/timeoutをまとめて次試行へ
            last_error = exc
            if attempt + 1 < attempts:
                time.sleep(0.4 * (attempt + 1))
    raise RuntimeError(f"{type(last_error).__name__}: {last_error}")


def canonical_venue(value: str) -> str:
    value = compact(value)
    if value in VENUES:
        return value
    return VENUE_ALIASES.get(value, value)


def normalize_grade(value: str) -> str:
    value = compact(value).upper()
    replacements = {"FI": "F1", "FII": "F2", "GI": "G1", "GII": "G2", "GIII": "G3", "オール": "G1"}
    return replacements.get(value, value)


def parse_today_meeting_categories(raw: bytes) -> dict[str, tuple[str, str]]:
    """KEIRIN.JPトップの開催情報から、会場別の開催区分と公式アイコンを取得する。"""
    text = raw.decode("utf-8", "ignore")
    marker = "var pc0101_json ="
    start = text.find(marker)
    if start < 0:
        raise ValueError("KEIRIN.JPトップの開催情報を検出できません")
    payload, _ = json.JSONDecoder().raw_decode(text[start + len(marker):].lstrip())
    labels = {"ico_kaisai_8.png": "モーニング", "ico_kaisai_3.png": "ナイター", "ico_kaisai_5.png": "ミッドナイト"}
    categories: dict[str, tuple[str, str]] = {}
    for meeting in payload.get("RaceList", []):
        venue = canonical_venue(meeting.get("keirinjoName", ""))
        icon_path = meeting.get("KubunIconPath", "")
        icon_name = icon_path.rsplit("/", 1)[-1]
        if venue in VENUES and icon_name in labels:
            categories[venue] = (labels[icon_name], f"https://www.keirin.jp{icon_path}")
    return categories


def meeting_venue(meeting: str) -> str:
    value = compact(meeting)
    for venue in sorted(VENUES, key=len, reverse=True):
        if value.startswith(venue):
            return venue
    return ""


def infer_date(mmdd: str, base: dt.date) -> dt.date:
    month, day = map(int, mmdd.split("/"))
    year = base.year
    if month < base.month - 6:
        year += 1
    elif month > base.month + 6:
        year -= 1
    return dt.date(year, month, day)


def make_event(venue: str, grade: str, span: str, source_url: str, base: dt.date) -> Event | None:
    span = norm(span).replace("〜", "~").replace("～", "~").replace("-", "~")
    match = re.search(r"(\d{2}/\d{2})\s*~\s*(\d{2}/\d{2})", span)
    if not match:
        return None
    venue = canonical_venue(venue)
    grade = normalize_grade(grade)
    try:
        start = infer_date(match.group(1), base)
        end = infer_date(match.group(2), base)
        if end < start:
            end = dt.date(start.year + 1, end.month, end.day)
    except ValueError:
        return None
    return Event(venue, grade, start.isoformat(), end.isoformat(), source_url)


def parse_keirin(raw: bytes, url: str, base: dt.date) -> tuple[str, str, str, str, list[Event], list[str]]:
    """today_status, meeting, race, updated_at, future, warnings"""
    doc = html.fromstring(raw)
    page_text = " ".join(doc.text_content().split())
    warnings: list[str] = []

    updated = re.findall(r"20\d{2}/\d{2}/\d{2}\s+\d{2}:\d{2}\s*更新", page_text)
    updated_at = max(updated) if updated else ""

    today_status, meeting, race = "unverified", "", ""
    nodes = doc.xpath("//p[contains(normalize-space(.),'開催中のレース')]")
    if nodes:
        containers = nodes[0].xpath("ancestor::div[contains(concat(' ', normalize-space(@class), ' '), ' pad_t_10 ')][1]")
        block = containers[0] if containers else nodes[0].getparent()
        block_text = " ".join(block.text_content().split())
        if "現在、開催中のレースには出場しておりません" in block_text:
            today_status = "not_racing"
        else:
            title = norm(nodes[0].text_content()).replace("■開催中のレース", "").strip()
            match = re.search(r"(.+?)(F[12]|G[123])$", compact(title))
            if match:
                venue = canonical_venue(match.group(1))
                grade = normalize_grade(match.group(2))
                meeting = f"{venue}{grade}"
            tables = block.xpath(".//table")
            if tables:
                rows = tables[0].xpath(".//tr")
                if len(rows) >= 3:
                    dates = [norm(c.text_content()) for c in rows[1].xpath("./th|./td")]
                    cells = [norm(c.text_content()) for c in rows[2].xpath("./th|./td")]
                    target = base.strftime("%m/%d")
                    if target in dates:
                        idx = dates.index(target)
                        raw_race = cells[idx * 3] if idx * 3 < len(cells) else ""
                        raw_race = re.sub(r"ダイジェスト", "", raw_race).strip()
                        if raw_race and raw_race not in {"-", "－"}:
                            race = norm(raw_race).replace("/", " ")
                            today_status = "racing" if meeting else "unverified"
                        else:
                            today_status = "in_meeting_not_racing" if meeting else "unverified"
                    else:
                        # KEIRIN.JPは翌日開始の開催も「開催中」に先行表示する。
                        # 表示日がすべて基準日より後なら、本日は出走なしと確定できる。
                        try:
                            shown_dates = [infer_date(value, base) for value in dates if re.fullmatch(r"\d{2}/\d{2}", value)]
                        except ValueError:
                            shown_dates = []
                        if shown_dates and min(shown_dates) > base:
                            today_status = "not_racing"
                            meeting = ""
                            warnings.append(f"翌日以降の開催を先行表示: {min(shown_dates):%m/%d}開始")
                        else:
                            warnings.append(f"開催中欄に基準日{target}がありません")
    else:
        warnings.append("KEIRIN.JPの開催中欄を検出できません")

    future: list[Event] = []
    future_nodes = doc.xpath("//p[contains(normalize-space(.),'出場予定')]")
    if future_nodes:
        tables = future_nodes[0].getparent().xpath(".//table")
        # 個人ページに複数の予定表がある場合にも、掲載分をすべて取得する。
        for table in tables:
            for row in table.xpath(".//tbody/tr"):
                cells = [norm(c.text_content()) for c in row.xpath("./th|./td")]
                if len(cells) < 2:
                    continue
                vg = compact(cells[0])
                match = re.match(r"(.+?)(F[12]|G[123]|オール)$", vg)
                if match:
                    event = make_event(match.group(1), match.group(2), cells[1], url, base)
                    if event:
                        future.append(event)
    return today_status, meeting, race, updated_at, future, warnings


def parse_winticket(raw: bytes, url: str, base: dt.date) -> list[Event]:
    doc = html.fromstring(raw)
    heads = doc.xpath("//h2[normalize-space()='出場予定']")
    if not heads:
        return []
    sections = heads[0].xpath("ancestor::section[1]")
    root = sections[0] if sections else heads[0].getparent()
    events: list[Event] = []
    for anchor in root.xpath('.//a[contains(@href,"/racecard/")]'):
        text = norm(" ".join(anchor.text_content().split()))
        match = re.match(r"^(.+?)\s+(F[12]|G[123])\s*\(\s*(\d{2}/\d{2})\s*[～〜]\s*(\d{2}/\d{2})\s*\)$", text)
        if match:
            event = make_event(match.group(1), match.group(2), f"{match.group(3)}～{match.group(4)}", url, base)
            if event:
                events.append(event)
    return events


def event_key(event: Event) -> tuple[str, str, str]:
    return event.venue, event.start, event.end


def validate_events(events: Iterable[Event]) -> tuple[list[Event], list[str]]:
    valid: list[Event] = []
    warnings: list[str] = []
    for event in sorted(events, key=lambda e: (e.start, e.venue, e.grade)):
        if event.venue not in VENUES:
            warnings.append(f"競輪場名が不正: {event.venue}")
            continue
        if event.grade not in {"F1", "F2", "G1", "G2", "G3"}:
            warnings.append(f"グレードが不正: {event.venue}{event.grade}")
            continue
        start, end = dt.date.fromisoformat(event.start), dt.date.fromisoformat(event.end)
        if end < start or (end - start).days > 6:
            warnings.append(f"開催期間が不正: {event.venue}{event.grade} {event.start}-{event.end}")
            continue
        valid.append(event)

    for left, right in zip(valid, valid[1:]):
        if dt.date.fromisoformat(right.start) <= dt.date.fromisoformat(left.end):
            if event_key(left) != event_key(right):
                warnings.append(f"予定重複: {left.venue}と{right.venue}")
    return valid, warnings


def investigate(player: Player, base: dt.date, timeout: int, meeting_categories: dict[str, tuple[str, str]]) -> Result:
    now = dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat(timespec="seconds")
    if player.vacancy:
        return Result(player=player, today_status="vacancy", today_text="－", checked_at=now)

    result = Result(player=player, keirin_url=KEIRIN_PROFILE.format(reg6=player.reg6),
                    winticket_url=WINTICKET_PROFILE.format(reg6=player.reg6), checked_at=now)
    all_events: list[Event] = []

    try:
        raw = fetch(result.keirin_url, timeout)
        if player.reg6 not in raw.decode("utf-8", "ignore"):
            result.warnings.append("KEIRIN.JPページ内で登録番号を確認できません")
        status, meeting, race, updated, events, warnings = parse_keirin(raw, result.keirin_url, base)
        result.today_status, result.meeting, result.race = status, meeting, race
        result.keirin_updated_at = updated
        result.warnings.extend(warnings)
        all_events.extend(events)
    except Exception as exc:
        result.errors.append(f"KEIRIN.JP: {exc}")

    try:
        all_events.extend(parse_winticket(fetch(result.winticket_url, timeout), result.winticket_url, base))
    except Exception as exc:
        result.errors.append(f"WINTICKET: {exc}")

    # WINTICKETを優先して同一予定を統合
    merged: dict[tuple[str, str, str], Event] = {}
    for event in all_events:
        key = event_key(event)
        if key not in merged or "winticket.jp" in event.source_url:
            merged[key] = event
    events, warnings = validate_events(merged.values())
    result.warnings.extend(warnings)

    result.upcoming = [e for e in events if dt.date.fromisoformat(e.start) > base]
    # WINTICKETの予定情報は欠場・あっせん変更の反映が遅れることがあるため、
    # 当日の参加判定には使わない。開催中かどうかは KEIRIN.JP のみを正とする。
    result.ongoing = [e for e in events if dt.date.fromisoformat(e.start) <= base <= dt.date.fromisoformat(e.end)]

    if result.today_status == "racing":
        category = meeting_categories.get(meeting_venue(result.meeting))
        if category:
            result.meeting_category, result.meeting_icon_url = category
        result.today_text = f"★本日出走★ {result.meeting}「{result.race}」"
    elif result.today_status == "not_racing":
        inspection_events = [
            event for event in result.upcoming
            if dt.date.fromisoformat(event.start) == base + dt.timedelta(days=1)
        ]
        if inspection_events:
            result.today_status = "pre_inspection"
            result.today_text = f"前検日（翌日開始：{'、'.join(format_event(event) for event in inspection_events)}）"
        else:
            result.today_text = "本日の出走なし"
    elif result.today_status == "in_meeting_not_racing":
        result.today_text = f"本日の出走なし（開催参加中：{result.meeting}）"
    else:
        result.today_text = "取得できず（要確認）"
    return result


def format_event(event: Event) -> str:
    start, end = dt.date.fromisoformat(event.start), dt.date.fromisoformat(event.end)
    return f"{event.venue}{event.grade} {start:%m/%d}-{end:%m/%d}"


def upcoming_text(result: Result) -> str:
    if result.player.vacancy:
        return "－"
    if result.upcoming:
        return "、".join(format_event(e) for e in result.upcoming)
    if result.errors and len(result.errors) >= 2:
        return "取得できず（要確認）"
    return "今後の出走予定なし"


def write_excel(path: Path, results: list[Result], base: dt.date, elapsed: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    book = xlsxwriter.Workbook(path)
    book.set_properties({"title": f"支部長・支部長代行 本日状況 {base.isoformat()}", "author": "keirin_status.py"})
    header = book.add_format({"bold": True, "font_color": "white", "bg_color": "#4472C4", "border": 1,
                              "align": "center", "valign": "vcenter", "text_wrap": True})
    body = book.add_format({"border": 1, "valign": "vcenter", "text_wrap": True, "font_name": "Meiryo", "font_size": 10})
    center = book.add_format({"border": 1, "align": "center", "valign": "vcenter", "text_wrap": True,
                              "font_name": "Meiryo", "font_size": 10})
    active = book.add_format({"border": 1, "valign": "vcenter", "text_wrap": True, "bold": True,
                              "font_color": "#006100", "bg_color": "#E2F0D9", "font_name": "Meiryo"})
    ongoing = book.add_format({"border": 1, "valign": "vcenter", "text_wrap": True,
                               "font_color": "#7F6000", "bg_color": "#FFF2CC", "font_name": "Meiryo"})
    error_fmt = book.add_format({"border": 1, "valign": "vcenter", "text_wrap": True,
                                 "font_color": "#9C0006", "bg_color": "#FFC7CE", "font_name": "Meiryo"})

    sheet = book.add_worksheet("支部長・代行 本日状況")
    sheet.freeze_panes(1, 0)
    sheet.autofilter(0, 0, len(results), 4)
    sheet.set_column("A:A", 10)
    sheet.set_column("B:B", 23)
    sheet.set_column("C:C", 12)
    sheet.set_column("D:D", 45)
    sheet.set_column("E:E", 74)
    headers = ["支部", "氏名", "登録番号", f"本日の状況（{base:%Y/%m/%d}）", "今後の出走予定"]
    for col, value in enumerate(headers):
        sheet.write(0, col, value, header)
    sheet.set_row(0, 26)
    for row, result in enumerate(results, 1):
        p = result.player
        name = p.name if p.vacancy else f"{p.name}（{p.role}）"
        sheet.write(row, 0, p.branch, center)
        sheet.write(row, 1, name, body)
        sheet.write_string(row, 2, p.registration_no, center)
        status_fmt = active if result.today_status == "racing" else ongoing if result.today_status in {"in_meeting_not_racing", "pre_inspection"} else error_fmt if result.today_status == "unverified" else body
        sheet.write(row, 3, result.today_text, status_fmt)
        sheet.write(row, 4, upcoming_text(result), body)
        sheet.set_row(row, 44)

    memo = book.add_worksheet("作成メモ")
    memo.set_column("A:A", 22)
    memo.set_column("B:B", 100)
    memo_rows = [
        ("項目", "内容"),
        ("基準日", f"{base:%Y/%m/%d}（日本時間）"),
        ("対象", f"支部長・支部長代行。欠員行を含む{len(results)}行"),
        ("本日の状況", "KEIRIN.JP個人ページ『開催中のレース』を6桁登録番号で直接照合"),
        ("今後の予定", "WINTICKETおよびKEIRIN.JP個人ページ『出場予定』を統合"),
        ("処理時間", f"{elapsed:.1f}秒"),
        ("取得不能", f"{sum(r.today_status == 'unverified' for r in results)}名"),
        ("注意", "公開情報は変更・欠場があり得るため、利用直前に確認してください"),
    ]
    for r, values in enumerate(memo_rows):
        for c, value in enumerate(values):
            memo.write(r, c, value, header if r == 0 else body)
        memo.set_row(r, 28 if r == 0 else 38)

    audit = book.add_worksheet("取得記録")
    audit.freeze_panes(1, 0)
    audit_headers = ["支部", "氏名", "登録番号", "判定", "確認日時", "KEIRIN更新日時", "KEIRIN.JP URL", "WINTICKET URL", "警告・エラー"]
    widths = [10, 18, 12, 24, 25, 25, 58, 58, 60]
    for c, value in enumerate(audit_headers):
        audit.write(0, c, value, header)
        audit.set_column(c, c, widths[c])
    for row, result in enumerate(results, 1):
        values = [result.player.branch, result.player.name, result.player.registration_no, result.today_status,
                  result.checked_at, result.keirin_updated_at, result.keirin_url, result.winticket_url,
                  "／".join(result.warnings + result.errors)]
        for c, value in enumerate(values):
            audit.write(row, c, value, center if c in {0, 2, 3} else body)
        audit.set_row(row, 45)

    raw_sheet = book.add_worksheet("取得データJSON")
    raw_sheet.set_column("A:A", 160)
    for row, result in enumerate(results):
        raw_sheet.write(row, 0, json.dumps(asdict(result), ensure_ascii=False), body)
    book.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("members", type=Path, help="支部長・代行・副支部長一覧.xlsx")
    parser.add_argument("--date", help="基準日 YYYY-MM-DD。省略時は日本時間の本日")
    parser.add_argument("--output", type=Path, help="出力xlsx")
    parser.add_argument("--workers", type=int, default=8, help="並列数（既定8）")
    parser.add_argument("--timeout", type=int, default=20, help="1回のHTTPタイムアウト秒（既定20）")
    args = parser.parse_args()

    jst = dt.timezone(dt.timedelta(hours=9))
    base = dt.date.fromisoformat(args.date) if args.date else dt.datetime.now(jst).date()
    output = args.output or Path(f"支部長_代行_本日状況一覧_{base:%Y%m%d}.xlsx")
    players = extract_players(args.members)
    if len(players) < 35:
        raise RuntimeError(f"対象者が少なすぎます: {len(players)}行")
    regs = [p.registration_no for p in players if not p.vacancy]
    if len(regs) != len(set(regs)):
        raise RuntimeError("入力名簿の登録番号が重複しています")

    started = time.monotonic()
    try:
        meeting_categories = parse_today_meeting_categories(fetch(KEIRIN_TOP, args.timeout))
    except Exception as exc:
        meeting_categories = {}
        print(f"開催区分の取得に失敗: {exc}", file=sys.stderr)
    results: list[Result] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, min(args.workers, 12))) as pool:
        future_map = {pool.submit(investigate, p, base, args.timeout, meeting_categories): p for p in players}
        for completed, future in enumerate(concurrent.futures.as_completed(future_map), 1):
            player = future_map[future]
            try:
                result = future.result()
            except Exception as exc:
                result = Result(player=player, errors=[f"内部エラー: {exc}"], checked_at=dt.datetime.now(jst).isoformat(timespec="seconds"))
            results.append(result)
            print(f"[{completed:02d}/{len(players)}] {player.branch} {player.name}: {result.today_status}", flush=True)
    results.sort(key=lambda r: r.player.order)
    elapsed = time.monotonic() - started
    write_excel(output, results, base, elapsed)
    print(f"\n完了: {output.resolve()}")
    print(f"処理時間: {elapsed:.1f}秒 / 本日出走: {sum(r.today_status == 'racing' for r in results)}名 / 要確認: {sum(r.today_status == 'unverified' for r in results)}名")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("中断しました", file=sys.stderr)
        raise SystemExit(130)
    except Exception as exc:
        print(f"エラー: {exc}", file=sys.stderr)
        raise SystemExit(1)
