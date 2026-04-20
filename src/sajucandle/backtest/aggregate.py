"""backtest.aggregate: run별 등급 통계.

run_id로 필터한 signal_log에서 tracking_done=TRUE row만 집계.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import asyncpg


@dataclass
class GradeStats:
    grade: str
    count: int
    win_rate: float           # mfe_7d_pct > 0 비율
    avg_mfe: float
    avg_mae: float
    avg_rr_tp1: Optional[float]


async def aggregate_run(
    conn: asyncpg.Connection,
    *,
    run_id: str,
) -> list[GradeStats]:
    """signal_log WHERE run_id=$1 AND tracking_done=TRUE → 등급별 집계."""
    rows = await conn.fetch(
        """
        SELECT signal_grade,
               COUNT(*) AS cnt,
               AVG(CASE WHEN mfe_7d_pct > 0 THEN 1.0 ELSE 0.0 END) AS win_rate,
               AVG(mfe_7d_pct) AS avg_mfe,
               AVG(mae_7d_pct) AS avg_mae,
               AVG(rr_tp1) AS avg_rr_tp1
        FROM signal_log
        WHERE run_id = $1 AND tracking_done = TRUE
        GROUP BY signal_grade
        ORDER BY AVG(mfe_7d_pct) DESC NULLS LAST
        """,
        run_id,
    )
    out: list[GradeStats] = []
    for r in rows:
        out.append(GradeStats(
            grade=r["signal_grade"],
            count=int(r["cnt"] or 0),
            win_rate=float(r["win_rate"] or 0.0),
            avg_mfe=float(r["avg_mfe"] or 0.0),
            avg_mae=float(r["avg_mae"] or 0.0),
            avg_rr_tp1=float(r["avg_rr_tp1"]) if r["avg_rr_tp1"] is not None else None,
        ))
    return out
