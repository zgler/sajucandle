# 사주캔들 (Saju Candle)

명리학(四柱) × 퀀트 하이브리드 스윙 트레이딩 추천 시스템.
전문가형 구독 도구. PRD v1.0 기반.

**현재 상태**: Phase 0 완료 — 만세력 엔진 + 대운/세운/월운/일진 + 합충형파해 + 십신 + 신살 + 종목 사주 DB + 종합 점수 파이프라인.

---

## 프로젝트 구조

```
src/sajucandle/
├── manseryeok/
│   ├── __init__.py
│   └── core.py                # sajupy fork: skyfield CSV + KST 절기 비교
├── saju/
│   ├── constants.py           # 천간/지지/60갑자/오행/음양/십신 기초
│   ├── daeun.py               # 대운 (순/역행, 시작 나이 연속값)
│   ├── sewoon.py              # 세운/월운/일진 래퍼
│   ├── relations.py           # 합충형파해 + 삼합 + 오행균형
│   ├── tengod.py              # 십신 10종
│   ├── shinsal.py             # 신살 12종 (길신 6 + 흉신 6)
│   └── scorer.py              # 종합 사주 점수 (PRD §4-3, 100점)
└── ticker/
    ├── schema.py              # TickerRecord 데이터클래스
    ├── loader.py              # CSV 로더
    └── saju_resolver.py       # 다층 종목 사주 해석

data/
├── solar_terms/               # skyfield 정확 절기 DB (1900~2100, 4826건)
├── manseryeok/
│   └── calendar_data_v1.csv   # 73442일 만세력 (KST 기준 term_time)
└── tickers/
    └── sample_tickers.csv     # 샘플 종목 20개 (코인 10, 주식 10)

tools/                         # 빌드 및 검증 스크립트
├── compute_solar_terms.py     # skyfield로 24절기 생성
├── compare_solar_terms.py     # sajupy CSV vs skyfield 오차
├── build_manseryeok_csv.py    # 새 만세력 CSV 생성
├── verify_day_pillar.py       # day_pillar 내부 일관성
└── cross_validate_day_pillar.py  # lunar-python과 독립 검증

tests/                         # 스모크 테스트
├── smoke_test_sajupy.py       # 원본 sajupy 기초 동작
├── smoke_test_forked_engine.py  # fork 엔진 (입춘 경계 분단위)
├── smoke_test_daeun.py        # 대운/세운/월운/일진
├── smoke_test_saju_scoring.py # relations + tengod + shinsal
└── smoke_test_full_pipeline.py  # 20개 종목 랭킹 산출

.venv/                          # Python venv (3.14)
```

---

## 설치

```bash
python -m venv .venv
.venv/Scripts/python.exe -m pip install skyfield pandas geopy lunar-python sajupy
```

(개발 중에는 sajupy도 설치했지만 `src/sajucandle/manseryeok/core.py`가 이를 대체한다.)

---

## 실행 예시

### 1. 사주 계산
```python
import sys
sys.path.insert(0, 'src')
from sajucandle.manseryeok.core import SajuCalculator

calc = SajuCalculator()
saju = calc.calculate_saju(
    year=1990, month=10, day=10, hour=14, minute=30,
    city="Seoul", use_solar_time=True,
)
# {'year_pillar': '庚午', 'month_pillar': '丙戌',
#  'day_pillar': '戊申', 'hour_pillar': '己未', ...}
```

### 2. 대운
```python
from sajucandle.saju.daeun import compute_daeun
from datetime import datetime

daeun = compute_daeun(
    calendar_data=calc.data,
    birth_dt=datetime(1990, 10, 10, 14, 30),
    year_pillar="庚午", month_pillar="丙戌", gender="M",
)
# direction: 순행, start_age_years: 9.48
# 10개 대운 리스트
```

### 3. 종목 랭킹
```bash
.venv/Scripts/python.exe tests/smoke_test_full_pipeline.py
```
20개 종목에 대해 오늘의 사주 점수를 100점 만점으로 산출.

---

## 검증 사항

| 항목 | 상태 |
|---|---|
| day_pillar 정확성 (vs lunar-python) | ✅ 20/20 일치 |
| month_pillar 입춘 경계 (KST 17:27) | ✅ 17:26=乙丑, 17:28=丙寅 분단위 정확 |
| year_pillar 입춘 엣지 | ✅ 17:00=癸卯, 17:28=甲辰 |
| skyfield 절기 시각 | ✅ NASA JPL DE440s ephemeris 기반 |
| sajupy 원본 CSV 절기 오차 | ❌ ±20~78분 (부정확, 교체됨) |
| 한자 호환 (淸/清) | ✅ 정규화 함수 내장 |
| 서머타임 처리 | ⚠️ 미지원 (1987~1988 KST 서머타임은 별도 처리 필요) |
| 1900 이전 종목 | ⚠️ founding→listing 폴백 처리 |

---

## 아직 할 일

### Phase 0 잔여
- [ ] 1900 이전 절기 데이터 보강 (1899~1900 경계)
- [ ] 서머타임 시대 처리 (1987~1988 KST)
- [ ] 지장간(地藏干) 전체 (본기/중기/여기) — 현재는 본기만

### Phase 1 (예정)
- [ ] 매크로·FA·TA·온체인 스코어러 구현
- [ ] 통합 랭커 (30/70 가중)
- [ ] 백테스트 프레임워크 (Backtrader + VectorBT)
- [ ] **Null Test 3종** (Placebo, Shuffle, Regime Decomposition)

### Phase 2~4
- 시그널 엔진, 알림, UI, 결제, 한국주식, ML 레이어

---

## PRD 사주 점수 구성 (100점 만점)

| 하위 지표 | 비중 | 산출 방법 |
|---|---:|---|
| 월운 × 종목일주 궁합 | 25 | `relations.pillar_compat_score` |
| 일진 × 종목일주 궁합 | 20 | 동일 |
| 세운 오행 편향 | 15 | 세운 오행 ∩ 종목 4주 오행 |
| 대운 장기 편향 | 10 | 현재 50 고정 (종목엔 대운 없음) |
| 종목 오행 균형도 | 10 | `relations.element_balance` |
| 합충형파해 이벤트 | 10 | 삼합 탐지 위주 |
| 신살 보정 | 10 | `shinsal.shinsal_total_score` |
| **합계** | **100** | `saju.scorer.saju_score` |

초기값(prior)이며 **백테스트 Null Test 결과로 튜닝 예정**.

---

## 라이선스·출처

- sajupy 원본: MIT (0ssw1/sajupy)
- skyfield: MIT (BrandonRhodes/python-skyfield) + JPL DE440s ephemeris
- lunar-python: 독립 검증용 (Apache 2.0)

만세력 CSV (`calendar_data_v1.csv`) 생성 방식:
1. sajupy CSV의 day_pillar 사용 (lunar-python과 20/20 일치 검증)
2. skyfield로 24절기 정확 KST 시각 재생성
3. 연주/월주 재계산 (입춘·월절 기준)
