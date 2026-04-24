"""FA Score 스모크 테스트 (주식 5종)."""

import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from sajucandle.quant.fundamental import fa_score

stocks = ["NVDA", "AAPL", "MSFT", "TSLA", "AMZN", "GOOGL", "META"]
print("=" * 75)
print("FA Score (yfinance 간이 버전)")
print("=" * 75)
results = []
for sym in stocks:
    r = fa_score(sym)
    b = r.get("breakdown", {})
    if not b:
        print(f"{sym:<6} 데이터 없음 (warning: {r.get('warning')})")
        continue
    print(f"{sym:<6} 총점 {r['total']:>5.1f}  "
          f"밸류={b['valuation']:>5.1f} "
          f"수익성={b['quality']:>5.1f} "
          f"FCF={b['fcf_yield']:>5.1f} "
          f"성장={b['growth']:>5.1f} "
          f"재무={b['balance_sheet']:>5.1f}")
    results.append(r)

# Raw 메트릭 확인
print("\nRaw 메트릭 샘플 (NVDA):")
if results:
    for k, v in results[0].get("raw_metrics", {}).items():
        print(f"  {k:<20} {v}")

out_file = Path(__file__).parent / "smoke_output_fa.json"
with out_file.open("w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2, default=str)
print(f"\n상세: {out_file}")
