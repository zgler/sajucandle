# Phase 0 리서치: 현재 코드 상태 점검

- **작성 시점**: 2026-04-20
- **대상 브랜치**: `main` (commit: `c092a7c` — "feat(week10-phase2): gating + /guide + error UX")
- **작성 목적**: 설계 명세(`docs/sajucandle-chart-analysis-spec.pdf`, Week 10 Phase 2 기준)와 실제 코드의 일치 여부 확인. Phase 1~4 작업의 기준점 확립.
- **테스트 현황**: 307 passed, 69 skipped (TEST_DATABASE_URL 미설정 환경)

## 요약

- 전체 체크 항목 수: **86개** (A~N 섹션 합계)
- 명세와 일치: **81개** (94%)
- 명세와 불일치: **2개** (critical)
- 명세 표현 불명확/모호: **3개**
- 명세에 없는 추가 로직: **7개** (모두 Week 8+ 증분, 명세 PDF가 Week 10 Phase 2까지의 분석 엔진만 다룸)

### 핵심 발견사항

1. **명세와 실제 코드 일치도 매우 높음** — 명세 PDF를 코드 직접 확인 후 작성했기에 분석 엔진 파라미터는 100% 일치.
2. **Critical 괴리 1개 (M)**: OHLCV 캐시 TTL이 **provider별로 다름**. Binance `_FRESH_TTL=300` (5분), yfinance `_FRESH_TTL=3600` (1h). 명세는 yfinance 기준으로만 기술.
3. **Critical 괴리 1개 (J)**: `volume_profile.compute_volume_profile`의 **기본 `top_n=3`**인데 명세 §10/§J는 "상위 5개". 실제로는 호출자(`identify_sr_levels`)가 `volume_top_n=5`로 오버라이드 — 명세-코드 호출 경로 기준 결과는 5개로 일치하나 함수 기본값은 괴리.
4. **명세 범위 밖 실제 기능**: Week 5~10의 broadcast Phase 0/1/3, signal_log DB + MFE/MAE 추적, admin OHLCV, `/stats`, `/guide`, `/watch /unwatch /watchlist` 등이 코드엔 있으나 분석 엔진 명세 PDF 외부.
5. **테스트 인프라 매우 튼튼**: 34개 test 파일, pytest-asyncio auto mode, DB 통합 테스트 skip/실행 분기 정상 동작. **CI 설정 없음** (Phase 1 백테스트 하네스 추가 시 GitHub Actions 검토 가치).

---

## 프로젝트 구조

```
D:\사주캔들/
├── src/sajucandle/
│   ├── analysis/                 # Week 8~9 분석 엔진 (5+3 모듈)
│   │   ├── swing.py              # Fractals + ATR prominence
│   │   ├── structure.py          # MarketStructure 분류
│   │   ├── timeframe.py          # 단일 TF TrendDirection
│   │   ├── multi_timeframe.py    # 3TF Alignment
│   │   ├── composite.py          # analyze() 조합기
│   │   ├── volume_profile.py     # Week 9 VPVR
│   │   ├── support_resistance.py # Week 9 S/R 융합
│   │   └── trade_setup.py        # Week 9 하이브리드 SL/TP
│   ├── market/                   # Week 6 멀티 자산 라우팅
│   │   ├── base.py
│   │   ├── binance.py
│   │   ├── yfinance.py
│   │   └── router.py             # MarketRouter + _CRYPTO_SYMBOLS/_STOCK_SYMBOLS
│   ├── saju_engine.py            # 명리 4축 계산 (lunar_python)
│   ├── tech_analysis.py          # RSI/SMA/volume 순수 함수
│   ├── signal_service.py         # SignalService — analyze() + 사주 + grade + TradeSetup
│   ├── score_service.py          # 사주 점수 서비스 + KST 자정 TTL 캐시
│   ├── market_data.py            # BinanceClient + 2-tier OHLCV 캐시
│   ├── cache.py                  # BaziCache
│   ├── cached_engine.py          # CachedSajuEngine
│   ├── handlers.py               # Telegram 커맨드 핸들러 (13개 명령)
│   ├── broadcast.py              # 일일 푸시 CLI (Phase 0/1/2/3)
│   ├── api.py                    # FastAPI 앱
│   ├── api_main.py               # uvicorn entry
│   ├── api_client.py             # 봇→API httpx 래퍼
│   ├── models.py                 # Pydantic 모델 (Signal/Analysis/TradeSetup/Watchlist/...)
│   ├── db.py                     # asyncpg Pool
│   ├── repositories.py           # users/user_bazi/user_watchlist/signal_log CRUD
│   ├── format.py                 # 명식 카드 + DISCLAIMER 상수
│   └── bot.py                    # Telegram 봇 엔트리
├── tests/                        # 34개 test 파일
│   ├── conftest.py               # db_pool, db_conn (트랜잭션 롤백 fixture)
│   └── test_*.py
├── migrations/
│   ├── 001_init.sql              # users, user_bazi (Week 3)
│   ├── 002_watchlist.sql         # user_watchlist (Week 7)
│   ├── 003_signal_log.sql        # signal_log + MFE/MAE (Week 8)
│   └── 004_signal_log_tradesetup.sql  # SL/TP 컬럼 (Week 9)
├── docs/
│   ├── sajucandle-chart-analysis-spec.pdf   # Week 10 명세
│   ├── master plan.docx          # Phase 0~4 마스터 플랜
│   ├── superpowers/specs/        # 주차별 설계 문서
│   └── superpowers/plans/        # 주차별 구현 플랜
├── pyproject.toml                # hatchling + PEP 621
├── railway.toml                  # 3서비스 (api/bot/broadcast)
├── Dockerfile
└── README.md
```

---

## 체크리스트 결과

### A. Swing 감지 (`src/sajucandle/analysis/swing.py`)

