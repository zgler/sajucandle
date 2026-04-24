"""렌더러 스모크 테스트 — 이미 생성된 signal report를 포맷 변환."""

import sys
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from sajucandle.manseryeok.core import SajuCalculator
from sajucandle.ticker.loader import load_tickers
from sajucandle.signal.engine import generate_signals
from sajucandle.signal.renderer import render_telegram, render_email_html, render_text

calc = SajuCalculator()
tickers = load_tickers(project_root / "data" / "tickers" / "stock_universe_30.csv")
stock_tickers = {s: r for s, r in tickers.items() if r.asset_class == "stock"}

report = generate_signals(
    calc=calc, records=stock_tickers, asset_class="stock",
    target_dt=datetime.now().replace(hour=9, minute=0, second=0, microsecond=0),
    current_holdings={"AAPL", "MSFT", "JPM", "XOM", "KO"},
    top_n=5, watch_buffer=5, saju_filter_threshold=30.0, fast_macro=True,
)

print("=" * 60)
print("[TEXT]")
print("=" * 60)
print(render_text(report))

print()
print("=" * 60)
print("[TELEGRAM]")
print("=" * 60)
print(render_telegram(report))

html = render_email_html(report)
out = Path(__file__).parent / "smoke_output_email.html"
out.write_text(html, encoding="utf-8")
print()
print(f"[HTML] → {out}")
