"""Macro Score 스모크 테스트.

FRED + CoinGecko + ccxt Funding 접근 확인.
네트워크 장애 시 50점(중립) 폴백 확인.
"""

import json
import sys
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from sajucandle.quant.macro import macro_score_stock, SECTOR_ETFS
from sajucandle.quant.crypto_macro import crypto_macro_score


def main():
    asof = datetime(2026, 4, 23)
    print(f"평가 시점: {asof}\n")

    print("=" * 60)
    print("주식 Macro Score (FRED + 섹터 RS)")
    print("=" * 60)
    stock = macro_score_stock(asof=asof)
    print(f"총점: {stock['total']}")
    for k, v in stock["breakdown"].items():
        w = stock["weights"][k]
        print(f"  {k:<15} {v:>5.1f}점 × w{w}% = {v/100*w:>5.1f}")

    print("\n" + "=" * 60)
    print("코인 Macro Score (CoinGecko + FRED + Funding)")
    print("=" * 60)
    coin = crypto_macro_score(asof=asof)
    print(f"총점: {coin['total']}")
    for k, v in coin["breakdown"].items():
        w = coin["weights"][k]
        print(f"  {k:<20} {v:>5.1f}점 × w{w}% = {v/100*w:>5.1f}")
    print(f"\n주의: {coin['note']}")

    # 상세 JSON
    out = {"stock_macro": stock, "coin_macro": coin}
    out_file = Path(__file__).parent / "smoke_output_macro.json"
    with out_file.open("w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n상세: {out_file}")


if __name__ == "__main__":
    main()