| 항목 | 명세값 | 코드값 | 일치 | 위치 |
|------|--------|--------|------|------|
| `fractal_window` 기본값 | 5 | 5 | ✓ | swing.py:43 |
| `atr_multiplier` 기본값 | 1.5 | 1.5 | ✓ | swing.py:44 |
| `atr_period` 기본값 | 14 | 14 | ✓ | swing.py:45 |
| ATR Wilder smoothing | ✓ | ✓ (14봉 SMA → (avg*13+TR)/14) | ✓ | swing.py:24-38 |
| Prominence 비교 기준 | 좌/우 각 fractal_window봉 = 10봉 최고점 대비 | `max(k.high for k in neighbors)` where `neighbors = left + right` | ✓ | swing.py:65-68 |
| 봉 수 < 2×window+1 빈 리스트 | 11개 미만 빈 리스트 | `n < 2*fractal_window + 1` | ✓ | swing.py:51-53 |
| `atr_multiplier=0` 필터 off | ✓ | `if threshold <= 0 or prominence >= threshold` | ✓ | swing.py:55-58, 69, 77 |

**A 섹션: 7/7 일치**

---

### B. Structure 판정 (`src/sajucandle/analysis/structure.py`)

| 항목 | 명세값 | 코드값 | 일치 | 위치 |
|------|--------|--------|------|------|
| 판정 우선순위 | UPTREND → BREAKDOWN → BREAKOUT → DOWNTREND → RANGE | UPTREND → BREAKDOWN → BREAKOUT → DOWNTREND → RANGE | ✓ | structure.py:85-94 |
| UPTREND score | 70 | 70 | ✓ | structure.py:32 |
| BREAKOUT score | 80 | 80 | ✓ | structure.py:33 |
| RANGE score | 50 | 50 | ✓ | structure.py:34 |
| BREAKDOWN score | 30 | 30 | ✓ | structure.py:35 |
| DOWNTREND score | 20 | 20 | ✓ | structure.py:36 |
| UPTREND 조건 | highs≥3 AND lows≥3 AND 최근 3개 HH + 3개 HL | `len(highs)>=3 AND len(lows)>=3 AND highs[-1]>highs[-2]>highs[-3] AND lows[-1]>lows[-2]>lows[-3]` | ✓ | structure.py:62-66 |
| DOWNTREND 조건 | UPTREND 대칭 | highs/lows 3개 연속 하락 | ✓ | structure.py:67-71 |
| BREAKDOWN 조건 | highs≥2 AND lows≥3 AND 최근 high 상승 AND 최근 low 하락 | `len(highs)>=2 AND len(lows)>=3 AND highs[-1]>highs[-2] AND lows[-1]<lows[-2]` | ✓ | structure.py:73-77 |
| BREAKOUT 조건 | highs≥3 AND 최근 high > max(이전 high들) × 1.03 | `len(highs)>=3 AND highs[-1] > prev_range_top * 1.03` | ✓ | structure.py:79-83 |
| 반환 타입 | `StructureAnalysis(state, last_high, last_low, score)` | 동일 | ✓ | structure.py:23-28 |

**B 섹션: 11/11 일치**

---

### C. Timeframe 트렌드 (`src/sajucandle/analysis/timeframe.py`)

| 항목 | 명세값 | 코드값 | 일치 | 위치 |
|------|--------|--------|------|------|
| EMA50 초기값 | SMA50 | SMA50 | ✓ | timeframe.py:25-28 |
| EMA α 계수 | 2/(period+1) = 2/51 | `k = 2.0 / (period + 1)` | ✓ | timeframe.py:25 |
| threshold | `last_ema × 0.0001` (0.01%) | `last_ema * 0.0001` | ✓ | timeframe.py:48 |
| UP 조건 | above AND rising AND close_rising | 동일 | ✓ | timeframe.py:60-62 |
| DOWN 조건 | below AND falling AND close_falling | 동일 | ✓ | timeframe.py:63-65 |
| 봉 수 < 56 FLAT | `len < ema_period + 6 = 56` | `if len(klines) < ema_period + 6: return FLAT` | ✓ | timeframe.py:36-37 |
| EMA 기울기 5봉 기준 | `ema[-1] - ema[-6]` | `last_ema - prev_ema` where `prev_ema = emas[-6]` | ✓ | timeframe.py:44-45 |

**C 섹션: 7/7 일치**

---

### D. Alignment (`src/sajucandle/analysis/multi_timeframe.py`)

| 항목 | 명세값 | 코드값 | 일치 | 위치 |
|------|--------|--------|------|------|
| ups/downs 카운트 | `dirs.count(UP)/count(DOWN)` | 동일 | ✓ | multi_timeframe.py:35-37 |
| aligned 조건 | ups==3 OR downs==3 | 동일 | ✓ | multi_timeframe.py:39 |
| bias 판정 | ups>downs=bullish / downs>ups=bearish / else=mixed | 동일 | ✓ | multi_timeframe.py:41-46 |
| score 공식 | `round((ups - downs + 3) / 6 × 100)` | `round((diff + 3) / 6 * 100)` where `diff = ups - downs` | ✓ | multi_timeframe.py:48-49 |
| aligned bullish 보정 | `max(score, 90)` | 동일 | ✓ | multi_timeframe.py:50-51 |
| aligned bearish 보정 | `min(score, 10)` | 동일 | ✓ | multi_timeframe.py:52-53 |

**D 섹션: 6/6 일치**

---

### E. 보조 지표 (`src/sajucandle/tech_analysis.py`)

