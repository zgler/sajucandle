"""SajuCandle 차트 분석 명세 → PDF.

reportlab + 맑은 고딕 TTF. 간단 마크다운 → Platypus 파서.
"""
from __future__ import annotations

import re
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    KeepTogether,
    PageBreak,
    Paragraph,
    Preformatted,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# ── Korean font ──
FONT_REG = "C:/Windows/Fonts/malgun.ttf"
FONT_BD = "C:/Windows/Fonts/malgunbd.ttf"
pdfmetrics.registerFont(TTFont("Malgun", FONT_REG))
pdfmetrics.registerFont(TTFont("MalgunBold", FONT_BD))

BASE_STYLES = getSampleStyleSheet()


def _style(name: str, parent_name: str, **kw) -> ParagraphStyle:
    parent = BASE_STYLES[parent_name]
    merged = {
        "fontName": "Malgun",
        "alignment": TA_LEFT,
        "leading": kw.pop("leading", parent.fontSize * 1.35),
    }
    merged.update(kw)
    return ParagraphStyle(name, parent=parent, **merged)


STYLES = {
    "title": _style("T", "Title", fontName="MalgunBold", fontSize=20, spaceAfter=14),
    "h1": _style("H1", "Heading1", fontName="MalgunBold", fontSize=16,
                 spaceBefore=16, spaceAfter=8, textColor=colors.HexColor("#1a1a1a")),
    "h2": _style("H2", "Heading2", fontName="MalgunBold", fontSize=13,
                 spaceBefore=12, spaceAfter=6, textColor=colors.HexColor("#2a2a2a")),
    "h3": _style("H3", "Heading3", fontName="MalgunBold", fontSize=11,
                 spaceBefore=8, spaceAfter=4),
    "body": _style("Body", "BodyText", fontSize=9.5, leading=13, spaceAfter=6),
    "code": _style("Code", "Code", fontName="Malgun", fontSize=8.3, leading=11,
                   leftIndent=6, rightIndent=6, spaceBefore=4, spaceAfter=6,
                   backColor=colors.HexColor("#f4f4f4"),
                   borderColor=colors.HexColor("#d0d0d0"),
                   borderWidth=0.5, borderPadding=4),
    "bullet": _style("Bullet", "BodyText", fontSize=9.5, leading=13,
                     leftIndent=14, bulletIndent=4, spaceAfter=3),
    "quote": _style("Quote", "BodyText", fontSize=9.5, leading=13,
                    leftIndent=14, textColor=colors.HexColor("#555"),
                    spaceAfter=6),
}


def _escape_inline(s: str) -> str:
    """Platypus Paragraph mini-markup: **bold**, `code` → XML tags."""
    # XML special chars
    s = s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    # **bold** (non-greedy, double-asterisk)
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
    # `code` — monospace 느낌 X, 그냥 색만 다르게
    s = re.sub(
        r"`([^`]+)`",
        r'<font color="#b84d1a">\1</font>',
        s,
    )
    return s


def _parse_table(lines: list[str]) -> Table:
    """`| a | b | ... |` 여러 줄 → Table. 2번째 줄의 `---`는 구분행."""
    rows = []
    for ln in lines:
        ln = ln.strip()
        if not ln:
            continue
        if set(ln.replace("|", "").replace("-", "").strip()) == set():
            continue  # separator row
        cells = [c.strip() for c in ln.strip("|").split("|")]
        rows.append(cells)
    if not rows:
        return None
    # 같은 폭으로 Paragraph 감싸기 (긴 셀 wrap)
    cell_style = _style("Cell", "BodyText", fontSize=8.5, leading=11)
    para_rows = [[Paragraph(_escape_inline(c), cell_style) for c in r] for r in rows]
    t = Table(para_rows, repeatRows=1, colWidths=None)
    t.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "Malgun"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8ecef")),
        ("FONTNAME", (0, 0), (-1, 0), "MalgunBold"),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#c0c0c0")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return t


