"""TA Score 스모크 테스트.

주식 5종: NVDA, AAPL, MSFT, TSLA, AMZN (벤치: SPY)
코인 5종: BTC-USD, ETH-USD, SOL-USD, DOGE-USD, BNB-USD (벤치: BTC-USD)

각 종목의 1년치 일봉 가져와서 TA Score 산출 + 랭킹.
"""

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from sajucandle.quant.price_data import get_ohlcv
from sajucandle.quant.technical import ta_score_stock, ta_score_coin


def main():
    end = datetime(2026, 4, 23)
    start = end - timedelta(days=400)  # 200MA 여유분 포함

    # ========== 주식 ==========
    print("=" * 70)
    print("주식 TA Score (벤치: SPY)")
    print("=" * 70)
    bench_spy = get_ohlcv("SPY", "stock", start, end)
    print(f"SPY 데이터: {len(bench_spy)}일\n")

    stocks = ["NVDA", "AAPL", "MSFT", "TSLA", "AMZN"]
    stock_results = []
    for sym in stocks:
        try:
            df = get_ohlcv(sym, "stock", start, end)
            if df.empty:
                print(f"[WARN] {sym} empty")
                continue
            score = ta_score_stock(df, bench_spy)
            stock_results.append({"symbol": sym, "rows": len(df), **score})
            b = score["breakdown"]
            print(f"{sym:<6} 총점 {score['total']:>5.1f}  "
                  f"supertrend={b['supertrend']:>5.1f} "
                  f"ma={b['ma_alignment']:>5.1f} "
                  f"rsi={b['rsi']:>5.1f} "
                  f"vol={b['volume_trend']:>5.1f} "
                  f"rs={b['relative_strength']:>5.1f}")
        except Exception as e:
            print(f"[ERROR] {sym}: {e}")

    # ========== 코인 ==========
    print("\n" + "=" * 70)
    print("코인 TA Score (벤치: BTC)")
    print("=" * 70)
    btc = get_ohlcv("BTC-USD", "coin", start, end)
    print(f"BTC 데이터: {len(btc)}일\n")

    coins = ["BTC-USD", "ETH-USD", "SOL-USD", "DOGE-USD", "BNB-USD"]
    coin_results = []
    for sym in coins:
        try:
            df = get_ohlcv(sym, "coin", start, end)
            if df.empty:
                print(f"[WARN] {sym} empty")
                continue
            score = ta_score_coin(df, btc)
            coin_results.append({"symbol": sym, "rows": len(df), **score})
            b = score["breakdown"]
            print(f"{sym:<10} 총점 {score['total']:>5.1f}  "
                  f"supertrend={b['supertrend']:>5.1f} "
                  f"ma_rsi={b['ma200_rsi']:>5.1f} "
                  f"macd={b['macd_momentum']:>5.1f} "
                  f"vol={b['volume_trend']:>5.1f} "
                  f"rs_btc={b['relative_strength_vs_btc']:>5.1f}")
        except Exception as e:
            print(f"[ERROR] {sym}: {e}")

    # 저장
    out = {"stocks": stock_results, "coins": coin_results,
           "evaluated_at": end.isoformat()}
    out_file = Path(__file__).parent / "smoke_output_ta.json"
    with out_file.open("w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n상세 JSON: {out_file}")


if __name__ == "__main__":
    main()