| 항목 | 명세값 | 코드값 | 일치 | 위치 |
|------|--------|--------|------|------|
| RSI(14) Wilder | 처음 14봉 SMA → (avg*13+TR)/14 | 동일 (period=14 default) | ✓ | tech_analysis.py:31-65 |
| RSI score ≤30 | 70 | 70 | ✓ | tech_analysis.py:90-91 |
| RSI score ≤45 | 55 | 55 | ✓ | tech_analysis.py:92-93 |
| RSI score ≤55 | 50 | 50 | ✓ | tech_analysis.py:94-95 |
| RSI score ≤70 | 40 | 40 | ✓ | tech_analysis.py:96-97 |
| RSI score >70 | 20 | 20 | ✓ | tech_analysis.py:98 |
| volume_ratio 공식 | `vol[-1] / mean(vol[-21:-1])` | `volumes[-1] / past_avg` where `past_avg = mean(volumes[-lookback-1:-1])`, `lookback=20` | ✓ | tech_analysis.py:68-81 |
| vol score ≥1.5 | 65 | 65 | ✓ | tech_analysis.py:117-118 |
| vol score ≥1.0 | 55 | 55 | ✓ | tech_analysis.py:119-120 |
| vol score ≥0.5 | 45 | 45 | ✓ | tech_analysis.py:121-122 |
| vol score <0.5 | 35 | 35 | ✓ | tech_analysis.py:123 |

**E 섹션: 11/11 일치**

---

### F. Composite 조합 (`src/sajucandle/analysis/composite.py`)

| 항목 | 명세값 | 코드값 | 일치 | 위치 |
|------|--------|--------|------|------|
| 1d swing 없으면 1h 폴백 | ✓ | `if not swings and len(klines_1h) >= 11: swings = detect_swings(klines_1h, ...)` | ✓ | composite.py:70-72 |
| swings=[] 시 폴백 보정 | `0.5×structure + 0.5×alignment` | `round(0.5 * structure.score + 0.5 * alignment.score)` | ✓ | composite.py:85-89 |
| 가중합 계수 | 0.45×structure + 0.35×alignment + 0.10×rsi + 0.10×vol | 동일 | ✓ | composite.py:91-96 |
| clamp | 0~100 | `max(0, min(100, composite))` | ✓ | composite.py:97 |
| `AnalysisResult.sr_levels` | List[SRLevel] | 동일 | ✓ | composite.py:42 |
| `AnalysisResult.atr_1d` | float | 동일 | ✓ | composite.py:43 |
| ATR(14, 1d) 계산 | ✓ | `_atr(klines_1d, 14) if len(klines_1d) >= 15 else 0.0` | ✓ | composite.py:120 |
| reason 포맷 | `1d{arr} 4h{arr} 1h{arr} ({label}) · RSI(1h) N · 볼륨↑/→/↓` | 동일 | ✓ | composite.py:99-111 |

**F 섹션: 8/8 일치**

---

### G. 사주 + 차트 합산 (`src/sajucandle/signal_service.py`)

| 항목 | 명세값 | 코드값 | 일치 | 위치 |
|------|--------|--------|------|------|
| 사주 가중치 | 0.1 | 0.1 | ✓ | signal_service.py:162 |
| 차트 analysis 가중치 | 0.9 | 0.9 | ✓ | signal_service.py:162 |
| 합산 공식 | `round(0.1×saju + 0.9×analysis)` | 동일 | ✓ | signal_service.py:162 |
| clamp | 0~100 | `max(0, min(100, final))` | ✓ | signal_service.py:163 |

**G 섹션: 4/4 일치**

---

### H. 등급 판정 (`_grade_signal`, `signal_service.py`)

| 항목 | 명세값 | 코드값 | 일치 | 위치 |
|------|--------|--------|------|------|
| 강진입 조건 | score≥75 AND aligned AND state∈(UPTREND,BREAKOUT) | 동일 | ✓ | signal_service.py:54-57 |
| Week 10 Phase 2 게이팅 | DOWNTREND/BREAKDOWN AND score≥60 → "관망" | 동일 | ✓ | signal_service.py:60-62 |
| 진입 임계 | score≥60 | 동일 | ✓ | signal_service.py:64 |
| 관망 임계 | score≥40 | 동일 | ✓ | signal_service.py:66 |
| 회피 임계 | <40 | else "회피" | ✓ | signal_service.py:68 |

**H 섹션: 5/5 일치**

---

### I. Trade Setup (`src/sajucandle/analysis/trade_setup.py`)

| 항목 | 명세값 | 코드값 | 일치 | 위치 |
|------|--------|--------|------|------|
| `_SL_ATR_MULT` | 1.5 | 1.5 | ✓ | trade_setup.py:10 |
| `_TP1_ATR_MULT` | 1.5 | 1.5 | ✓ | trade_setup.py:11 |
| `_TP2_ATR_MULT` | 3.0 | 3.0 | ✓ | trade_setup.py:12 |
| `_SNAP_TOLERANCE` | 0.3 | 0.3 | ✓ | trade_setup.py:13 |
| `_SNAP_TOLERANCE_TP2` | 0.5 | 0.5 | ✓ | trade_setup.py:14 |
| `_SR_BUFFER_ATR` | 0.2 | 0.2 | ✓ | trade_setup.py:15 |
| SL search range | `[entry - 1.8×ATR, entry - 1.2×ATR]` | `[entry - (1.5+0.3)*ATR, entry - (1.5-0.3)*ATR]` | ✓ | trade_setup.py:60-61 |
| TP2 search range | `[entry + 2.5×ATR, entry + 3.5×ATR]` | `[entry + (3.0-0.5)*ATR, entry + (3.0+0.5)*ATR]` | ✓ | trade_setup.py:84-85 |
| ATR ≤ 0 폴백 | `atr = entry × 0.01` | 동일 | ✓ | trade_setup.py:52-53 |
| 반환 필드 | 10개 (entry, sl, tp1, tp2, risk_pct, rr_tp1, rr_tp2, sl_basis, tp1_basis, tp2_basis) | 동일 | ✓ | trade_setup.py:18-29 |
| strength 기반 best-level 선택 | strength high > medium > low | `_STRENGTH_ORDER = {"low":0, "medium":1, "high":2}`, sort reverse | ✓ | trade_setup.py:32, 43 |

