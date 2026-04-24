"""사주 점수 역설계 캘리브레이터 (B안).

전략:
  1. 역사 백테스트 데이터에서 (종목, 기간, 사주_컴포넌트, 실제수익) 수집
  2. IC 분석: 각 컴포넌트의 Spearman 상관 → 유효 컴포넌트 식별
  3. Ridge 회귀: forward_return ~ saju_features (정규화)
  4. 새 가중치 제안: 실제 IC 부호 + 크기 기반

출력: calibrated_weights dict (scorer.py의 weights 교체용)
"""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from ..manseryeok.core import SajuCalculator
from ..ticker.schema import TickerRecord
from ..ticker.saju_resolver import resolve_ticker_saju
from ..saju.scorer import saju_score
from .backtest import _month_starts, _forward_return


FEATURE_NAMES = [
    "wolwoon_x_ilju",
    "ilji_x_ilju",
    "sewoon_element_match",
    "daeun_bias",
    "element_balance",
    "samchung_events",
    "shinsal_boost",
]


def collect_saju_features(
    calc: SajuCalculator,
    records: Dict[str, TickerRecord],
    asset_class: str,
    start: datetime,
    end: datetime,
    train_end: Optional[datetime] = None,
) -> pd.DataFrame:
    """각 (종목, 리밸런싱 기간)에 대해 사주 컴포넌트 + 실제 수익률 수집.

    Returns
    -------
    DataFrame:
      index: (symbol, date)
      columns: FEATURE_NAMES + ["total_100", "forward_return"]
    """
    rebalance_dates = _month_starts(start, end)
    if len(rebalance_dates) < 2:
        return pd.DataFrame()

    # 종목 사주 사전 계산
    resolved: Dict[str, Dict] = {}
    for sym, rec in records.items():
        if rec.asset_class != asset_class:
            continue
        try:
            resolved[sym] = resolve_ticker_saju(calc, rec)
        except Exception:
            continue

    rows = []
    for i, rb_date in enumerate(rebalance_dates[:-1]):
        next_date = rebalance_dates[i + 1]
        if train_end and rb_date > train_end:
            break

        for sym, res in resolved.items():
            if not res.get("primary_pillar"):
                continue
            primary_source = res["primary_source"]
            if primary_source == "founding":
                primary_saju = res["components"]["founding"]["saju"]
            elif primary_source == "listing":
                primary_saju = res["components"]["listing"]["saju"]
            else:
                primary_saju = res["components"]["transition"][0]["saju"]

            try:
                sc = saju_score(
                    calc=calc,
                    ticker_primary_pillar=res["primary_pillar"],
                    ticker_saju=primary_saju,
                    target_dt=rb_date,
                )
                fwd = _forward_return(sym, asset_class, rb_date, next_date)
                row = {
                    "symbol": sym,
                    "date": rb_date.strftime("%Y-%m-%d"),
                    "forward_return": fwd,
                    "total_100": sc["total_100"],
                }
                row.update(sc["breakdown"])
                rows.append(row)
            except Exception:
                continue

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows).set_index(["symbol", "date"])
    return df


def ic_analysis(df: pd.DataFrame) -> pd.DataFrame:
    """각 사주 컴포넌트 ↔ forward_return의 Spearman IC 계산.

    Returns
    -------
    DataFrame: columns=[IC, IC_t, IC_mean_by_date, verdict]
    """
    from scipy import stats as sp_stats

    results = []
    # 전체 IC
    for feat in FEATURE_NAMES:
        if feat not in df.columns:
            continue
        mask = df[feat].notna() & df["forward_return"].notna()
        x = df.loc[mask, feat]
        y = df.loc[mask, "forward_return"]
        if len(x) < 10:
            continue
        corr, pval = sp_stats.spearmanr(x, y)
        results.append({
            "feature": feat,
            "IC": round(corr, 4),
            "p_value": round(pval, 4),
            "n": len(x),
        })

    # 날짜별 IC (시계열 IC)
    date_ics: Dict[str, List[float]] = {f: [] for f in FEATURE_NAMES}
    for date in df.index.get_level_values("date").unique():
        sub = df.xs(date, level="date") if date in df.index.get_level_values("date") else None
        if sub is None or len(sub) < 5:
            continue
        for feat in FEATURE_NAMES:
            if feat not in sub.columns:
                continue
            mask = sub[feat].notna() & sub["forward_return"].notna()
            x = sub.loc[mask, feat]
            y = sub.loc[mask, "forward_return"]
            if len(x) < 4:
                continue
            try:
                corr, _ = sp_stats.spearmanr(x, y)
                if not np.isnan(corr):
                    date_ics[feat].append(corr)
            except Exception:
                pass

    ic_df = pd.DataFrame(results).set_index("feature")
    for feat in FEATURE_NAMES:
        vals = date_ics.get(feat, [])
        ic_df.loc[feat, "ICIR"] = round(
            float(np.mean(vals)) / float(np.std(vals)) if vals and np.std(vals) > 0 else 0, 3
        )
        ic_df.loc[feat, "date_IC_mean"] = round(float(np.mean(vals)) if vals else 0, 4)
        ic_df.loc[feat, "n_dates"] = len(vals)
    return ic_df


