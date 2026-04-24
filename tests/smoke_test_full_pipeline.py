"""전체 파이프라인 통합 스모크 테스트.

목표:
1. 20개 샘플 종목의 다층 사주 해석
2. 오늘 시점의 사주 점수 계산
3. 점수 순 랭킹 출력 (자산군별 분리)
"""

import json
import sys
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from sajucandle.manseryeok.core import SajuCalculator
from sajucandle.saju.scorer import saju_score
from sajucandle.ticker.loader import load_tickers
from sajucandle.ticker.saju_resolver import resolve_ticker_saju


def main():
    calc = SajuCalculator()
    tickers = load_tickers()
    print(f"[LOAD] 종목 {len(tickers)}개 로드")
    print(f"[ENGINE] 만세력 범위 {calc.min_year}~{calc.max_year}\n")

    target_dt = datetime(2026, 4, 23, 12, 0)
    print(f"[TARGET] 평가 시점: {target_dt}\n")

    rankings = []
    for sym, rec in tickers.items():
        try:
            resolved = resolve_ticker_saju(calc, rec)
            if not resolved.get("primary_pillar"):
                continue
            # primary 구성요소의 전체 4주 사주
            primary_source = resolved["primary_source"]
            if primary_source == "founding":
                primary_saju = resolved["components"]["founding"]["saju"]
            elif primary_source == "listing":
                primary_saju = resolved["components"]["listing"]["saju"]
            else:
                primary_saju = resolved["components"]["transition"][0]["saju"]

            score = saju_score(
                calc=calc,
                ticker_primary_pillar=resolved["primary_pillar"],
                ticker_saju=primary_saju,
                target_dt=target_dt,
            )
            rankings.append({
                "symbol": sym,
                "name": rec.name,
                "asset_class": rec.asset_class,
                "primary_pillar": resolved["primary_pillar"],
                "primary_source": primary_source,
                "total_100": score["total_100"],
                "breakdown": score["breakdown"],
                "weighted": score["weighted"],
            })
        except Exception as e:
            print(f"[ERROR] {sym}: {e}")
            continue

    # 자산군별 랭킹
    for asset_class in ["coin", "stock"]:
        subset = [r for r in rankings if r["asset_class"] == asset_class]
        subset.sort(key=lambda r: r["total_100"], reverse=True)
        print(f"\n{'=' * 80}")
        print(f"[RANKING] {asset_class.upper()} (총 {len(subset)}개)")
        print(f"{'=' * 80}")
        print(f"{'순위':<4}{'종목':<12}{'일주':<6}{'출처':<12}{'점수':>8}  {'세부'}")
        print("-" * 80)
        for i, r in enumerate(subset[:10], 1):
            w = r["weighted"]
            detail = (
                f"월={w['wolwoon_x_ilju']:4.1f} 일={w['ilji_x_ilju']:4.1f}"
                f" 세={w['sewoon_element_match']:4.1f} 균={w['element_balance']:4.1f}"
                f" 신={w['shinsal_boost']:4.1f}"
            )
            print(f"{i:<4}{r['symbol']:<12}{r['primary_pillar']:<6}"
                  f"{r['primary_source']:<12}{r['total_100']:>7.1f}  {detail}")

    # 상세 JSON 저장
    out_file = Path(__file__).parent / "smoke_output_full_pipeline.json"
    with out_file.open("w", encoding="utf-8") as f:
        json.dump(rankings, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n상세: {out_file}")


if __name__ == "__main__":
    main()