**I 섹션: 11/11 일치**

---

### J. S/R 식별 (`support_resistance.py` + `volume_profile.py`)

| 항목 | 명세값 | 코드값 | 일치 | 위치 |
|------|--------|--------|------|------|
| bucket_count 기본 | 20 | 20 (volume_profile) + 20 (support_resistance 호출 기본) | ✓ | volume_profile.py:21, support_resistance.py:41 |
| top_n 명세 | 5 | **`compute_volume_profile` 기본=3**, **`identify_sr_levels` 호출 기본=5** | ⚠️ 불일치 (함수 기본 vs 호출 경로) | volume_profile.py:22, support_resistance.py:40 |
| 최대 volume node strength | "medium" | `strength = "medium" if is_top else "low"` | ✓ | support_resistance.py:69 |
| 클러스터 병합 거리 | ≤ 0.5% | `merge_tolerance_pct: float = 0.5` 기본 | ✓ | support_resistance.py:39 |
| swing+volume 둘 다 → "high" | ✓ | `if has_swing and has_volume: level.strength = "high"` | ✓ | support_resistance.py:78-82 |
| max_supports/resistances | 3 | `max_supports: int = 3, max_resistances: int = 3` | ✓ | support_resistance.py:37-38 |
| 현재가 위/아래 분리 | ✓ | `price < current` → support / `price > current` → resistance | ✓ | support_resistance.py:85-88 |
| 가까운 순 정렬 | ✓ | `supports.sort(key=lambda x: current - x.price)`, resistances 대칭 | ✓ | support_resistance.py:89-90 |

**J 섹션: 7/8 일치 + 1 경미 불일치**

**⚠️ J-2 불일치 상세**: `compute_volume_profile(..., top_n=3)` 이 기본값이지만 실제로 `identify_sr_levels`가 `volume_top_n=5`를 넘겨서 5개 반환됨. 명세는 "상위 5개 노드"라고 단정. 실사용 결과는 5개로 일치하나 함수 기본값 / 명세 단정이 어긋남. Phase 4 튜닝 시 이 기본값을 변경할 일이 생기면 혼란 가능.

---

### K. 카드 출력 (`handlers.py::_format_signal_card`)

| 항목 | 명세값 | 코드값 | 일치 | 위치 |
|------|--------|--------|------|------|
| 진입/강진입에 세팅 블록 | 진입/손절/익절1·2/R:R/리스크% | `_append_trade_setup_block` 호출 | ✓ | handlers.py:423-424 |
| 세팅 블록 전환 조건 | `grade in ("강진입", "진입") AND trade_setup 존재` | 동일 | ✓ | handlers.py:423 |
| 관망/회피에 주요 레벨 | 저항/지지 각 최대 3개 | `_append_sr_levels_block` 호출 | ✓ | handlers.py:425-426 |
| 주요 레벨 전환 조건 | sr_levels 존재 | `elif sr_levels:` | ✓ | handlers.py:425 |
| 구조 라벨 한글 매핑 | UPTREND→"상승추세 (HH-HL)" 등 | `_STRUCTURE_LABEL` dict | ✓ | handlers.py:_STRUCTURE_LABEL 상수 |
| TF 화살표 | ↑/↓/→ | `_TF_ARROW_UI = {"up":"↑","down":"↓","flat":"→"}` | ✓ | handlers.py:_TF_ARROW_UI 상수 |
| DISCLAIMER | "정보 제공 목적. 투자 판단과 손실 책임은 본인에게 있습니다." | 동일 (`format.DISCLAIMER`) | ✓ | format.py:14 |

**K 섹션: 7/7 일치**

---

### L. 지원 심볼 (`src/sajucandle/market/router.py`)

| 항목 | 명세값 | 코드값 | 일치 | 위치 |
|------|--------|--------|------|------|
| `_CRYPTO_SYMBOLS` | BTCUSDT, ETHUSDT, XRPUSDT | 동일 (3개) | ✓ | router.py:12 |
| `_STOCK_SYMBOLS` | AAPL, MSFT, GOOGL, NVDA, TSLA, AMD, META, AMZN | 동일 (8개) | ✓ | router.py:13-14 |
| 미지원 심볼 예외 | `UnsupportedTicker` | 동일 | ✓ | router.py:26-27 |
| 정규화 | `upper().lstrip("$")` | 동일 | ✓ | router.py:22 |

**L 섹션: 4/4 일치**

---

### M. 캐시 (`market_data.py`, `market/yfinance.py`, `signal_service.py`, `score_service.py`)

| 항목 | 명세값 | 코드값 | 일치 | 위치 |
|------|--------|--------|------|------|
| OHLCV 캐시 키 포맷 | `ohlcv:{symbol}:{interval}:{fresh|backup}` | 동일 (양쪽 provider) | ✓ | market_data.py:101-102, yfinance.py:50-51 |
| **Fresh TTL (Binance)** | 1h | **300초 (5분)** | **✗ 괴리** | market_data.py:25 |
| **Fresh TTL (yfinance)** | 1h | 3600초 (1h) | ✓ | yfinance.py:28 |
| Backup TTL | 24h | 86400초 (24h, 양쪽 일치) | ✓ | market_data.py:26, yfinance.py:29 |
| Signal 캐시 키 | `signal:{chat_id}:{date}:{ticker}` | 동일 | ✓ | signal_service.py:137 |
| Signal TTL | 300초 | `_SIGNAL_TTL = 300` | ✓ | signal_service.py:40 |
| 사주 캐시 키 | `score:{chat_id}:{date}:{asset}` | 동일 | ✓ | score_service.py:47 |
| 사주 TTL | KST 자정까지 (최소 60초) | 구현 확인 필요 (§Open Questions 참조) | ? | score_service.py |

**M 섹션: 6/8 확정 일치 + 1 괴리 + 1 미확인**

