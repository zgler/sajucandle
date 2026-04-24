"""OHLCV 가격 데이터 통합 인터페이스.

자산군별 소스 매핑:
  stock  → yfinance (무료, 일봉 기본)
  coin   → ccxt (Binance 기본, USDT 페어)

캐싱: data/prices/<asset_class>/<symbol>.csv

반환 DataFrame:
  index: DatetimeIndex (UTC 자정)
  columns: open, high, low, close, volume
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import pandas as pd


_ROOT = Path(__file__).resolve().parents[3]
_PRICE_CACHE_DIR = _ROOT / "data" / "prices"

# In-memory cache: (symbol, asset_class) → DataFrame (전체 기간)
# CSV 재읽기 비용 제거. 프로세스 내 재사용.
_MEMORY_CACHE: dict = {}


def _cache_path(symbol: str, asset_class: str) -> Path:
    safe = symbol.replace("/", "_")
    d = _PRICE_CACHE_DIR / asset_class
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{safe}.csv"


def _load_cache(path: Path) -> Optional[pd.DataFrame]:
    if not path.exists():
        return None
    try:
        df = pd.read_csv(path, index_col="date")
        # 인덱스를 명시적으로 datetime으로 변환 (parse_dates가 실패하는 경우 대비)
        df.index = pd.to_datetime(df.index, errors="coerce")
        df = df[df.index.notna()]
        return df
    except Exception:
        return None


def _save_cache(path: Path, df: pd.DataFrame) -> None:
    out = df.copy()
    out.index.name = "date"
    out.to_csv(path)


# ------------------------------------------------------------------
# 주식 (yfinance)
# ------------------------------------------------------------------

def _fetch_stock(symbol: str, start: datetime, end: datetime) -> pd.DataFrame:
    import yfinance as yf
    # yfinance 반환: OHLCV + Adj Close
    df = yf.download(
        symbol, start=start.strftime("%Y-%m-%d"),
        end=(end + timedelta(days=1)).strftime("%Y-%m-%d"),
        interval="1d", progress=False, auto_adjust=True,
    )
    if df.empty:
        return pd.DataFrame()
    # 멀티인덱스 처리
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.rename(columns={
        "Open": "open", "High": "high", "Low": "low",
        "Close": "close", "Volume": "volume",
    })
    df = df[["open", "high", "low", "close", "volume"]]
    df.index = pd.to_datetime(df.index).tz_localize(None)
    return df


# ------------------------------------------------------------------
# 코인 (ccxt → Binance 기본)
# ------------------------------------------------------------------

def _fetch_coin(symbol: str, start: datetime, end: datetime,
                exchange_id: str = "binance") -> pd.DataFrame:
    import ccxt
    ex_cls = getattr(ccxt, exchange_id)
    ex = ex_cls({"enableRateLimit": True})
    # 심볼 정규화: BTC-USD → BTC/USDT (Binance 관행)
    sym = symbol.replace("-USD", "/USDT").replace("-USDT", "/USDT")
    if "/" not in sym:
        sym = f"{sym}/USDT"

    since_ms = int(start.replace(tzinfo=timezone.utc).timestamp() * 1000)
    end_ms = int(end.replace(tzinfo=timezone.utc).timestamp() * 1000)

    all_rows = []
    cur_since = since_ms
    while cur_since < end_ms:
        batch = ex.fetch_ohlcv(sym, timeframe="1d", since=cur_since, limit=1000)
        if not batch:
            break
        all_rows.extend(batch)
        last_ts = batch[-1][0]
        if last_ts <= cur_since:
            break
        cur_since = last_ts + 24 * 3600 * 1000
        if len(batch) < 1000:
            break

    if not all_rows:
        return pd.DataFrame()
    df = pd.DataFrame(all_rows, columns=["ts", "open", "high", "low", "close", "volume"])
    df["date"] = pd.to_datetime(df["ts"], unit="ms").dt.tz_localize(None)
    df = df.drop_duplicates(subset=["date"]).set_index("date")
    df = df[["open", "high", "low", "close", "volume"]]
    df = df[(df.index >= pd.Timestamp(start)) & (df.index <= pd.Timestamp(end))]
    return df


# ------------------------------------------------------------------
# 퍼블릭 API
# ------------------------------------------------------------------

def get_ohlcv(
    symbol: str,
    asset_class: str,
    start: datetime,
    end: datetime,
    use_cache: bool = True,
    force_refresh: bool = False,
) -> pd.DataFrame:
    """OHLCV 일봉 데이터 조회. 메모리 → CSV → 외부 API 3단계 캐시.

    Returns
    -------
    DataFrame (DatetimeIndex, columns=open·high·low·close·volume).
    """
    mem_key = (symbol, asset_class)

    # 1단계: 메모리 캐시
    if use_cache and not force_refresh and mem_key in _MEMORY_CACHE:
        cached = _MEMORY_CACHE[mem_key]
        mask = (cached.index >= pd.Timestamp(start)) & (cached.index <= pd.Timestamp(end))
        subset = cached[mask]
        if not subset.empty and subset.index.min() <= pd.Timestamp(start) + timedelta(days=7):
            return subset

    # 2단계: CSV 파일 캐시
    cache = _cache_path(symbol, asset_class)
    if use_cache and not force_refresh:
        cached = _load_cache(cache)
        if cached is not None and not cached.empty:
            _MEMORY_CACHE[mem_key] = cached  # 메모리 승격
            mask = (cached.index >= pd.Timestamp(start)) & (cached.index <= pd.Timestamp(end))
            subset = cached[mask]
            if not subset.empty and subset.index.min() <= pd.Timestamp(start) + timedelta(days=7):
                return subset

    # 3단계: 외부 API
    if asset_class == "stock":
        df = _fetch_stock(symbol, start, end)
    elif asset_class == "coin":
        df = _fetch_coin(symbol, start, end)
    else:
        raise ValueError(f"Unknown asset_class: {asset_class}")

    if not df.empty and use_cache:
        _save_cache(cache, df)
        _MEMORY_CACHE[mem_key] = df
    return df
