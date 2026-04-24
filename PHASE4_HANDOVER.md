# Phase 4 핸드오버 — 본 프로젝트(USB) 폴더 덮어쓰기 매뉴얼

작성일: 2026-04-24
작업 루트(소스): `C:\Users\user\Downloads\사주캔들 로직\` (분석 로직 전용 폴더)
목적: USB 본 프로젝트 폴더에 Phase 4 산출물을 머지/덮어쓰기 위한 가이드.

---

## 1. 핵심 결론 (이 핸드오버를 읽는 이유)

1. **사주 = 가중치 실패, 필터로만 유효**
   - Null Test v1 (30%): z = −7.46 FAIL
   - Null Test v2 (10%, 3컴포넌트): z = −3.97 FAIL
   - 원인: 60갑자 사이클 → 구조적 나이/섹터 편향. 가중치 레벨에서 불가역.

2. **확정 전략 = C 필터 (사주 < 30 제외 후 순수 퀀트 랭킹)**

   | 자산 | 기간 | CAGR | Sharpe | MDD |
   |---|---|---|---|---|
   | 주식 (SPY B&H) | 2015–24 | 13.0% | 0.90 | −33.7% |
   | 주식 C필터 <30 | 2015–24 | **14.0%** | **0.97** | **−14.8%** |
   | 코인 C필터 <30 | 2020-10–2024 | **85.8%** | **0.93** | −72.5% |

3. **Regime-conditional은 불필요**
   - Sideways 비중 71% → C필터 always-ON과 결과 완전 동일.

4. **OOS 검증 ✅ PASS** (2026-04-24 완료)
   - 학습(2015-19) 최적 = 테스트(2020-24) 최적 = **threshold 20** (양 기간 모두 1위)
   - 테스트 Sharpe 0.98 (SPY 0.90 초과), Sharpe 감소율 14% (정상)
   - threshold 20-30은 동률(테스트 Sharpe 0.98), 40+ 급락 (0.55)
   - 상세: `tests/smoke_output_oos_validation.json`

---

## 2. USB 폴더에 "덮어쓰기/추가"할 파일 목록

### 2.1 신규 추가 (Phase 4 핵심)

```
src/sajucandle/signal/__init__.py
src/sajucandle/signal/engine.py           ← 월간 시그널 생성기 (BUY/HOLD/SELL/WATCH/KILL)
src/sajucandle/signal/regime.py           ← Bull/Bear/Sideways 레짐 감지
src/sajucandle/signal/renderer.py         ← Telegram MDv2 / HTML / 텍스트 렌더링

src/sajucandle/api/__init__.py
src/sajucandle/api/main.py                ← FastAPI (/signals/stock 등)

src/sajucandle/scheduler/__init__.py
src/sajucandle/scheduler/runner.py        ← 월간 자동실행 (APScheduler)

data/tickers/coin_universe_15.csv         ← 코인 15종 재설계
```

### 2.2 기존 파일 수정 여부 확인 필요 (USB 쪽과 비교 후 머지)

```
src/sajucandle/quant/backtest.py          ← saju_filter_mode 플래그 추가
src/sajucandle/quant/ranker.py            ← saju_filter_mode 지원
data/tickers/stock_universe_30.csv        ← 최신판
```

### 2.3 검증용 테스트 (tests/)

```
tests/smoke_test_signal_engine.py         ← 시그널 엔진 통합
tests/smoke_test_regime_engine.py         ← 레짐 조건부 백테스트
tests/smoke_test_oos_validation.py        ← 아웃오브샘플 검증
tests/smoke_test_coin_v2.py               ← 코인 15종 백테스트
tests/smoke_test_nulltest_v2.py           ← v2 10% Null Test
tests/smoke_test_saju_v2.py               ← saju_score_v2
```

### 2.4 결과물(참고용, 덮어쓰기 불필요)

```
tests/smoke_output_*.json                 ← 각 테스트 결과 원본
```

---

## 3. 덮어쓰기 절차 (USB 확보 후)

```bash
# 1. 본 프로젝트 루트(USB)에서 백업 먼저
cp -r <USB_PROJECT_ROOT> <USB_PROJECT_ROOT>_backup_20260424