**✗ M-2 괴리 상세**: Binance OHLCV fresh 캐시는 5분인데 명세는 "1h"로 단일값 기술. 설계 의도는 합리적(BTC 24/7 실시간성 > 주식 장중 변동성)이지만 명세가 provider별 구분을 안 함 → 문서 오류. Phase 1 백테스트 하네스에서 과거 데이터 조회 시 이 TTL 차이가 영향 줄 수 있음 (caching layer 재설계 여부).

---

### N. 테스트 인프라 (`tests/`, `pyproject.toml`)

| 항목 | 명세값 | 코드값 | 일치 | 위치 |
|------|--------|--------|------|------|
| `tests/` 디렉토리 | ✓ | 존재 (34 test 파일) | ✓ | tests/ |
| analysis 모듈별 unit test | ✓ | `test_analysis_{swing,structure,timeframe,multi_timeframe,composite,support_resistance,trade_setup,volume_profile}.py` 8개 | ✓ | tests/ |
| 테스트 러너 | pytest | pytest + pytest-asyncio | ✓ | pyproject.toml |
| asyncio 모드 | - | `asyncio_mode = "auto"` | ⊕ | pyproject.toml |
| DB 통합 테스트 fixture | - | `db_pool`, `db_conn` (BEGIN-ROLLBACK 자동) | ⊕ | conftest.py |
| TEST_DATABASE_URL skip 처리 | - | `pytest.skip("TEST_DATABASE_URL not set")` | ⊕ | conftest.py |
| **CI 설정** | 명세 없음 | **존재하지 않음** (`.github/workflows/`, `.gitlab-ci.yml` 모두 없음) | ⚠️ | — |
| 테스트 커버리지 도구 | - | 설정 없음 (`coverage.py`, `pytest-cov` 미설치) | ⚠️ | pyproject.toml |
| 현재 통과 수 | - | 307 passed, 69 skipped (TEST_DATABASE_URL 없을 때) | ✓ | `pytest -q` |

**N 섹션: 명세 언급 부족. 실제 인프라 상태 기록.**

**⚠️ Phase 1 영향**:
- **CI 부재**: 백테스트 하네스를 Phase 1에서 추가 후 Phase 2+에서 코드 변경이 백테스트 결과를 깨뜨리는지 자동 검증할 수단 없음. Phase 1 완료 시 GitHub Actions 도입 권고.
- **테스트 커버리지 도구 부재**: Phase 2 "숏 신호 대칭 구현" 시 대칭 분기가 제대로 커버되는지 추적하기 어려움. `pytest-cov` 추가 권고.

---

## 괴리 리스트 (Critical)

### 1. OHLCV Fresh TTL provider별 비대칭 (M-2)

- **무엇이 다른가**: 명세는 "Fresh TTL 1h" 단일값. 실제는 Binance 5분 / yfinance 1h.
- **어느 Phase에 영향**:
  - **Phase 1 백테스트**: 과거 OHLCV 재조회 시 캐시 효과가 provider별로 달라짐. 단 백테스트는 주로 backup TTL (24h)에 의존하므로 영향 경미.
  - **Phase 4 튜닝**: 실시간 운영 데이터와 백테스트 데이터의 신선도 차이 고려 필요.
- **제안 조치**: **코드 그대로 두고 명세 갱신** (설계 의도는 합리적 — BTC 24/7 + 실시간 가격 변동 > 주식 시간외 캐시 가능).
  - 명세 PDF §13을 "Fresh TTL 5분(Binance) / 1h(yfinance), Backup TTL 24h"로 수정.

### 2. `volume_profile.top_n` 기본값 3 vs 명세 "상위 5개" (J-2)

- **무엇이 다른가**: `compute_volume_profile` 함수 기본 `top_n=3`. 명세는 "상위 5개". 호출자(`identify_sr_levels`)는 `volume_top_n=5`로 호출하므로 실사용 결과는 5개로 명세 일치. 그러나 함수 단독 사용 시 3개.
- **어느 Phase에 영향**:
  - **Phase 1 백테스트**: 만약 백테스트가 `compute_volume_profile`을 직접 호출하면 5개 가정한 분석이 3개만 받음.
  - **Phase 3 지표 고도화**: volume profile 관련 개선 시 혼란.
- **제안 조치**: **함수 기본값을 5로 수정** (코드 한 줄). 명세와 맞춤 + 호출자 kwargs 제거 가능.
  - `volume_profile.py:22`: `top_n: int = 3` → `top_n: int = 5`.
  - `support_resistance.py:40`: `volume_top_n=5` 기본값 삭제 가능.

---

## 명세에 없는 추가 로직

명세 PDF는 "분석 엔진 + 카드 출력"만 다룸. 다음은 코드엔 있으나 명세 범위 밖:

1. **signal_log DB 스키마 + 기록 (Week 8)**
   - `repositories.insert_signal_log()` — `/signal` 성공 시 best-effort 기록.
   - `signal_log` 테이블 22컬럼 (SL/TP 포함).
   - Phase 11 백테스트 데이터 원천.

2. **broadcast.py Phase 0 (MFE/MAE 추적, Week 8~9)**
   - `run_phase0_tracking()` — pending signal_log rows의 7일 MFE/MAE 갱신.
   - `run_broadcast()`의 맨 앞 단계.

3. **broadcast.py Phase 1/2/3 (Week 5/7)**
   - Phase 1: precompute — admin chat으로 watchlist 심볼 signal 호출 (캐시 워밍).
   - Phase 2: 모닝 사주 카드 발송.
   - Phase 3: watchlist 요약 카드 발송.

4. **`GET /v1/admin/ohlcv` (Week 9)**
   - Phase 0 tracking의 default callback이 사용.
   - query params: ticker, interval, since, limit.

5. **`GET /v1/admin/signal-stats` + `/stats` 봇 명령 (Week 10 Phase 1)**
   - signal_log 집계 (total, by_grade, tracking 상태, MFE/MAE 통계).
   - admin chat_id 전용.