def md_to_story(md: str) -> list:
    story = []
    lines = md.splitlines()
    i = 0
    n = len(lines)

    while i < n:
        ln = lines[i]
        stripped = ln.strip()

        # Heading
        if stripped.startswith("# "):
            story.append(Paragraph(_escape_inline(stripped[2:]), STYLES["title"]))
            i += 1
            continue
        if stripped.startswith("## "):
            story.append(Paragraph(_escape_inline(stripped[3:]), STYLES["h1"]))
            i += 1
            continue
        if stripped.startswith("### "):
            story.append(Paragraph(_escape_inline(stripped[4:]), STYLES["h2"]))
            i += 1
            continue
        if stripped.startswith("#### "):
            story.append(Paragraph(_escape_inline(stripped[5:]), STYLES["h3"]))
            i += 1
            continue

        # Fenced code block
        if stripped.startswith("```"):
            j = i + 1
            code_lines = []
            while j < n and not lines[j].strip().startswith("```"):
                code_lines.append(lines[j])
                j += 1
            story.append(Preformatted("\n".join(code_lines), STYLES["code"]))
            i = j + 1
            continue

        # Horizontal rule
        if stripped.startswith("---"):
            story.append(Spacer(1, 6))
            story.append(Paragraph(
                '<para><font color="#c0c0c0">' + "─" * 60 + "</font></para>",
                STYLES["body"],
            ))
            story.append(Spacer(1, 4))
            i += 1
            continue

        # Table (| 로 시작)
        if stripped.startswith("|"):
            j = i
            table_lines = []
            while j < n and lines[j].strip().startswith("|"):
                table_lines.append(lines[j])
                j += 1
            t = _parse_table(table_lines)
            if t is not None:
                story.append(KeepTogether(t))
                story.append(Spacer(1, 6))
            i = j
            continue

        # Blockquote
        if stripped.startswith("> "):
            story.append(Paragraph(_escape_inline(stripped[2:]), STYLES["quote"]))
            i += 1
            continue

        # Unordered list
        if re.match(r"^[-*] ", stripped):
            # collect consecutive bullets
            bullets = []
            while i < n:
                s2 = lines[i].strip()
                if re.match(r"^[-*] ", s2):
                    bullets.append(s2[2:])
                    i += 1
                else:
                    break
            for b in bullets:
                story.append(Paragraph(
                    "• " + _escape_inline(b), STYLES["bullet"]
                ))
            continue

        # Ordered list
        m = re.match(r"^(\d+)\.\s+(.*)", stripped)
        if m:
            items = []
            while i < n:
                m2 = re.match(r"^(\d+)\.\s+(.*)", lines[i].strip())
                if m2:
                    items.append((m2.group(1), m2.group(2)))
                    i += 1
                else:
                    break
            for num, txt in items:
                story.append(Paragraph(
                    f"{num}. " + _escape_inline(txt), STYLES["bullet"]
                ))
            continue

        # Empty
        if not stripped:
            story.append(Spacer(1, 3))
            i += 1
            continue

        # Regular paragraph — 연속된 non-empty non-special 줄 합치기
        para_lines = []
        while i < n:
            s2 = lines[i]
            ss2 = s2.strip()
            if (not ss2 or ss2.startswith("#") or ss2.startswith("```")
                or ss2.startswith("|") or ss2.startswith("> ")
                or re.match(r"^[-*] ", ss2) or re.match(r"^\d+\.\s+", ss2)
                or ss2.startswith("---")):
                break
            para_lines.append(ss2)
            i += 1
        if para_lines:
            story.append(Paragraph(
                _escape_inline(" ".join(para_lines)), STYLES["body"]
            ))

    return story


# ─────────────────────────────────────────────
# SPEC CONTENT
# ─────────────────────────────────────────────