# 2. 여기(C:\Users\user\Downloads\사주캔들 로직)의 파일을 복사
# 2-1. 신규 폴더 전체 복사
cp -r src/sajucandle/signal    <USB>/src/sajucandle/
cp -r src/sajucandle/api       <USB>/src/sajucandle/
cp -r src/sajucandle/scheduler <USB>/src/sajucandle/

# 2-2. 데이터/유니버스
cp data/tickers/coin_universe_15.csv <USB>/data/tickers/

# 2-3. 테스트 파일
cp tests/smoke_test_signal_engine.py   <USB>/tests/
cp tests/smoke_test_regime_engine.py   <USB>/tests/
cp tests/smoke_test_oos_validation.py  <USB>/tests/
cp tests/smoke_test_coin_v2.py         <USB>/tests/
cp tests/smoke_test_nulltest_v2.py     <USB>/tests/
cp tests/smoke_test_saju_v2.py         <USB>/tests/

# 2-4. backtest/ranker는 diff 먼저
diff <USB>/src/sajucandle/quant/backtest.py src/sajucandle/quant/backtest.py
diff <USB>/src/sajucandle/quant/ranker.py   src/sajucandle/quant/ranker.py
# → 차이 확인 후 수동 머지 (USB에 최신 변경이 있을 수 있음)

