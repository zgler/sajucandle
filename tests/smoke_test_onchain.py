"""On-chain Score 스모크 테스트 (BTC·ETH·미지원 코인)."""

import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from sajucandle.quant.onchain import onchain_score

coins = ["BTC-USD", "ETH-USD", "SOL-USD", "DOGE-USD"]
print("=" * 75)
print("On-chain Score (CoinMetrics Community)")
print("=" * 75)
results = []
for sym in coins:
    r = onchain_score(sym)
    results.append(r)
    b = r.get("breakdown", {})
    if not b:
        print(f"{sym:<10} 총점 {r['total']}  [{r.get('warning')}]")
        continue
    print(f"{sym:<10} 총점 {r['total']:>5.1f}  "
          f"Addr={b['active_addresses']:>5.1f} "
          f"Cap={b['cap_trend_90d']:>5.1f} "
          f"DD={b['price_drawdown']:>5.1f} "
          f"MA={b['price_ma200_ratio']:>5.1f} "
          f"Vol={b['volume_7d_vs_30d']:>5.1f}")

out_file = Path(__file__).parent / "smoke_output_onchain.json"
with out_file.open("w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2, default=str)
print(f"\n상세: {out_file}")
