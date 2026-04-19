"""users + user_bazi CRUD. asyncpg Connection 주입 받음."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional

import asyncpg


@dataclass
class UserProfile:
    telegram_chat_id: int
    birth_year: int
    birth_month: int
    birth_day: int
    birth_hour: int
    birth_minute: int
    asset_class_pref: str = "swing"
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


_UPSERT_USER = """
INSERT INTO users (telegram_chat_id) VALUES ($1)
ON CONFLICT (telegram_chat_id) DO UPDATE
    SET updated_at = now()
RETURNING created_at, updated_at
"""

_UPSERT_BAZI = """
INSERT INTO user_bazi (
    telegram_chat_id, birth_year, birth_month, birth_day,
    birth_hour, birth_minute, asset_class_pref
) VALUES ($1, $2, $3, $4, $5, $6, $7)
ON CONFLICT (telegram_chat_id) DO UPDATE SET
    birth_year = EXCLUDED.birth_year,
    birth_month = EXCLUDED.birth_month,
    birth_day = EXCLUDED.birth_day,
    birth_hour = EXCLUDED.birth_hour,
    birth_minute = EXCLUDED.birth_minute,
    asset_class_pref = EXCLUDED.asset_class_pref,
    updated_at = now()
RETURNING created_at, updated_at
"""

_SELECT = """
SELECT u.telegram_chat_id,
       b.birth_year, b.birth_month, b.birth_day,
       b.birth_hour, b.birth_minute,
       b.asset_class_pref,
       u.created_at, u.updated_at