# 3. 덮어쓰기 후 동작 확인
cd <USB>
PYTHONPATH=src .venv/Scripts/python.exe tests/smoke_test_signal_engine.py
```

---

## 4. 신규 의존성

```
fastapi               # API 서버
uvicorn               # ASGI
apscheduler           # 월간 스케줄러
```

설치:
```bash
pip install fastapi uvicorn apscheduler
```
혹은 `pyproject.toml`의 dependencies에 추가.

---

## 5. 실행 진입점 (USB 덮어쓰기 후)

### API 서버
```bash
PYTHONPATH=src uvicorn sajucandle.api.main:app --port 8001
```
- `GET /health`
- `GET /signals/stock` — JSON
- `GET /signals/stock/html` — HTML
- `GET /signals/stock/telegram` — Telegram MDv2 텍스트

### 스케줄러 데몬
```bash
PYTHONPATH=src python -m sajucandle.scheduler.runner --daemon
# 매월 1일 09:00 KST 자동 실행
```

### 수동 시그널 생성 (특정일)
```bash
PYTHONPATH=src python -m sajucandle.scheduler.runner --date 2026-05-01
```

---

## 6. 검증 결과 테이블

### 6.1 주식 (2015-01 ~ 2024-12, 30종 유니버스)
| 전략 | CAGR | Sharpe | MDD | Hit |
|---|---|---|---|---|
| SPY B&H | 13.0% | 0.90 | −33.7% | — |
| 순수 퀀트 (필터없음) | 7.6% | 0.65 | −19.1% | 57.1% |
| **C 필터 <30** | **14.0%** | **0.97** | **−14.8%** | 62.2% |
| Regime-conditional | 14.0% | 0.97 | −14.8% | 62.2% |

### 6.2 코인 (2020-10 ~ 2024-12, 15종)
| 전략 | CAGR | Sharpe | MDD | Hit |
|---|---|---|---|---|
| BTC B&H | ≈+68%/yr | — | — | — |
| 순수 퀀트 | 14.0% | 0.51 | −73.6% | 40.0% |
| **C 필터 <30** | **85.8%** | **0.93** | −72.5% | 58.0% |
| C 필터 <40 | 45.6% | 0.78 | −76.1% | 58.0% |
| 사주 30% 가중(deprecated) | 79.1% | 0.90 | −73.4% | 56.0% |

### 6.3 OOS 검증 (threshold grid, 2026-04-24)
| threshold | 학습 Sharpe | 테스트 Sharpe | Δ |
|---|---|---|---|
| 0 | 0.64 | 0.92 | — |
| **20** | **1.14** | **0.98** | −14% ⭐ |
| 30 | 1.08 | 0.98 | −9% |
| 40 | 1.02 | 0.55 | −46% |
| 50 | 0.84 | 0.54 | −36% |

→ 학습·테스트 공통 최적 = threshold 20. 30도 동률. 40+ 급락(overfitting 경계). **Sweet spot: 20–30.**

### 6.4 Null Test 요약 (확정)
| 버전 | Sharpe | Placebo 평균 | z-score | 판정 |
|---|---|---|---|---|
| v1 (30% 가중) | — | — | −7.46 | FAIL |
| v2 (10% 가중) | 0.58 | — | −3.97 | FAIL |
| C 필터 <30 | 0.97 | — | 확인 필요 | 잠정 PASS |

### 6.5 Regime 분포 (2015–24, SPY 3개월 롤링)
- Bull: 19%
- Bear: 10%
- Sideways: **71%**
- → 레짐 게이팅 무의미.

---

## 7. 다음 단계 (USB 확보 후)

1. **threshold 20 vs 30 선택**: OOS에서 20=30 동률. 엔진 default는 30 유지하되, 실운영에서 20으로 낮추는 실험 고려.
2. **UI/렌더링 연결**: 본 폴더의 renderer.py 출력을 USB의 프론트엔드/이메일/텔레그램 봇에 연결.
3. **구독자 DB 연동**: 시그널 → 구독자별 전송 파이프라인 (USB에 별도 보관 중).
4. **결제 연동**: (USB 영역, 이번 핸드오버 범위 밖)
5. **Phase 2 코인 정밀 재검증**: 이번에 확인한 유니버스 15종 / 50개월 결과를 공식 Null Test에 넣기.

---

## 8. 주의사항

- **saju_score_v2 (3컴포넌트 + ICIR 가중) 는 v2 Null Test에서도 FAIL.** 가중치 방식 완전 폐기 권장.
- **Windows stdout 버퍼링**: 테스트 재실행 시 파이썬 로그가 지연 표시됨. `sys.stdout.reconfigure(encoding="utf-8")` 필수.
- **PowerShell $env 이슈**: 백그라운드 실행 시 `$env:PYTHONPATH`가 bash에서 먹히므로 `PYTHONPATH=src ./.venv/Scripts/python.exe ...` 형태로 bash-native 실행.
- **APScheduler job.next_run_time**: 스케줄러 start() 이전에 접근 금지.
- **FastAPI load_tickers**: Path 객체 필요 (`str()` 변환 금지).

---

## 9. 파일 매니페스트 (자동 생성된 타임스탬프 기준)

| 파일 | 용도 | 수정일 |
|---|---|---|
| src/sajucandle/signal/engine.py | 시그널 생성기 | 2026-04-23 22:10 |
| src/sajucandle/signal/regime.py | 레짐 감지 | 2026-04-23 22:09 |
| src/sajucandle/signal/renderer.py | 출력 포맷 | 2026-04-23 18:21 |
| src/sajucandle/api/main.py | FastAPI | 2026-04-23 18:23 |
| src/sajucandle/scheduler/runner.py | 월간 크론 | 2026-04-23 18:34 |
| data/tickers/coin_universe_15.csv | 코인 유니버스 | 2026-04-23 22:05 |
| tests/smoke_test_oos_validation.py | OOS 검증 | 2026-04-23 22:16 |
| tests/smoke_test_regime_engine.py | 레짐 백테스트 | 2026-04-23 22:11 |
| tests/smoke_test_coin_v2.py | 코인 재검증 | 2026-04-23 22:06 |

---

**끝. USB 확보 후 이 문서를 기준으로 덮어쓰기 진행.**
