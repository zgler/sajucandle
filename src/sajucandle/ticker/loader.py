"""종목 CSV 로더."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Dict, List, Optional

from .schema import TickerRecord, TransitionPoint


def _parse_transition_points(raw: str) -> List[TransitionPoint]:
    if not raw or raw.strip() in ("", "[]"):
        return []
    try:
        data = json.loads(raw)
        return [TransitionPoint(
            date=d.get("date", ""),
            label=d.get("label", ""),
            time=d.get("time", "00:00"),
        ) for d in data if d.get("date")]
    except json.JSONDecodeError:
        return []


def load_tickers(csv_path: Optional[Path] = None) -> Dict[str, TickerRecord]:
    """CSV에서 종목 레코드 로드. symbol → TickerRecord 딕셔너리."""
    if csv_path is None:
        project_root = Path(__file__).resolve().parents[3]
        csv_path = project_root / "data" / "tickers" / "sample_tickers.csv"
    records: Dict[str, TickerRecord] = {}
    with csv_path.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            sym = row.get("symbol", "").strip()
            if not sym:
                continue
            try:
                wf = float(row.get("weight_founding") or 0.5)
                wl = float(row.get("weight_listing") or 0.3)
                wt = float(row.get("weight_transition") or 0.2)
            except ValueError:
                wf, wl, wt = 0.5, 0.3, 0.2
            rec = TickerRecord(
                symbol=sym,
                name=row.get("name", sym),
                asset_class=row.get("asset_class", "stock"),
                market=row.get("market", ""),
                sector=row.get("sector", ""),
                founding_date=row.get("founding_date") or None,
                founding_time=row.get("founding_time") or "09:00",
                listing_date=row.get("listing_date") or None,
                listing_time=row.get("listing_time") or "09:30",
                birth_city=row.get("birth_city") or "New York",
                transition_points=_parse_transition_points(
                    row.get("transition_points_json", "")),
                weight_founding=wf,
                weight_listing=wl,
                weight_transition=wt,
                notes=row.get("notes", ""),
            )
            rec.normalize_weights()
            records[sym] = rec
    return records
