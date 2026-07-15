#!/usr/bin/env python3
"""競輪役員の状況JSONから、GitHub Pages用の静的HTMLを生成する。"""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path


STATUS = {
    "racing": ("出走", "status-racing"),
    "pre_inspection": ("前検日", "status-inspection"),
    "in_meeting_not_racing": ("開催参加中", "status-ongoing"),
    "not_racing": ("出走なし", "status-idle"),
    "unverified": ("確認中", "status-check"),
    "vacancy": ("欠員", "status-vacancy"),
}


def esc(value: object) -> str:
    return html.escape(str(value or ""), quote=True)


def japanese_date(value: str) -> str:
    year, month, day = value.split("-")
    return f"{year}年{int(month)}月{int(day)}日"


def schedule_label(item: dict) -> str:
    start, end = item["start"], item["end"]
    dates = japanese_date(start) if start == end else f"{japanese_date(start)}〜{japanese_date(end)}"
    return f"{esc(item.get('venue'))} {esc(item.get('grade'))}｜{dates}"


def upcoming_cell(officer: dict) -> str:
    upcoming = officer.get("upcoming", [])[:3]
    if not upcoming:
        return '<span class="muted">予定なし</span>'
    values = []
    for item in upcoming:
        label = schedule_label(item)
        url = item.get("source_url")
        values.append(
            f'<li><a href="{esc(url)}" target="_blank" rel="noreferrer">{label}</a></li>'
            if url else f"<li>{label}</li>"
        )
    return "<ul>" + "".join(values) + "</ul>"


def today_race(officer: dict) -> str:
    status = officer.get("today_status")
    if status == "racing":
        icon = officer.get("meeting_icon_url")
        icon_html = (
            f'<img src="{esc(icon)}" alt="{esc(officer.get("meeting_category"))}" '
            f'title="{esc(officer.get("meeting_category"))}">' if icon else ""
        )
        return (
            '<span class="race-detail">'
            f'<span>{esc(officer.get("meeting"))}</span>{icon_html}'
            f'<span>{esc(officer.get("race"))}</span></span>'
        )
    if status == "in_meeting_not_racing":
        return esc(officer.get("meeting") or "開催参加中")
    return "—"


def officer_row(officer: dict) -> str:
    player = officer["player"]
    label, class_name = STATUS.get(officer.get("today_status"), STATUS["unverified"])
    source = officer.get("keirin_url")
    source_html = (
        f'<a class="source-link" href="{esc(source)}" target="_blank" rel="noreferrer">keirin.jp</a>'
        if source else '<span class="muted">—</span>'
    )
    return f"""<tr>
      <td class="support">{esc(player.get('branch'))}</td>
      <td><div class="person"><span class="position">{esc(player.get('role'))}</span><strong>{esc(player.get('name'))}</strong></div></td>
      <td><span class="status {class_name}">{label}</span></td>
      <td class="race">{today_race(officer)}</td>
      <td class="upcoming">{upcoming_cell(officer)}</td>
      <td>{source_html}</td>
    </tr>"""


