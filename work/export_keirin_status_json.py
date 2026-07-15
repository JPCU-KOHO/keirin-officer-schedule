#!/usr/bin/env python3
"""keirin_status.py が作成した Excel の監査データをサイト用 JSON に書き出す。"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET


NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def read_results(workbook: Path) -> list[dict]:
    with zipfile.ZipFile(workbook) as archive:
        root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
    strings = ["".join(node.itertext()) for node in root.findall("m:si", NS)]
    return [json.loads(value) for value in strings if value.startswith('{"player":')]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workbook", type=Path)
    parser.add_argument("--date", required=True, help="基準日 YYYY-MM-DD")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    officers = read_results(args.workbook)
    if len(officers) < 35:
        raise RuntimeError(f"取得件数が少なすぎます: {len(officers)}")

    payload = {
        "baseDate": args.date,
        "generatedAt": dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat(timespec="seconds"),
        "source": "keirin_status.py",
        "officers": officers,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{args.output.resolve()} ({len(officers)} records)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