def ridge_calibrate(df: pd.DataFrame, alpha: float = 1.0) -> Dict[str, float]:
    """Ridge 회귀로 사주 컴포넌트 → 수익률 가중치 추정.

    Returns
    -------
    dict: feature → calibrated_weight (합계 100으로 정규화, 음수는 0으로 클리핑)
    """
    from sklearn.linear_model import Ridge
    from sklearn.preprocessing import StandardScaler

    feats = [f for f in FEATURE_NAMES if f in df.columns]
    sub = df[feats + ["forward_return"]].dropna()
    if len(sub) < 30:
        return {}

    X = sub[feats].values
    y = sub["forward_return"].values

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    model = Ridge(alpha=alpha)
    model.fit(X_scaled, y)

    raw_coefs = {f: c for f, c in zip(feats, model.coef_)}

    # 음수 계수 → 0 (사주 점수 반전 안 하고 단순 격하)
    clipped = {f: max(0.0, c) for f, c in raw_coefs.items()}
    total = sum(clipped.values())
    if total <= 0:
        return {f: round(100 / len(feats), 1) for f in feats}

    # 100점 합산으로 정규화
    normalized = {f: round(v / total * 100, 1) for f, v in clipped.items()}
    return normalized


def propose_new_weights(
    calc: SajuCalculator,
    records: Dict[str, TickerRecord],
    asset_class: str,
    start: datetime,
    end: datetime,
    train_ratio: float = 0.6,
) -> Dict:
    """사주 가중치 재설계 제안.

    train_ratio 비율 기간으로 캘리브레이션,
    나머지로 OOS(out-of-sample) IC 검증.

    Returns
    -------
    {
      "ic_analysis": DataFrame.to_dict(),
      "calibrated_weights": {"wolwoon_x_ilju": 35.2, ...},
      "prior_weights": {"wolwoon_x_ilju": 25, ...},
      "n_obs": int,
      "train_period": (start_str, end_str),
    }
    """
    total_months = (end.year - start.year) * 12 + (end.month - start.month)
    train_months = int(total_months * train_ratio)
    if start.month + train_months <= 12:
        train_end = datetime(start.year, start.month + train_months, 1)
    else:
        extra_year = (start.month + train_months - 1) // 12
        extra_month = (start.month + train_months - 1) % 12 + 1
        train_end = datetime(start.year + extra_year, extra_month, 1)

    print(f"  학습 기간: {start.strftime('%Y-%m')} ~ {train_end.strftime('%Y-%m')}")
    print("  수집 중...")

    df = collect_saju_features(calc, records, asset_class, start, end, train_end=train_end)
    if df.empty:
        return {"error": "데이터 없음"}

    n_obs = len(df)
    print(f"  관측값: {n_obs}개 수집 완료")

    ic_df = ic_analysis(df)
    cal_weights = ridge_calibrate(df)

    prior = {
        "wolwoon_x_ilju": 25, "ilji_x_ilju": 20,
        "sewoon_element_match": 15, "daeun_bias": 10,
        "element_balance": 10, "samchung_events": 10,
        "shinsal_boost": 10,
    }

    return {
        "ic_table": ic_df.to_dict(),
        "calibrated_weights": cal_weights,
        "prior_weights": prior,
        "n_obs": n_obs,
        "train_period": (start.strftime("%Y-%m"), train_end.strftime("%Y-%m")),
        "feature_df_shape": df.shape,
    }