CSS = """
:root { --navy:#071c33; --ink:#10253b; --gold:#c79a48; --teal:#206d73; --paper:#f8f5ee; --line:#d9dfdf; --muted:#667586; }
* { box-sizing:border-box; } body { margin:0; color:var(--ink); background:var(--paper); font-family:-apple-system,BlinkMacSystemFont,"Hiragino Sans","Yu Gothic","Noto Sans JP",sans-serif; } a { color:inherit; }
.hero { color:#fffdf7; background:radial-gradient(circle at 84% 12%,rgba(42,117,122,.48),transparent 29%),linear-gradient(135deg,#071a31 0%,#092745 55%,#0a304c 100%); padding:27px clamp(22px,6vw,92px) 64px; overflow:hidden; position:relative; }.hero::after { content:""; position:absolute; width:660px; height:660px; border:1px solid rgba(199,154,72,.48); border-radius:50%; right:-240px; bottom:-490px; box-shadow:0 0 0 50px rgba(199,154,72,.05),0 0 0 100px rgba(199,154,72,.04); pointer-events:none; }
.topline,.hero-grid,.content { max-width:1280px; margin:auto; position:relative; z-index:1; }.topline { display:flex; align-items:center; justify-content:space-between; gap:16px; padding-bottom:46px; border-bottom:1px solid rgba(255,255,255,.18); }.eyebrow { margin:0; letter-spacing:.15em; font-size:11px; font-weight:750; color:#e4bd76; }.refresh-note { margin:0; font-size:13px; color:#d5e2e4; }.hero-grid { display:grid; grid-template-columns:minmax(0,1fr) 335px; align-items:end; gap:70px; padding-top:57px; } h1 { margin:0; font-size:clamp(42px,6.4vw,78px); letter-spacing:-.06em; line-height:1.12; font-weight:760; }.lead { margin:27px 0 25px; max-width:630px; color:#d7e2e8; font-size:16px; line-height:1.85; }.date-chip { display:inline-flex; align-items:baseline; gap:13px; border-left:3px solid var(--gold); padding-left:13px; }.date-chip span { color:#a9bcc5; font-size:12px; }.date-chip strong { font-size:18px; }.hero-panel { padding:28px; background:rgba(3,14,28,.4); border:1px solid rgba(237,211,159,.47); box-shadow:14px 14px 0 rgba(3,14,28,.16); }.hero-panel p { margin:0; color:#d2ac66; font-size:13px; }.hero-panel strong { display:block; margin:6px 0; font-size:64px; line-height:1; letter-spacing:-.06em; }.hero-panel strong span { margin-left:7px; font-size:16px; letter-spacing:0; }.hero-panel-rule { height:1px; margin:21px 0 14px; background:rgba(255,255,255,.2); }.hero-panel small { color:#c0d0d7; }
.content { padding:58px clamp(22px,6vw,92px) 88px; }.table-card { background:#fff; border:1px solid var(--line); box-shadow:0 10px 28px rgba(18,38,57,.06); }.table-title-row { padding:22px 26px; border-bottom:1px solid var(--line); display:flex; justify-content:space-between; align-items:center; }.table-title-row h2 { margin:0; font-size:17px; }.table-title-row span { font-size:12px; color:var(--muted); }.table-wrap { overflow-x:auto; } table { width:100%; min-width:970px; border-collapse:collapse; } th { padding:13px 16px; background:#eef3f2; color:#52646c; text-align:left; font-size:11px; letter-spacing:.07em; white-space:nowrap; } td { padding:17px 16px; border-top:1px solid #e9eeed; vertical-align:top; font-size:13px; line-height:1.5; } tbody tr:first-child td { border-top:0; } tbody tr:hover { background:#fcfdfc; }.support { color:var(--teal); font-weight:700; white-space:nowrap; }.person { display:grid; gap:3px; min-width:118px; }.person strong { font-size:15px; }.position { color:var(--muted); font-size:11px; }.status { display:inline-block; border-radius:99px; padding:4px 9px; white-space:nowrap; font-size:11px; font-weight:700; }.status-racing { color:#fff; background:#b46d26; }.status-idle { color:#51616e; background:#edf1f2; }.status-check { color:#785817; background:#f5edcf; }.status-ongoing { color:#755913; background:#f6e8b5; }.status-inspection { color:#155c62; background:#d9eeec; }.status-vacancy { color:#72525e; background:#f0e4e8; }.race { white-space:nowrap; }.race-detail { display:inline-flex; align-items:center; gap:7px; white-space:nowrap; }.race-detail img { display:block; width:auto; height:18px; object-fit:contain; }.upcoming { min-width:255px; }.upcoming ul { display:grid; gap:5px; margin:0; padding:0; list-style:none; }.upcoming a { text-decoration-color:#9cabb2; text-underline-offset:3px; }.upcoming a:hover,.source-link:hover { color:var(--teal); }.source-link { color:var(--teal); font-size:12px; font-weight:700; text-underline-offset:3px; }.muted { color:#9aa4aa; }.notice { display:grid; grid-template-columns:130px 1fr; gap:16px; margin-top:26px; padding:20px 22px; border-left:3px solid var(--gold); background:#eee8da; }.notice strong { font-size:13px; }.notice p { margin:0; color:#53606a; font-size:13px; line-height:1.7; }
@media (max-width:760px) { .hero { padding-bottom:45px; }.topline { padding-bottom:28px; }.hero-grid { grid-template-columns:1fr; gap:30px; padding-top:40px; }.hero-panel { max-width:100%; }.content { padding-top:42px; }.notice { grid-template-columns:1fr; gap:7px; } }
"""


def render(payload: dict) -> str:
    officers = list(payload["officers"])
    rank = {"racing": 0, "pre_inspection": 1, "in_meeting_not_racing": 2, "not_racing": 3, "unverified": 4, "vacancy": 5}
    officers.sort(key=lambda item: (rank.get(item.get("today_status"), 99), item["player"].get("order", 0)))
    racing = sum(item.get("today_status") == "racing" for item in officers)
    inspections = sum(item.get("today_status") == "pre_inspection" for item in officers)
    checking = sum(item.get("today_status") == "unverified" for item in officers)
    rows = "\n".join(officer_row(item) for item in officers)
    base_date = japanese_date(payload["baseDate"])
    return f"""<!doctype html>
<html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="description" content="支部長・支部長代行・副支部長の出走・予定一覧"><title>支部長等 出走・予定一覧</title><style>{CSS}</style></head>
<body><main><section class="hero"><div class="topline"><p class="eyebrow">OFFICER RACE DESK</p><p class="refresh-note">情報更新：毎朝 5:07</p></div><div class="hero-grid"><div><h1>支部長等<br>出走・予定一覧</h1><p class="lead">支部長・支部長代行・副支部長の、本日の出走状況と今後の予定をまとめて確認できます。</p><div class="date-chip"><span>対象日</span><strong>{base_date}</strong></div></div><div class="hero-panel"><p>本日の出走</p><strong>{racing}<span>名</span></strong><div class="hero-panel-rule"></div><small>確認対象 {len(officers)}行 ／ 前検日 {inspections}名 ／ 確認中 {checking}名</small></div></div></section>
<section class="content"><div class="table-card"><div class="table-title-row"><h2>役員別一覧</h2><span>全 {len(officers)} 名</span></div><div class="table-wrap"><table><thead><tr><th>支部</th><th>役職・氏名</th><th>本日の状況</th><th>本日のレース</th><th>今後の予定（直近３開催）</th><th>情報源</th></tr></thead><tbody>{rows}</tbody></table></div></div><aside class="notice"><strong>更新について</strong><p>keirin.jp の選手ページを直接照合して作成しています。keirin.jp の更新後、毎朝5時ごろに一覧へ反映します。</p></aside></section></main></body></html>"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = json.loads(args.data.read_text(encoding="utf-8"))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render(payload), encoding="utf-8")
    print(args.output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