FROM users u
JOIN user_bazi b USING (telegram_chat_id)
WHERE u.telegram_chat_id = $1
"""


async def upsert_user(conn: asyncpg.Connection, profile: UserProfile) -> UserProfile:
    """users + user_bazi upsert. 단일 트랜잭션."""
    async with conn.transaction():
        u_row = await conn.fetchrow(_UPSERT_USER, profile.telegram_chat_id)
        b_row = await conn.fetchrow(
            _UPSERT_BAZI,
            profile.telegram_chat_id,
            profile.birth_year,
            profile.birth_month,
            profile.birth_day,
            profile.birth_hour,
            profile.birth_minute,
            profile.asset_class_pref,
        )
    return UserProfile(
        telegram_chat_id=profile.telegram_chat_id,
        birth_year=profile.birth_year,
        birth_month=profile.birth_month,
        birth_day=profile.birth_day,
        birth_hour=profile.birth_hour,
        birth_minute=profile.birth_minute,
        asset_class_pref=profile.asset_class_pref,
        created_at=u_row["created_at"],
        updated_at=b_row["updated_at"],
    )


async def get_user(conn: asyncpg.Connection, chat_id: int) -> Optional[UserProfile]:
    row = await conn.fetchrow(_SELECT, chat_id)
    if row is None:
        return None
    return UserProfile(
        telegram_chat_id=row["telegram_chat_id"],
        birth_year=row["birth_year"],
        birth_month=row["birth_month"],
        birth_day=row["birth_day"],
        birth_hour=row["birth_hour"],
        birth_minute=row["birth_minute"],
        asset_class_pref=row["asset_class_pref"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


async def delete_user(conn: asyncpg.Connection, chat_id: int) -> None:
    """ON DELETE CASCADE로 user_bazi도 함께 삭제. 없으면 no-op."""
    await conn.execute("DELETE FROM users WHERE telegram_chat_id = $1", chat_id)


async def list_chat_ids(conn: asyncpg.Connection) -> list[int]:
    """명식이 등록된 모든 사용자의 chat_id 리스트.

    user_bazi 기준. users에만 있고 명식 없는 레코드는 제외 (/score가 어차피 실패).
    반환 순서는 보장 X.
    """
    rows = await conn.fetch("SELECT telegram_chat_id FROM user_bazi")
    return [r["telegram_chat_id"] for r in rows]


# ─────────────────────────────────────────────
# Week 7: watchlist
# ─────────────────────────────────────────────


@dataclass
class WatchlistEntry:
    ticker: str
    added_at: datetime


async def list_watchlist(
    conn: asyncpg.Connection, chat_id: int
) -> list[WatchlistEntry]:
    """사용자의 watchlist (added_at ASC). 비어있으면 []."""
    rows = await conn.fetch(
        "SELECT ticker, added_at FROM user_watchlist "
        "WHERE telegram_chat_id = $1 ORDER BY added_at ASC",
        chat_id,
    )
    return [WatchlistEntry(ticker=r["ticker"], added_at=r["added_at"]) for r in rows]


async def add_to_watchlist(
    conn: asyncpg.Connection, chat_id: int, ticker: str
) -> None:
    """INSERT. 중복이면 asyncpg.UniqueViolationError 전파."""
    await conn.execute(
        "INSERT INTO user_watchlist (telegram_chat_id, ticker) VALUES ($1, $2)",
        chat_id, ticker,
    )


async def remove_from_watchlist(
    conn: asyncpg.Connection, chat_id: int, ticker: str
) -> bool:
    """DELETE. True=삭제됨, False=애초에 없었음."""
    result = await conn.execute(
        "DELETE FROM user_watchlist "
        "WHERE telegram_chat_id = $1 AND ticker = $2",
        chat_id, ticker,
    )
    # asyncpg execute는 "DELETE N" 형태 문자열 반환
    return result.endswith(" 1")


async def count_watchlist(
    conn: asyncpg.Connection, chat_id: int
) -> int:
    """현재 등록된 심볼 개수."""
    n = await conn.fetchval(
        "SELECT COUNT(*) FROM user_watchlist WHERE telegram_chat_id = $1",
        chat_id,
    )
    return int(n or 0)


async def list_all_watchlist_tickers(
    conn: asyncpg.Connection,
) -> set[str]:
    """모든 사용자 watchlist ticker union. broadcast precompute용."""
    rows = await conn.fetch("SELECT DISTINCT ticker FROM user_watchlist")
    return {r["ticker"] for r in rows}


# ─────────────────────────────────────────────
# Week 8: signal_log
# ─────────────────────────────────────────────


@dataclass
class SignalLogRow:
    id: int
    sent_at: datetime
    source: str
    telegram_chat_id: Optional[int]
    ticker: str
    target_date: date
    entry_price: float
    saju_score: int
    analysis_score: int
    structure_state: str
    alignment_bias: str
    rsi_1h: Optional[float]
    volume_ratio_1d: Optional[float]
    composite_score: int
    signal_grade: str
    mfe_7d_pct: Optional[float]
    mae_7d_pct: Optional[float]
    close_24h: Optional[float]
    close_7d: Optional[float]
    last_tracked_at: Optional[datetime]
    tracking_done: bool


async def insert_signal_log(
    conn: asyncpg.Connection,
    *,
    source: str,
    telegram_chat_id: Optional[int],
    ticker: str,
    target_date,
    entry_price: float,
    saju_score: int,
    analysis_score: int,
    structure_state: str,
    alignment_bias: str,
    rsi_1h: Optional[float],
    volume_ratio_1d: Optional[float],
    composite_score: int,
    signal_grade: str,
    # Week 9
    stop_loss: Optional[float] = None,
    take_profit_1: Optional[float] = None,
    take_profit_2: Optional[float] = None,
    risk_pct: Optional[float] = None,
    rr_tp1: Optional[float] = None,
    rr_tp2: Optional[float] = None,
    sl_basis: Optional[str] = None,
    tp1_basis: Optional[str] = None,
    tp2_basis: Optional[str] = None,
) -> int:
    """signal_log INSERT → id 반환."""
    row = await conn.fetchrow(
        """
        INSERT INTO signal_log (
            source, telegram_chat_id,
            ticker, target_date, entry_price,
            saju_score, analysis_score,
            structure_state, alignment_bias,
            rsi_1h, volume_ratio_1d,
            composite_score, signal_grade,
            stop_loss, take_profit_1, take_profit_2,
            risk_pct, rr_tp1, rr_tp2,
            sl_basis, tp1_basis, tp2_basis
        ) VALUES (
            $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13,
            $14, $15, $16, $17, $18, $19, $20, $21, $22
        ) RETURNING id
        """,
        source, telegram_chat_id,
        ticker, target_date, entry_price,
        saju_score, analysis_score,
        structure_state, alignment_bias,
        rsi_1h, volume_ratio_1d,
        composite_score, signal_grade,
        stop_loss, take_profit_1, take_profit_2,
        risk_pct, rr_tp1, rr_tp2,
        sl_basis, tp1_basis, tp2_basis,
    )
    return int(row["id"])


async def list_pending_tracking(
    conn: asyncpg.Connection,
    now: datetime,
    max_rows: int = 500,
) -> list[SignalLogRow]:
    """tracking_done=FALSE AND sent_at > now-7d AND sent_at < now-1h."""
    from datetime import timedelta as _td
    rows = await conn.fetch(
        """
        SELECT id, sent_at, source, telegram_chat_id,
               ticker, target_date, entry_price,
               saju_score, analysis_score,
               structure_state, alignment_bias,
               rsi_1h, volume_ratio_1d,
               composite_score, signal_grade,
               mfe_7d_pct, mae_7d_pct,
               close_24h, close_7d,
               last_tracked_at, tracking_done
        FROM signal_log
        WHERE tracking_done = FALSE
          AND sent_at > $1
          AND sent_at < $2
        ORDER BY sent_at ASC
        LIMIT $3
        """,
        now - _td(days=7),
        now - _td(hours=1),
        max_rows,
    )
    result: list[SignalLogRow] = []
    for r in rows:
        result.append(SignalLogRow(
            id=int(r["id"]),
            sent_at=r["sent_at"],
            source=r["source"],
            telegram_chat_id=r["telegram_chat_id"],
            ticker=r["ticker"],
            target_date=r["target_date"],
            entry_price=float(r["entry_price"]),
            saju_score=int(r["saju_score"]),
            analysis_score=int(r["analysis_score"]),
            structure_state=r["structure_state"],
            alignment_bias=r["alignment_bias"],
            rsi_1h=float(r["rsi_1h"]) if r["rsi_1h"] is not None else None,
            volume_ratio_1d=float(r["volume_ratio_1d"]) if r["volume_ratio_1d"] is not None else None,
            composite_score=int(r["composite_score"]),
            signal_grade=r["signal_grade"],
            mfe_7d_pct=float(r["mfe_7d_pct"]) if r["mfe_7d_pct"] is not None else None,
            mae_7d_pct=float(r["mae_7d_pct"]) if r["mae_7d_pct"] is not None else None,
            close_24h=float(r["close_24h"]) if r["close_24h"] is not None else None,
            close_7d=float(r["close_7d"]) if r["close_7d"] is not None else None,
            last_tracked_at=r["last_tracked_at"],
            tracking_done=r["tracking_done"],
        ))
    return result


async def update_signal_tracking(
    conn: asyncpg.Connection,
    signal_id: int,
    *,
    mfe_pct: float,
    mae_pct: float,
    close_24h: Optional[float],
    close_7d: Optional[float],
    tracking_done: bool,
) -> None:
    await conn.execute(
        """
        UPDATE signal_log SET
            mfe_7d_pct = $2,
            mae_7d_pct = $3,
            close_24h = $4,
            close_7d = $5,
            tracking_done = $6,
            last_tracked_at = now()
        WHERE id = $1
        """,
        signal_id, mfe_pct, mae_pct, close_24h, close_7d, tracking_done,
    )


# ─────────────────────────────────────────────
# Week 10 Phase 1: signal_log 집계
# ─────────────────────────────────────────────


async def aggregate_signal_stats(
    conn: asyncpg.Connection,
    *,
    since: datetime,
    ticker: Optional[str] = None,
    grade: Optional[str] = None,
) -> dict:
    """signal_log 집계 — total, by_grade, tracking, MFE/MAE 통계."""
    conditions = ["sent_at >= $1"]
    params: list = [since]
    if ticker is not None:
        params.append(ticker)
        conditions.append(f"ticker = ${len(params)}")
    if grade is not None:
        params.append(grade)
        conditions.append(f"signal_grade = ${len(params)}")
    where = " AND ".join(conditions)

    total_row = await conn.fetchval(
        f"SELECT COUNT(*) FROM signal_log WHERE {where}",
        *params,
    )
    total = int(total_row or 0)

    by_grade_rows = await conn.fetch(
        f"SELECT signal_grade, COUNT(*) AS cnt FROM signal_log "
        f"WHERE {where} GROUP BY signal_grade",
        *params,
    )
    by_grade = {r["signal_grade"]: int(r["cnt"]) for r in by_grade_rows}

    tracking_row = await conn.fetchrow(
        f"SELECT "
        f"  COUNT(*) FILTER (WHERE tracking_done) AS done, "
        f"  COUNT(*) FILTER (WHERE NOT tracking_done) AS pending "
        f"FROM signal_log WHERE {where}",
        *params,
    )
    tracking_completed = int(tracking_row["done"] or 0)
    tracking_pending = int(tracking_row["pending"] or 0)

    stats_row = await conn.fetchrow(
        f"SELECT "
        f"  COUNT(*) AS n, "
        f"  AVG(mfe_7d_pct) AS mfe_avg, "
        f"  AVG(mae_7d_pct) AS mae_avg, "
        f"  PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY mfe_7d_pct) AS mfe_median, "
        f"  PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY mae_7d_pct) AS mae_median "
        f"FROM signal_log "
        f"WHERE {where} AND tracking_done = TRUE "
        f"AND mfe_7d_pct IS NOT NULL AND mae_7d_pct IS NOT NULL",
        *params,
    )
    sample_size = int(stats_row["n"] or 0)

    def _f(v):
        return float(v) if v is not None else None

    return {
        "total": total,
        "by_grade": by_grade,
        "tracking_completed": tracking_completed,
        "tracking_pending": tracking_pending,
        "sample_size": sample_size,
        "mfe_avg": _f(stats_row["mfe_avg"]),
        "mfe_median": _f(stats_row["mfe_median"]),
        "mae_avg": _f(stats_row["mae_avg"]),
        "mae_median": _f(stats_row["mae_median"]),
    }