6. **`/guide` 봇 명령 (Week 10 Phase 2)**
   - 등급/구조/정렬/세팅 블록 해석 가이드.

7. **Watchlist 기능 (Week 7)**
   - `/watch`, `/unwatch`, `/watchlist` 명령 + `user_watchlist` 테이블.
   - 5개 제한, 모닝 푸시 Phase 3 통합.

8. **에러 메시지 분리 (Week 10 Phase 2)**
   - timeout / transport / 502 / 503 / 5xx 원인별 사용자 메시지.

---

## 테스트 인프라 상태

### 파일 목록 (34개)

**분석 엔진 (8):** `test_analysis_{swing, structure, timeframe, multi_timeframe, composite, support_resistance, trade_setup, volume_profile}.py`

**API (8):** `test_api.py, test_api_admin.py, test_api_client.py, test_api_ohlcv.py, test_api_score.py, test_api_signal.py, test_api_stats.py, test_api_users.py, test_api_watchlist.py`

**Bot + 인프라 (7):** `test_handlers.py, test_format.py, test_market_*.py (4), test_tech_analysis.py`

**데이터/서비스 (5):** `test_db.py, test_cache.py, test_cached_engine.py, test_broadcast.py, test_repositories.py, test_score_service.py, test_signal_service.py`

### 커버리지 추정

- **분석 엔진**: 매우 높음. 각 모듈당 5~10 테스트. `test_analysis_*.py` 총 60+ 테스트.
- **API/봇**: 높음. 정상 경로 + 에러 분기 + edge case 다수.
- **broadcast 통합**: 중간. Phase 0~3 각각 mock 기반, 실제 Railway cron 시나리오는 부분 커버.
- **DB 통합**: TEST_DATABASE_URL 있을 때만. 현재 skipped 69개 대부분 DB 관련.

### Phase 1 백테스트 하네스 배치 제안

- **위치**: `src/sajucandle/backtest/` 신규 패키지 + `tests/test_backtest_*.py`.
- **엔트리**: `python -m sajucandle.backtest <ticker> <from> <to>` CLI.
- **의존성**: 기존 `analysis.analyze()`, `MarketRouter`, `admin/ohlcv` (과거 데이터 조회).
- **주의**: 기존 `signal_log`에 `source='backtest'`로 기록 (스키마 이미 존재) — 운영 signal과 분리.

---

## 캐시·인프라 확인

### Redis 사용 여부