SPEC_MD = r"""# SajuCandle 차트 분석 로직 — 기술 명세

> 다른 AI가 이 시스템을 이해/재현할 수 있도록 작성. 모든 숫자와 임계값은 현재 `main` 브랜치 코드(Week 10 Phase 2 기준)와 일치.

## 0. 큰 그림

**최종 출력:** 각 심볼에 대해 `composite_score (0~100)` + `signal_grade (강진입/진입/관망/회피)` + (조건부) `TradeSetup (entry/SL/TP1/TP2/R:R/risk_pct)`

**데이터 흐름:**

```
(1h/4h/1d OHLCV) → analyze() → AnalysisResult(composite_score, structure, alignment, sr_levels, atr_1d, rsi_1h, volume_ratio_1d)
       ↓
사주 composite × 0.1 + analysis.composite_score × 0.9 → final_score (round + clamp 0~100)
       ↓
_grade_signal(final_score, analysis) → "강진입"|"진입"|"관망"|"회피"
       ↓
(진입/강진입일 때만) compute_trade_setup(current_price, atr_1d, sr_levels) → TradeSetup
```

---

## 1. 입력 데이터

각 심볼마다 3개 타임프레임 OHLCV `Kline(open_time, open, high, low, close, volume)` 리스트:

| TF | limit | 용도 |
|----|-------|------|
| 1d | 100 | 시장 구조, Volume Profile, S/R 식별, ATR(14) |
| 4h | 150 | 멀티 TF 정렬 |
| 1h | 200 | 멀티 TF 정렬, RSI(14) |

- BTC 계열: Binance `data-api.binance.vision` (24/7)
- 미국주식: yfinance. 4h는 1h봉을 pandas `resample("4h", origin="epoch")`로 집계. 1h은 60일 제한.

---

## 2. Swing Point 감지 (`analysis/swing.py`)

**Fractals + ATR prominence filter.**

```
fractal_window = 5
atr_multiplier = 1.5
atr_period     = 14
```

### 알고리즘
1. ATR(14) 계산 (Wilder smoothing: 처음 14봉 SMA → 이후 `avg = (avg*13 + TR) / 14`).
2. `threshold = ATR × 1.5`.
3. 각 중심봉 i (i = 5 ~ n-6)에 대해:

- **Swing High**: `center.high`가 좌/우 5봉 각각의 high보다 **전부** 크면 후보. Prominence = `center.high - max(좌/우 10봉 high)`. `prominence >= threshold`이면 채택.
- **Swing Low**: 대칭. `min(좌/우 10봉 low) - center.low >= threshold`.

4. 반환: `SwingPoint(index, timestamp, price, kind="high"|"low")` 리스트 (시간순).

**포인트:** `atr_multiplier=0`이면 필터 off (모든 fractal 채택). 봉 < 11개면 빈 리스트.

---

## 3. 시장 구조 분류 (`analysis/structure.py`)

Swing points → `MarketStructure` enum 5종 + score.

### 판정 규칙 (우선순위 순)

```
highs = [sp for sp in swings if sp.kind == "high"]
lows  = [sp for sp in swings if sp.kind == "low"]
```

1. **UPTREND** (score=70): `len(highs)≥3 AND len(lows)≥3 AND highs[-1]>highs[-2]>highs[-3] AND lows[-1]>lows[-2]>lows[-3]` — 마지막 3개 high + 3개 low 모두 상승.
2. **BREAKDOWN** (score=30): `len(highs)≥2 AND len(lows)≥3 AND highs[-1]>highs[-2] AND lows[-1]<lows[-2]` — 고점은 오르는데 저점이 깨짐 (상승 추세 이탈 전조).
3. **BREAKOUT** (score=80): `len(highs)≥3 AND highs[-1] > max(highs[:-1]) × 1.03` — 최근 고점이 이전 모든 고점보다 3% 이상 돌파.
4. **DOWNTREND** (score=20): UPTREND의 대칭. 3개 연속 LH + LL.
5. **RANGE** (score=50): 그 외 전부 (충분한 swing 없음 포함).

**score 매핑:** `{UPTREND:70, BREAKOUT:80, RANGE:50, BREAKDOWN:30, DOWNTREND:20}`.

**반환:** `StructureAnalysis(state, last_high, last_low, score)`.

---

## 4. 단일 TF 트렌드 방향 (`analysis/timeframe.py`)

각 TF (1h, 4h, 1d) 개별 판정. EMA50 기반.

### 알고리즘
1. EMA50 전 시리즈 계산 (초기값 SMA50, 이후 `α = 2/51`).
2. `threshold = last_ema × 0.0001` (0.01%, 노이즈 컷).
3. 상대 위치/기울기/단기 close 3조건 판정:

- `above = last_close > last_ema + threshold`
- `below = last_close < last_ema - threshold`
- `rising = (last_ema - ema[-6]) > threshold` (EMA 5봉 기울기)
- `falling = (last_ema - ema[-6]) < -threshold`
- `close_rising = (closes[-1] - closes[-6]) > threshold`
- `close_falling = (closes[-1] - closes[-6]) < -threshold`

4. 판정:

- `above AND rising AND close_rising` → **UP**
- `below AND falling AND close_falling` → **DOWN**
- 그 외 → **FLAT**

**봉 < 56개면** FLAT (EMA50 + 5봉 기울기 계산 불가).

---

## 5. 멀티 TF 정렬 (`analysis/multi_timeframe.py`)

```
t1h, t4h, t1d = trend_direction(each TF)
ups   = count(UP)
downs = count(DOWN)

aligned = (ups == 3) OR (downs == 3)

bias:
  ups > downs   → "bullish"
  downs > ups   → "bearish"
  ups == downs  → "mixed"

score = round((ups - downs + 3) / 6 × 100)   # -3..3 → 0..100
# 보정:
if aligned AND bias == "bullish":  score = max(score, 90)
if aligned AND bias == "bearish":  score = min(score, 10)
```

**반환:** `Alignment(tf_1h, tf_4h, tf_1d, aligned, bias, score)`.

| 조합 예시 | score |
|-----------|-------|
| UP/UP/UP | 90+ (강정렬 bullish) |
| DOWN/DOWN/DOWN | 10- (강정렬 bearish) |
| UP/UP/FLAT | ≈67 |
| UP/FLAT/DOWN | 50 |
| UP/DOWN/DOWN | ≈33 |

---

## 6. 보조 지표 — RSI(1h) & Volume(1d)

**RSI(14):** 표준 Wilder. 1h 봉 closes 사용. 길이 부족 시 50.0 반환.

**RSI → score 매핑 (`_rsi_score`):**

```
RSI ≤ 30  → 70  (과매도, 매수 유리)
RSI ≤ 45  → 55
RSI ≤ 55  → 50
RSI ≤ 70  → 40
RSI > 70  → 20  (과매수, 매수 불리)
```

**volume_ratio(1d):** `volumes[-1] / mean(volumes[-21:-1])`. 최근 1일 볼륨 대 과거 20일 평균.

**vol → score 매핑 (`_volume_score`):**

```
ratio ≥ 1.5  → 65
ratio ≥ 1.0  → 55
ratio ≥ 0.5  → 45
ratio < 0.5  → 35
```

---

## 7. `analyze()` — composite_score 조합 (`analysis/composite.py`)

```
swings = detect_swings(klines_1d, 5, 1.5)
if not swings: swings = detect_swings(klines_1h, 5, 1.5)   # 폴백

structure = classify_structure(swings)
alignment = compute_alignment(k1h, k4h, k1d)
rsi_1h    = rsi(1h closes, 14)
vr_1d     = volume_ratio(1d volumes, 20)

# 폴백 보정: swing 없으면 structure(=RANGE 50)에 alignment 방향 섞음
structure_score = structure.score
if not swings:
    structure_score = round(0.5 * structure.score + 0.5 * alignment.score)

composite = round(
    0.45 × structure_score +
    0.35 × alignment.score +
    0.10 × _rsi_score(rsi_1h) +
    0.10 × _volume_score(vr_1d)
)
composite = clamp(composite, 0, 100)
```

ATR(14, 1d)도 이 시점에 계산. S/R 레벨은 §10 참조.

**예시 계산 (강세 상황):**

- UPTREND structure = 70
- 3TF 전부 UP aligned = 90
- RSI(1h) 35 → 55
- vol 1.2x → 55
- `0.45×70 + 0.35×90 + 0.10×55 + 0.10×55 = 31.5 + 31.5 + 5.5 + 5.5 = 74`

---

## 8. 사주와 합산 → final_score (`signal_service.py`)

```
saju_composite = ScoreService.compute(profile, target_date, asset_class).composite_score  # 0~100
analysis = analyze(k1h, k4h, k1d)

final = round(0.1 × saju_composite + 0.9 × analysis.composite_score)
final = clamp(final, 0, 100)
```

**사주 가중치 0.1**: Week 8에서 이전 0.4 → 0.1로 강등. 실제 트레이딩 판단은 차트 중심, 사주는 참고 한 줄.

사주 composite는 4축(재물/결단/충돌/합) 가중합으로 별도 계산됨. 여기선 블랙박스로 취급.

---

## 9. 등급 판정 (`_grade_signal`, Week 10 Phase 2)

```
def _grade_signal(score, analysis):
    state = analysis.structure.state

    # 1. 강진입: 3조건 AND
    if score >= 75 AND analysis.alignment.aligned AND state in (UPTREND, BREAKOUT):
        return "강진입"

    # 2. Week 10 Phase 2 게이팅: 하락/이탈 구조에서 진입 차단
    if state in (DOWNTREND, BREAKDOWN):
        if score >= 60:
            return "관망"    # 60+ 여도 관망으로 강등

    # 3. 기본 임계값
    if score >= 60: return "진입"
    if score >= 40: return "관망"
    return "회피"
```

### 규칙 표

| final_score | structure | alignment.aligned | 결과 |
|-------------|-----------|-------------------|------|
| ≥75 | UPTREND/BREAKOUT | True | **강진입** |
| ≥75 | 그 외 또는 aligned=False | - | 진입 |
| ≥60 | DOWNTREND / BREAKDOWN | - | **관망 (강등)** |
| ≥60 | 그 외 | - | 진입 |
| 40-59 | 무관 | - | 관망 |
| <40 | 무관 | - | 회피 |

**핵심:** 구조가 뒷받침하지 않으면 점수 높아도 매수 신호 안 나옴.

---

## 10. S/R 식별 (`analysis/support_resistance.py`)

현재가 기준 위/아래 각 최대 3개 레벨 반환. Swing + Volume Profile 융합.

### 단계

1. **후보 수집:**

- Swing high → `SRLevel(price=sp.price, kind=RESISTANCE, strength="low", sources=["swing_high"])`
- Swing low → SUPPORT 후보
- Volume Profile 상위 5개 노드 (매물대). node 중간값(`(price_low + price_high)/2`)이 현재가 위면 RESISTANCE, 아래면 SUPPORT. 최대 volume node는 `strength="medium"`, 나머지는 `"low"`, source=["volume_node"].

2. **Volume Profile 계산 (`volume_profile.py`):**

- 가격 범위 `[min(low), max(high)]`를 20 bucket 등분.
- 각 봉의 `(high+low)/2`가 속한 bucket에 volume 전량 더함.
- volume_sum 내림차순 상위 5개.

3. **병합:** 같은 kind(Support/Resistance) 내에서 가격차 `≤ 0.5%` 인접 후보들을 클러스터 → 단순 평균 가격, sources 합집합, strength는 max (high>medium>low).

4. **Strength 재판정:** 클러스터 sources에 `swing_*` AND `volume_node` 둘 다 있으면 → `"high"`.

5. **필터 + 정렬:**

- Support: `price < current`, 현재가로부터 가까운 순, 최대 3개.
- Resistance: `price > current`, 가까운 순, 최대 3개.

---

## 11. Trade Setup (`analysis/trade_setup.py`) — 진입/강진입 등급에만

ATR 기본 + S/R snap 하이브리드.

```
_SL_ATR_MULT       = 1.5
_TP1_ATR_MULT      = 1.5
_TP2_ATR_MULT      = 3.0
_SNAP_TOLERANCE    = 0.3    # SL/TP1 snap 허용 범위 (ATR 배수의 ±30%)
_SNAP_TOLERANCE_TP2= 0.5    # TP2는 ±50%
_SR_BUFFER_ATR     = 0.2    # S/R 레벨 뚫고 0.2 ATR 여유
```

### SL 산출

1. `sl_base = entry - 1.5 × ATR`.
2. Search range: `[entry - 1.8×ATR, entry - 1.2×ATR]`.
3. 이 범위 안에 있는 SUPPORT 레벨 중 strength 최고 선택.

- 발견 → `SL = support.price - 0.2×ATR`, `sl_basis = "sr_snap"`.
- 없음 → `SL = sl_base`, `sl_basis = "atr"`.

### TP1 산출 (대칭)

- Range `[entry + 1.2×ATR, entry + 1.8×ATR]`.
- 해당 범위 RESISTANCE 있으면 → `TP1 = resistance.price - 0.2×ATR` (저항 약간 앞에서 보수적 익절).

### TP2 산출 (더 넓은 tolerance)

- `tp2_base = entry + 3.0 × ATR`.
- Range `[entry + 2.5×ATR, entry + 3.5×ATR]` (±50%).
- 동일 규칙.

### 파생 값

```
risk_pct = (entry - SL) / entry × 100
rr_tp1   = (TP1 - entry) / (entry - SL)
rr_tp2   = (TP2 - entry) / (entry - SL)
```

**반환:** `TradeSetup(entry, stop_loss, take_profit_1, take_profit_2, risk_pct, rr_tp1, rr_tp2, sl_basis, tp1_basis, tp2_basis)`.

### Degenerate case

`atr_1d ≤ 0`이면 `atr_1d = entry × 0.01` (1% fallback). SL/TP 가 degenerate 한 값으로라도 계산됨.

---

## 12. 카드 출력 (`handlers.py`)

### 진입/강진입 (세팅 블록 포함)

```
── {date} {ticker} ──
🟢 장 중 / 🕐 휴장 중 · 기준: ... (us_stock만)
현재가: ${current:,.2f} ({change_sign}{change_pct}%)

구조: {structure label (상승추세 HH-HL / 하락추세 LH-LL / 횡보 박스 / 상승 돌파 / 하락 이탈)}
정렬: 1d{arrow} 4h{arrow} 1h{arrow}  ({강정렬|혼조|부분정렬})
진입조건: RSI(1h) {rsi:.0f} · 거래량 {vol_ratio:.1f}x

세팅:
 진입 ${entry:,.2f}
 손절 ${sl:,.2f} ({sl_pct:+.1f}%)
 익절1 ${tp1:,.2f} ({tp1_pct:+.1f}%)  익절2 ${tp2:,.2f} ({tp2_pct:+.1f}%)
 R:R {rr1:.1f} / {rr2:.1f}   리스크 {risk_pct:.1f}%

종합: {final_score:>3} | {grade}
사주: {saju_composite:>3} ({saju_grade})

※ 정보 제공 목적. 투자 판단과 손실 책임은 본인에게 있습니다.
```

### 관망/회피 (주요 레벨 블록)

```
... (위와 동일 구조까지)

주요 레벨:
 저항 ${r1:,.2f} · ${r2:,.2f} · ${r3:,.2f}
 지지 ${s1:,.2f} · ${s2:,.2f} · ${s3:,.2f}

종합: ... | ...
```

---

## 13. 캐시 전략

- **OHLCV Redis 2-tier**: `ohlcv:{symbol}:{interval}:{fresh|backup}`. Provider별 비대칭:
  - **Binance**: Fresh TTL **5분** (24/7 시장 실시간성), Backup TTL 24h
  - **yfinance**: Fresh TTL **1h** (장외 시간 변동 작음), Backup TTL 24h
  - 프로바이더 실패 시 backup fallback.
- **Signal composite Redis**: `signal:{chat_id}:{date}:{ticker}`, TTL 300초 (5분). 같은 사용자가 5분 내 재조회 시 캐시 hit.
- **사주 composite Redis**: `score:{chat_id}:{date}:{asset}`, TTL은 KST 자정까지 (최소 60초).

---

## 14. 제외/주의 사항

- **공휴일**: 미국 장 공휴일(1년 ~9일) 커버하지 않음. `is_market_open`이 True로 잘못 뜰 수 있으나 `last_session_date`는 yfinance가 휴장일 데이터를 안 주므로 정확.
- **사주 점수 로직**: 이 문서 범위 밖 (블랙박스). 기본적으로 일진 4축(재물/결단/충돌/합) 가중합.
- **튜닝 상수**: `_SL_ATR_MULT`, `_SNAP_TOLERANCE`, volume profile bucket_count 등은 **백테스트 이전의 initial value**. 실데이터(MFE/MAE 누적) 이후 조정 예정.
- **구조 판정 엄격도**: 3개 연속 HH-HL을 요구하므로 swing이 부족한 초반/횡보 구간엔 RANGE로 가는 경우 많음. 그래서 `composite.py`에 폴백 보정 (swings=[]일 때 alignment 50% 섞음).

---

## 15. 지원 자산

**Crypto (Binance):** BTCUSDT, ETHUSDT, XRPUSDT.

**US Stock (yfinance):** AAPL, MSFT, GOOGL, NVDA, TSLA, AMD, META, AMZN.

그 외 티커는 `UnsupportedTicker` 예외.

화이트리스트: `src/sajucandle/market/router.py`의 `_CRYPTO_SYMBOLS`, `_STOCK_SYMBOLS` frozenset.

---

이 명세로 다른 AI가 동일 로직 재현 가능. 구현 원본은 `src/sajucandle/analysis/` 패키지 5개 파일 + `signal_service.py` + `tech_analysis.py` 조합.
"""


def main():
    out_path = Path(r"D:\사주캔들\docs\sajucandle-chart-analysis-spec.pdf")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    doc = SimpleDocTemplate(
        str(out_path),
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title="SajuCandle 차트 분석 명세",
        author="SajuCandle",
    )
    story = md_to_story(SPEC_MD)
    doc.build(story)
    print(f"WROTE {out_path}  ({out_path.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
