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


# 支部の並びは、画面の「支部（北から）順」と地区タブの両方で利用する。
REGIONS = {
    "北日本": ("北海道", "青森", "宮城", "福島"),
    "関東": ("茨城", "栃木", "群馬", "埼玉", "東京", "新潟"),
    "南関東": ("千葉", "神奈川", "静岡"),
    "中部": ("愛知", "富山", "岐阜", "三重"),
    "近畿": ("福井", "京都", "大阪", "兵庫", "奈良", "和歌山"),
    "中国": ("岡山", "広島", "山口"),
    "四国": ("香川", "徳島", "高知", "愛媛"),
    "九州": ("福岡", "佐賀", "長崎", "大分", "熊本", "鹿児島"),
}
BRANCH_ORDER = {
    branch: index
    for index, branch in enumerate(branch for branches in REGIONS.values() for branch in branches)
}
BRANCH_REGION = {
    branch: region
    for region, branches in REGIONS.items()
    for branch in branches
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
    """個人ページに載っている今後の予定を、件数で切らずにすべて表示する。"""
    upcoming = officer.get("upcoming", [])
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
    """JavaScriptを使えない場合にも、基準日の一覧を表示する。"""
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
.hero { color:#fffdf7; background:linear-gradient(118deg,#071a31,#0a304c); }.hero-inner,.content { max-width:1280px; margin:auto; }.hero-main { min-height:82px; padding:18px clamp(22px,6vw,92px); display:flex; align-items:center; justify-content:space-between; gap:24px; }.hero h1 { margin:0; font-size:clamp(24px,3.2vw,36px); letter-spacing:-.045em; line-height:1.15; }.header-info { display:flex; align-items:center; justify-content:flex-end; flex-wrap:wrap; gap:12px 24px; }.header-item { display:grid; gap:3px; }.header-item span { color:#b9cad0; font-size:11px; letter-spacing:.06em; }.header-item strong { font-size:15px; white-space:nowrap; }.header-count strong { color:#f3cd84; font-size:19px; }.target-bar { border-top:1px solid rgba(255,255,255,.2); padding:11px clamp(22px,6vw,92px) 13px; display:flex; align-items:center; gap:12px; }.target-bar label { color:#b9cad0; font-size:12px; font-weight:700; }.target-bar input { width:154px; border:1px solid rgba(255,255,255,.45); border-radius:5px; padding:6px 8px; color:#fffdf7; background:#0a2946; font:700 13px -apple-system,BlinkMacSystemFont,"Hiragino Sans","Yu Gothic",sans-serif; color-scheme:dark; }.target-bar small { color:#b9cad0; font-size:12px; }.header-note { margin:0; padding:0 clamp(22px,6vw,92px) 14px; color:#c6d2d7; font-size:11px; line-height:1.65; }
.content { padding:36px clamp(22px,6vw,92px) 72px; }.table-card { background:#fff; border:1px solid var(--line); box-shadow:0 10px 28px rgba(18,38,57,.06); }.table-title-row { padding:20px 26px; border-bottom:1px solid var(--line); display:flex; justify-content:space-between; align-items:center; gap:16px; }.table-title-row h2 { margin:0; font-size:17px; }.table-title-row span { font-size:12px; color:var(--muted); }.table-controls { padding:18px 26px 19px; border-bottom:1px solid var(--line); background:#fbfcfb; }.control-label { display:block; margin:0 0 8px; color:#667586; font-size:11px; font-weight:750; letter-spacing:.06em; }.tab-list,.sort-list { display:flex; flex-wrap:wrap; gap:7px; }.tab-list { margin-bottom:16px; }.filter-tab,.sort-button { appearance:none; cursor:pointer; border:1px solid #cbd6d5; border-radius:999px; padding:7px 11px; color:#36505b; background:#fff; font:700 12px/1 -apple-system,BlinkMacSystemFont,"Hiragino Sans","Yu Gothic","Noto Sans JP",sans-serif; transition:background .16s,color .16s,border-color .16s; }.filter-tab:hover,.sort-button:hover { border-color:#78a09d; }.filter-tab[aria-pressed="true"],.sort-button[aria-pressed="true"] { color:#fff; border-color:var(--teal); background:var(--teal); }.table-wrap { overflow-x:auto; } table { width:100%; min-width:970px; border-collapse:collapse; } th { padding:13px 16px; background:#eef3f2; color:#52646c; text-align:left; font-size:11px; letter-spacing:.07em; white-space:nowrap; } td { padding:17px 16px; border-top:1px solid #e9eeed; vertical-align:top; font-size:13px; line-height:1.5; } tbody tr:first-child td { border-top:0; } tbody tr:hover { background:#fcfdfc; }.support { color:var(--teal); font-weight:700; white-space:nowrap; }.person { display:grid; gap:3px; min-width:118px; }.person strong { font-size:15px; }.position { color:var(--muted); font-size:11px; }.status { display:inline-block; border-radius:99px; padding:4px 9px; white-space:nowrap; font-size:11px; font-weight:700; }.status-racing { color:#fff; background:#b46d26; }.status-idle { color:#51616e; background:#edf1f2; }.status-check { color:#785817; background:#f5edcf; }.status-ongoing,.status-scheduled { color:#755913; background:#f6e8b5; }.status-inspection { color:#155c62; background:#d9eeec; }.status-vacancy { color:#72525e; background:#f0e4e8; }.race { white-space:nowrap; }.race-detail { display:inline-flex; align-items:center; gap:7px; white-space:nowrap; }.race-detail img { display:block; width:auto; height:18px; object-fit:contain; }.upcoming { min-width:280px; }.upcoming ul { display:grid; gap:5px; margin:0; padding:0; list-style:none; }.upcoming a { text-decoration-color:#9cabb2; text-underline-offset:3px; }.upcoming a:hover,.source-link:hover { color:var(--teal); }.source-link { color:var(--teal); font-size:12px; font-weight:700; text-underline-offset:3px; }.muted { color:#9aa4aa; }.notice { display:grid; grid-template-columns:130px 1fr; gap:16px; margin-top:26px; padding:20px 22px; border-left:3px solid var(--gold); background:#eee8da; }.notice strong { font-size:13px; }.notice p { margin:0; color:#53606a; font-size:13px; line-height:1.7; }
@media (max-width:760px) { .hero-main { min-height:auto; padding-top:18px; padding-bottom:16px; align-items:flex-start; flex-direction:column; gap:14px; }.header-info { justify-content:flex-start; gap:10px 18px; }.target-bar { padding-top:10px; padding-bottom:11px; flex-wrap:wrap; }.content { padding-top:26px; }.table-title-row,.table-controls { padding-left:18px; padding-right:18px; }.notice { grid-template-columns:1fr; gap:7px; } }
"""


SCRIPT = r"""
<script>
(() => {
  const officers = __OFFICERS__;
  const baseDate = __BASE_DATE__;
  const input = document.getElementById('target-date');
  const body = document.getElementById('officer-rows');
  const count = document.getElementById('result-count');
  const targetCaption = document.getElementById('target-caption');
  const statusHead = document.getElementById('status-head');
  const raceHead = document.getElementById('race-head');
  const statusSortLabel = document.getElementById('status-sort-label');
  const tabs = Array.from(document.querySelectorAll('.filter-tab'));
  const sorts = Array.from(document.querySelectorAll('.sort-button'));
  let region = 'all';
  let sort = 'status';

  const escapeHtml = (value) => String(value ?? '').replace(/[&<>'"]/g, (character) => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', "'":'&#39;', '"':'&quot;' }[character]));
  const toJapaneseDate = (value) => {
    const [year, month, day] = value.split('-');
    return `${year}年${Number(month)}月${Number(day)}日`;
  };
  const shift = (date, days) => {
    const value = new Date(`${date}T00:00:00Z`);
    value.setUTCDate(value.getUTCDate() + days);
    return value.toISOString().slice(0, 10);
  };
  const eventsFor = (officer) => [...(officer.ongoing || []), ...(officer.upcoming || [])];
  const statusMeta = {
    racing: ['出走', 'status-racing', 0],
    pre_inspection: ['前検日', 'status-inspection', 1],
    scheduled: ['参加予定', 'status-scheduled', 2],
    in_meeting_not_racing: ['開催参加中', 'status-ongoing', 3],
    not_racing: ['出走なし', 'status-idle', 4],
    not_scheduled: ['予定なし', 'status-idle', 4],
    unverified: ['確認中', 'status-check', 5],
    vacancy: ['欠員', 'status-vacancy', 6],
  };
  const currentState = (officer) => ({ key: officer.today_status || 'unverified', event: null });
  const plannedState = (officer, target) => {
    if (officer.player?.vacancy) return { key: 'vacancy', event: null };
    const events = eventsFor(officer);
    const attending = events.find((event) => event.start <= target && target <= event.end);
    if (attending) return { key: 'scheduled', event: attending };
    const inspection = events.find((event) => shift(event.start, -1) === target);
    if (inspection) return { key: 'pre_inspection', event: inspection };
    return { key: 'not_scheduled', event: null };
  };
  const stateFor = (officer, target) => target === baseDate ? currentState(officer) : plannedState(officer, target);
  const eventLabel = (event) => `${event.venue} ${event.grade}`;
  const source = (officer) => officer.keirin_url ? `<a class="source-link" href="${escapeHtml(officer.keirin_url)}" target="_blank" rel="noreferrer">keirin.jp</a>` : '<span class="muted">—</span>';
  const scheduleList = (officer) => {
    const events = officer.upcoming || [];
    if (!events.length) return '<span class="muted">予定なし</span>';
    return `<ul>${events.map((event) => {
      const dates = event.start === event.end ? toJapaneseDate(event.start) : `${toJapaneseDate(event.start)}〜${toJapaneseDate(event.end)}`;
      const label = `${escapeHtml(event.venue)} ${escapeHtml(event.grade)}｜${dates}`;
      return event.source_url ? `<li><a href="${escapeHtml(event.source_url)}" target="_blank" rel="noreferrer">${label}</a></li>` : `<li>${label}</li>`;
    }).join('')}</ul>`;
  };
  const detailFor = (officer, state, target) => {
    if (target === baseDate) {
      if (state.key === 'racing') {
        const icon = officer.meeting_icon_url ? `<img src="${escapeHtml(officer.meeting_icon_url)}" alt="${escapeHtml(officer.meeting_category)}" title="${escapeHtml(officer.meeting_category)}">` : '';
        return `<span class="race-detail"><span>${escapeHtml(officer.meeting)}</span>${icon}<span>${escapeHtml(officer.race)}</span></span>`;
      }
      return state.key === 'in_meeting_not_racing' ? escapeHtml(officer.meeting || '開催参加中') : '—';
    }
    if (!state.event) return '—';
    if (state.key === 'pre_inspection') return `翌日開始：${escapeHtml(eventLabel(state.event))}`;
    return escapeHtml(eventLabel(state.event));
  };
  const compare = (left, right) => {
    if (sort === 'branch') return left.branchRank - right.branchRank || left.order - right.order;
    return left.stateRank - right.stateRank || left.branchRank - right.branchRank || left.order - right.order;
  };
  const render = () => {
    const target = input.value || baseDate;
    const selected = officers.map((officer) => {
      const state = stateFor(officer, target);
      const meta = statusMeta[state.key] || statusMeta.unverified;
      return {
        officer, state, label: meta[0], className: meta[1], stateRank: meta[2],
        branchRank: Number(officer.player?.branch_rank ?? 999), order: Number(officer.player?.order ?? 999),
        region: officer.player?.region || 'その他',
      };
    }).filter((entry) => region === 'all' || entry.region === region).sort(compare);
    body.innerHTML = selected.map(({ officer, state, label, className }) => `<tr>
      <td class="support">${escapeHtml(officer.player?.branch)}</td>
      <td><div class="person"><span class="position">${escapeHtml(officer.player?.role)}</span><strong>${escapeHtml(officer.player?.name)}</strong></div></td>
      <td><span class="status ${className}">${label}</span></td>
      <td class="race">${detailFor(officer, state, target)}</td>
      <td class="upcoming">${scheduleList(officer)}</td>
      <td>${source(officer)}</td>
    </tr>`).join('');
    const prefix = region === 'all' ? '全地区' : region;
    count.textContent = `${prefix} ${selected.length} 名`;
    targetCaption.textContent = toJapaneseDate(target);
    const isToday = target === baseDate;
    statusHead.textContent = isToday ? '本日の状況' : '対象日の状況';
    raceHead.textContent = isToday ? '本日のレース' : '対象日の予定';
    statusSortLabel.textContent = isToday ? '本日の状況順' : '対象日の状況順';
    tabs.forEach((button) => button.setAttribute('aria-pressed', String(button.dataset.region === region)));
    sorts.forEach((button) => button.setAttribute('aria-pressed', String(button.dataset.sort === sort)));
  };
  input.addEventListener('change', render);
  tabs.forEach((button) => button.addEventListener('click', () => { region = button.dataset.region; render(); }));
  sorts.forEach((button) => button.addEventListener('click', () => { sort = button.dataset.sort; render(); }));
  render();
})();
</script>
"""


def render(payload: dict) -> str:
    officers = list(payload["officers"])
    rank = {"racing": 0, "pre_inspection": 1, "in_meeting_not_racing": 2, "not_racing": 3, "unverified": 4, "vacancy": 5}
    officers.sort(key=lambda item: (rank.get(item.get("today_status"), 99), item["player"].get("order", 0)))
    for officer in officers:
        player = officer.setdefault("player", {})
        branch = str(player.get("branch") or "")
        player["region"] = BRANCH_REGION.get(branch, "その他")
        player["branch_rank"] = BRANCH_ORDER.get(branch, 999)

    racing = sum(item.get("today_status") == "racing" for item in officers)
    rows = "\n".join(officer_row(item) for item in officers)
    tabs = "\n".join(
        f'<button class="filter-tab" type="button" data-region="{esc(region)}" aria-pressed="false">{esc(region)}</button>'
        for region in REGIONS
    )
    base_date = payload["baseDate"]
    all_end_dates = [
        item["end"]
        for officer in officers
        for item in officer.get("upcoming", [])
        if item.get("end")
    ]
    max_date = max(all_end_dates, default=base_date)
    embedded_officers = json.dumps(officers, ensure_ascii=False).replace("</", "<\\/")
    script = SCRIPT.replace("__OFFICERS__", embedded_officers).replace("__BASE_DATE__", json.dumps(base_date))

    return f"""<!doctype html>
<html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="description" content="支部長・支部長代行の出走・予定一覧"><title>支部長等 出走・予定一覧</title><style>{CSS}</style></head>
<body><main><header class="hero"><div class="hero-inner"><div class="hero-main"><h1>支部長等出走・予定一覧</h1><div class="header-info"><div class="header-item"><span>情報更新日</span><strong>{japanese_date(base_date)}</strong></div><div class="header-item header-count"><span>本日の出走</span><strong>{racing}名</strong></div></div></div><div class="target-bar"><label for="target-date">対象日</label><input id="target-date" type="date" value="{esc(base_date)}" min="{esc(base_date)}" max="{esc(max_date)}"><small><span id="target-caption">{japanese_date(base_date)}</span>の状況を表示</small></div><p class="header-note">※参加情報は複数サイトにおける当該選手の「今後の予定」を参照しているため、情報が古い場合があります。KEIRIN.JPでの最終確認をお願いします。</p></div></header>
<section class="content"><div class="table-card"><div class="table-title-row"><h2>役員別一覧</h2><span id="result-count">全地区 {len(officers)} 名</span></div><div class="table-controls"><span class="control-label">地区</span><div class="tab-list" role="group" aria-label="地区で絞り込む"><button class="filter-tab" type="button" data-region="all" aria-pressed="true">全地区</button>{tabs}</div><span class="control-label">並び替え</span><div class="sort-list" role="group" aria-label="一覧の並び替え"><button class="sort-button" type="button" data-sort="status" aria-pressed="true" id="status-sort-label">本日の状況順</button><button class="sort-button" type="button" data-sort="branch" aria-pressed="false">支部（北から）順</button></div></div><div class="table-wrap"><table><thead><tr><th>支部</th><th>役職・氏名</th><th id="status-head">本日の状況</th><th id="race-head">本日のレース</th><th>今後の予定（全件）</th><th>情報源</th></tr></thead><tbody id="officer-rows">{rows}</tbody></table></div></div><aside class="notice"><strong>更新について</strong><p>keirin.jp の選手ページを直接照合して作成しています。対象日の予定は、選手ページに掲載された出場予定から判定しています。</p></aside></section></main>{script}</body></html>"""


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