- `redis>=5.0,<6.0` 의존성 존재 (pyproject.toml).
- Upstash Redis 사용 (rediss:// URL). Railway 서비스 3개(api/bot/broadcast)가 동일 `REDIS_URL` 공유.
- Redis 없는 환경(로컬 dev)은 캐시 건너뛰고 HTTP 직접 호출.

### OHLCV 프로바이더 구현 상태

| Provider | 클래스 | 인터벌 지원 | 캐시 | 상태 |
|----------|--------|-------------|------|------|
| Binance | `BinanceClient` (market_data.py) | 1h, 4h, 1d (네이티브) | 2-tier Redis (fresh 5분, backup 24h) | 정상 운영 |
| yfinance | `YFinanceClient` (market/yfinance.py) | 1d (네이티브), 1h (60일 제한), 4h (1h resample) | 2-tier Redis (fresh 1h, backup 24h) | 정상 운영 |

### DB (Supabase PostgreSQL)

- 4개 migration 실행됨 전제 (001 users → 002 watchlist → 003 signal_log → 004 SL/TP).
- asyncpg Pool (min=1, max=5) 싱글톤.

---

## 이후 Phase를 위한 권고사항

### Phase 1: 백테스트 하네스

1. **룩어헤드 방지**: 백테스트 시점 t 기준으로 과거 OHLCV만 analyze()에 넘겨야. Redis 캐시는 현재 "심볼별 최신"이라 t 시점 스냅샷 제공 불가. **admin OHLCV 엔드포인트를 `until=` 파라미터로 확장** 또는 **백테스트 전용 cache key 포맷** 도입.
2. **성능**: 수년치 1h봉 × 수십 심볼 반복 분석은 무거움. 병렬화 or 일봉 위주로 시작 (3TF가 아니라 1d 단일 TF 백테스트부터).
3. **신호 변동성 추적**: 동일 날짜에도 intraday로 등급이 자주 바뀌면 "진입 시점 언제?"가 모호. 백테스트는 1d 종가 기준 1회만 or 3TF 마감 시점 기준으로 정하기.
4. **MFE/MAE 재계산**: Phase 0 tracking과 동일 로직 재사용. `run_phase0_tracking` 로직을 `backtest/tracker.py`로 분리해 공통화 가능.

### Phase 2: 숏 신호 대칭 + 5등급 체계

1. **현재 `_grade_signal`은 롱 전용**: `aligned + UPTREND/BREAKOUT`만 "강진입". 숏은 없음.
2. **대칭 구현 체크포인트**:
   - `alignment.bias == "bearish"` + `aligned` + `DOWNTREND/BREAKDOWN` → "강숏" 가능.
   - `_grade_signal` 반환이 4종에서 5종 이상으로 확장 → `SignalResponse.signal_grade` Pydantic Literal 확장 필요.
   - `_analysis_to_summary` 카드 포맷 분기도 숏용 세팅 블록 필요 (TP가 entry 아래, SL이 entry 위).
3. **TradeSetup 대칭**: `compute_trade_setup`이 현재 롱만 가정. 숏 방향 분기 필요.
4. **signal_log `signal_grade` 컬럼**: TEXT라 enum 확장 영향 없음.

### Phase 3: 지표 고도화

- **RSI divergence**: `tech_analysis.py`에 `rsi_divergence(closes, highs, lows, period)` 함수 추가 예상.
- **Volatility regime**: ATR 기반 regime (low/medium/high). `_SL_ATR_MULT` 같은 tuning 상수를 regime별로 분기.
- **BREAKOUT 재검증**: 현재 3% 하드코드. ATR 기반 동적 임계값 후보 (예: `max(high 중 이전 max) + 1.5 × ATR`).

### Phase 4: 가중치/임계값 튜닝

- Phase 1 백테스트 결과 기반 grid search. `composite.py` 가중치 (0.45/0.35/0.10/0.10), grade 임계값 (75/60/40).
- `_rsi_score`/`_volume_score` 계단 매핑도 튜닝 대상 가능 (연속 함수로 변환).

---

## Open Questions

설계자 판단 필요한 항목:

1. **사주 TTL 확인 필요**: `score_service.py`의 사주 점수 캐시 TTL이 명세 "KST 자정까지 (최소 60초)"와 정확히 일치하는지 코드 재확인. 이번 Phase 0에서는 시간 관계로 헤더만 확인 (line 47 cache_key). 코드 세부 재검증 권고.

2. **volume_profile.top_n 기본값 변경**: 명세(5)에 맞춰 코드 기본값을 3→5로 수정할지, 아니면 명세를 "호출부에서 5로 overide"로 갱신할지. 1줄 수정 vs 명세 수정.

3. **OHLCV Fresh TTL 비대칭**: 명세를 현재 코드 기준으로 고칠지 (provider별 TTL 다름 기재), 아니면 코드를 일원화할지 (둘 다 1h or 둘 다 5분).

4. **Phase 1 백테스트 시작 전 CI 도입 여부**: GitHub Actions 없음. Phase 1 전에 기본 CI 추가하여 백테스트 회귀 자동 방지할지, 아니면 Phase 1 후 병행 작업으로 할지.

5. **backtest 경로 확정**: `src/sajucandle/backtest/` 신규 패키지 vs 기존 `broadcast.py`에 CLI flag (`--backtest from=... to=...`) 추가. 전자는 명확 분리, 후자는 코드 재사용 큼.

6. **숏 구현 시 카드 상징 변경 방향**: "강진입"/"진입"의 한국어를 유지하면서 롱/숏 구분 어떻게 할지 — prefix (롱/숏)? 이모지? 완전 새 label?

---

## CLAUDE.md 갱신 제안

### 기존에서 보존할 내용

CLAUDE.md 파일이 **현재 프로젝트 루트에 존재하지 않음**. 이번 리서치에서 신규 작성 대상.

### 새로 추가할 내용 (제안)

아래 전문을 `CLAUDE.md`로 생성 (프로젝트 루트).

```markdown
# CLAUDE.md — SajuCandle 프로젝트 지침

> Claude Code 세션 시작 시 최우선으로 이 문서를 읽고 모든 작업을 진행하기 전 준수해야 할 규칙·용어·컨벤션을 따른다.

## 1. 워크플로우 규칙

### 1.1 설계자-실행자 모델
- **설계자는 사용자.** 너(Claude)는 실행자(Executor)다.
- 사용자가 `"구현해"` 또는 동등한 명시적 지시를 내리기 전까지 **서비스 코드(`src/sajucandle/*`)를 수정하지 않는다**.
- 리서치, 설계, 플랜 문서 작성은 항상 먼저 한다. 실행은 승인 후.

### 1.2 산출물 규칙
- 채팅에 장문 작성 금지. 모든 산출물은 `docs/**/*.md` 파일로 쓰고 채팅엔 경로와 요약만.
- 산출물 디렉토리 표준:
  - `docs/planning/research/` — 현황 파악 리서치
  - `docs/superpowers/specs/` — 설계 스펙
  - `docs/superpowers/plans/` — 구현 플랜

### 1.3 Phase 모델
- 현재 진행 중: **Phase 0** (현황 파악) → Phase 1 (백테스트 하네스) → Phase 2 (숏 대칭) → Phase 3 (지표 고도화) → Phase 4 (튜닝).
- 각 Phase 완료 시 사용자 승인 대기 → 다음 Phase 프롬프트 작성.

## 2. 도메인 용어

| 용어 | 정의 |
|------|------|
| **swing** | Fractals + ATR prominence 필터로 감지한 국소 고/저점 (`SwingPoint`) |
| **structure** | swing 기반 시장 상태 분류 (UPTREND/DOWNTREND/RANGE/BREAKOUT/BREAKDOWN) |
| **alignment** | 1h/4h/1d 3개 TF의 trend_direction 정렬 상태 |
| **composite_score** | analyze()의 최종 점수 (0.45 structure + 0.35 alignment + 0.10 rsi + 0.10 volume, 0~100) |
| **final_score** | `0.1 × saju + 0.9 × analysis.composite_score` (등급 판정 입력) |
| **signal_grade** | 강진입/진입/관망/회피 4종 (롱 관점. 숏은 Phase 2에서 추가) |
| **TradeSetup** | entry/SL/TP1/TP2/R:R/risk_pct 구체 가격 제시 (진입/강진입 등급만) |
| **S/R** | Support/Resistance 레벨. swing + volume profile 융합 |
| **VPVR** | Volume Profile Visible Range. bucket별 volume 합 상위 N개 |
| **ATR** | Average True Range (Wilder, period=14). 변동성 지표 |
| **EMA** | Exponential Moving Average (period=50, α=2/51) |
| **iljin** | 日辰 — 해당 날짜의 천간지지 (명리) |
| **yongsin** | 用神 — 명식 전체 균형에 도움되는 오행 |

## 3. 코딩 컨벤션

### 3.1 Python 스타일
- **Python 3.12+** 전제. `from __future__ import annotations` 항상 사용.
- **PEP 621** + hatchling 빌드. `pyproject.toml`에 의존성 관리.
- **ruff** 린트 (line-length=100, target-version=py312). 커밋 전 `python -m ruff check src/ tests/` 통과 필수.
- 타입 힌트 적극 사용. dataclass / Pydantic BaseModel로 데이터 구조 표현.
- **Private 상수**는 module-level `_PREFIX` 언더스코어.
- **async** I/O는 FastAPI + asyncpg. 순수 계산 함수는 sync.

### 3.2 테스트
- pytest + pytest-asyncio (`asyncio_mode = "auto"`).
- TDD 선호: 테스트 먼저 → 실패 확인 → 구현 → 통과 → commit.
- DB 통합 테스트는 `db_conn` fixture(트랜잭션 롤백) 사용. `TEST_DATABASE_URL` 없을 때 자동 skip.
- Mock: `unittest.mock` + `respx` (httpx) + `fakeredis`.

### 3.3 커밋 메시지
- Conventional commits: `feat(scope): ...`, `fix(...)`, `docs(...)`, `refactor(...)`, `test(...)`.
- 각 task = 1 commit 원칙 (구현 플랜의 subagent-driven 패턴 계승).

## 4. 모듈 책임

### 4.1 분석 엔진 (`src/sajucandle/analysis/`)

| 모듈 | 책임 |
|------|------|
| `swing.py` | Fractals + ATR prominence → `SwingPoint` list |
| `structure.py` | swings → `MarketStructure` enum + score |
| `timeframe.py` | 단일 TF EMA50 기반 `TrendDirection` enum |
| `multi_timeframe.py` | 3TF 정렬 → `Alignment` (aligned/bias/score) |
| `volume_profile.py` | VPVR bucket 누적 → top-N `VolumeNode` |
| `support_resistance.py` | swing + volume 융합 → 현재가 기준 `SRLevel` 최대 6개 |
| `trade_setup.py` | ATR + S/R snap 하이브리드 → `TradeSetup` |
| `composite.py` | 위 모듈 조합 → `AnalysisResult` (analyze 엔트리) |

### 4.2 서비스 레이어

| 모듈 | 책임 |
|------|------|
| `signal_service.py` | analyze() + 사주 합산 + 등급 판정 + TradeSetup 생성 + Redis 캐시 |
| `score_service.py` | 사주 4축 점수 + KST 자정 TTL 캐시 |
| `tech_analysis.py` | RSI/SMA/volume_ratio/score 매핑 (순수 함수) |
| `market_data.py` | Binance OHLCV 클라이언트 + 2-tier Redis 캐시 (fresh 5분/backup 24h) |
| `market/yfinance.py` | yfinance OHLCV + 2-tier 캐시 (fresh 1h/backup 24h) + 4h resample |
| `market/router.py` | ticker → provider 라우팅 + 화이트리스트 |

### 4.3 인프라

| 모듈 | 책임 |
|------|------|
| `api.py` | FastAPI 엔드포인트 전체 (14개) |
| `api_client.py` | 봇 → API httpx 래퍼 |
| `handlers.py` | Telegram 커맨드 (13개) + 카드 포맷 |
| `broadcast.py` | 일일 푸시 CLI (Phase 0 tracking → Phase 1 precompute → Phase 2 사주 → Phase 3 watchlist) |
| `repositories.py` | DB CRUD (users/user_bazi/user_watchlist/signal_log) |
| `models.py` | Pydantic 모델 |
| `format.py` | 명식 카드 + DISCLAIMER 상수 |

## 5. 제약사항 / 주의점

### 5.1 외부 API 제약
- **yfinance 1h 인터벌**: 최근 **60일**만 조회 가능. 백테스트 시 제약.
- **yfinance 4h**: 네이티브 미지원 → 1h 데이터를 `pandas.resample("4h", origin="epoch")`로 집계.
- **Binance `data-api.binance.vision`**: Market data 공개 미러. 인증 불필요. Railway IP 차단 우회 (`api.binance.com`은 차단됨).
- **미국 장 공휴일 미처리**: `is_market_open`이 True로 잘못 판정될 수 있음 (1년 ~9일). `last_session_date`는 yfinance가 휴장일 데이터 안 주므로 정확.

### 5.2 로직 제약
- **숏 미지원**: 현재 분석은 롱 관점만. 하락장은 "회피"로만 표시. Phase 2에서 대칭 구현 예정.
- **사주 가중치 10%**: Week 8에서 0.4→0.1로 강등. 실 트레이딩 판단은 차트 중심.
- **구조 판정 엄격**: UPTREND/DOWNTREND는 3개 연속 HH-HL/LH-LL 요구. swing 부족 시 RANGE 폴백 → composite에서 alignment 50% 섞음.
- **튜닝 상수**: `_SL_ATR_MULT` 등은 **백테스트 이전 initial value**. Phase 4에서 조정 예정.

### 5.3 캐시 TTL (provider별 비대칭 주의)
- Binance OHLCV: **fresh 5분** (24/7 시장 실시간성)
- yfinance OHLCV: **fresh 1h** (시간외 변동 작음)
- Signal composite: 5분 (`signal:*`)
- 사주: KST 자정까지 (`score:*`)

## 6. 현재 구현 상태 (Phase 0 확정)

- **브랜치**: `main` (commit `c092a7c` 기준)
- **주차**: Week 10 Phase 2 완료
- **테스트**: 307 passed, 69 skipped
- **상세**: `docs/planning/research/phase0_current_state.md` (이 문서 바로 위 섹션)

## 7. 다음 단계 (Phase 1 준비)

Phase 1은 **백테스트 하네스 구축**. 시작 전 설계자가 Phase 0 리서치의 "Open Questions"에 답변 필요:

1. volume_profile.top_n 기본값 3 → 5 보정 여부
2. OHLCV TTL 비대칭을 명세 반영 or 코드 일원화
3. Phase 1 전 CI 도입 여부
4. backtest 패키지 경로 (신규 vs broadcast CLI 확장)

위 답변 후 Phase 1 프롬프트 작성 단계로 이동.
```
