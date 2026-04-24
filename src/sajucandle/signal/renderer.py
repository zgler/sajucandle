"""구독자 알림 렌더러 — 이메일 / 텔레그램 포맷.

이메일: HTML (테이블 + 색상 뱃지)
텔레그램: Markdown V2 (이모지 + 굵게)
"""

from __future__ import annotations


from .engine import SignalReport, SignalType

# 신호별 이모지/색상
_EMOJI = {
    SignalType.BUY:   "🟢",
    SignalType.HOLD:  "🔵",
    SignalType.SELL:  "🔴",
    SignalType.WATCH: "🟡",
    SignalType.KILL:  "⚫",
}

_HTML_COLOR = {
    SignalType.BUY:   "#16a34a",
    SignalType.HOLD:  "#2563eb",
    SignalType.SELL:  "#dc2626",
    SignalType.WATCH: "#d97706",
    SignalType.KILL:  "#6b7280",
}


# ── 텔레그램 ──────────────────────────────────────────────────────────────

def render_telegram(report: SignalReport) -> str:
    """텔레그램 Markdown V2 포맷."""
    dt_str = report.target_dt.strftime("%Y년 %m월")
    lines = [
        f"*📊 사주캔들 {dt_str} 리밸런싱 신호*",
        f"_유니버스 {report.universe_size}종 → 사주 통과 {report.survivors}종_",
        "",
    ]

    order = [SignalType.BUY, SignalType.HOLD, SignalType.SELL,
             SignalType.WATCH, SignalType.KILL]

    for sig_type in order:
        items = report.by_signal(sig_type)
        if not items:
            continue
        emoji = _EMOJI[sig_type]
        label = sig_type.value
        lines.append(f"{emoji} *{label}*")
        for t in sorted(items, key=lambda x: x.rank or 999):
            # 텔레그램 MDv2: 특수문자(#, -, . 등)는 이스케이프 필요
            rank_str = _tg_escape(f"#{t.rank}") if t.rank else _tg_escape("—")
            saju_str = _tg_escape(f"{t.saju_score:.0f}")
            quant_str = _tg_escape(f"{t.quant_score:.0f}")
            sym = _tg_escape(t.symbol)
            lines.append(
                f"  `{sym:<8}` {rank_str:<4} "
                f"사주 {saju_str} / 퀀트 {quant_str}"
            )
        lines.append("")

    if report.new_holdings:
        held = " ".join(sorted(report.new_holdings))
        lines.append(f"📋 *이번 달 보유*: `{_tg_escape(held)}`")

    return "\n".join(lines)


def _tg_escape(text: str) -> str:
    """텔레그램 MarkdownV2 특수문자 이스케이프."""
    special = r"_*[]()~`>#+-=|{}.!"
    return "".join(f"\\{c}" if c in special else c for c in str(text))


# ── 이메일 HTML ───────────────────────────────────────────────────────────

def render_email_html(report: SignalReport) -> str:
    """이메일용 HTML 리포트."""
    dt_str = report.target_dt.strftime("%Y년 %m월 %d일")
    rows = _build_rows(report)

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<style>
  body {{ font-family: -apple-system, sans-serif; background: #f9fafb; margin: 0; padding: 24px; }}
  .card {{ background: white; border-radius: 12px; padding: 24px; max-width: 640px;
           margin: 0 auto; box-shadow: 0 1px 4px rgba(0,0,0,.08); }}
  h1 {{ font-size: 20px; margin: 0 0 4px; color: #111827; }}
  .sub {{ color: #6b7280; font-size: 13px; margin-bottom: 20px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 14px; }}
  th {{ background: #f3f4f6; padding: 8px 10px; text-align: left;
        color: #374151; font-weight: 600; border-bottom: 1px solid #e5e7eb; }}
  td {{ padding: 9px 10px; border-bottom: 1px solid #f3f4f6; vertical-align: middle; }}
  tr:last-child td {{ border-bottom: none; }}
  .badge {{ display: inline-block; padding: 2px 8px; border-radius: 9999px;
             font-size: 12px; font-weight: 700; color: white; }}
  .holdings {{ margin-top: 16px; background: #f0fdf4; border-radius: 8px;
               padding: 12px 16px; font-size: 13px; color: #15803d; }}
</style>
</head>
<body>
<div class="card">
  <h1>📊 사주캔들 리밸런싱 신호</h1>
  <p class="sub">{dt_str} · 유니버스 {report.universe_size}종 → 사주 통과 {report.survivors}종</p>
  <table>
    <tr>
      <th>신호</th><th>종목</th><th>순위</th>
      <th>사주점수</th><th>퀀트점수</th><th>사유</th>
    </tr>
    {rows}
  </table>
  <div class="holdings">
    📋 <strong>이번 달 보유:</strong> {" / ".join(sorted(report.new_holdings))}
  </div>
</div>
</body>
</html>"""


def _build_rows(report: SignalReport) -> str:
    order = [SignalType.BUY, SignalType.HOLD, SignalType.SELL,
             SignalType.WATCH, SignalType.KILL]
    html = []
    for sig_type in order:
        items = report.by_signal(sig_type)
        for t in sorted(items, key=lambda x: x.rank or 999):
            color = _HTML_COLOR[sig_type]
            rank_str = f"#{t.rank}" if t.rank else "—"
            html.append(
                f"<tr>"
                f"<td><span class='badge' style='background:{color}'>{t.signal.value}</span></td>"
                f"<td><strong>{t.symbol}</strong></td>"
                f"<td>{rank_str}</td>"
                f"<td>{t.saju_score:.0f}</td>"
                f"<td>{t.quant_score:.0f}</td>"
                f"<td style='color:#6b7280;font-size:12px'>{t.reason}</td>"
                f"</tr>"
            )
    return "\n    ".join(html)


# ── 텍스트 (콘솔/슬랙) ───────────────────────────────────────────────────

def render_text(report: SignalReport) -> str:
    """plain-text 포맷 (콘솔 출력, 슬랙 코드블록 등)."""
    return report.summary()
