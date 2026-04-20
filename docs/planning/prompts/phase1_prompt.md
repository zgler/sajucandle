# Phase 1 프롬프트 (Claude Code용) — 백테스트 하네스 구축

**사용법**: 아래 `===` 블록 전체를 Claude Code에 복붙. 프로젝트 루트(`D:\사주캔들`)에서 실행 상태여야 함.

**선행 조건**:
- Phase 0 완료. `docs/planning/research/phase0_current_state.md` 존재.
- `CLAUDE.md` 프로젝트 루트에 존재.
- Commit: `32068bd` 이상 (Phase 0 커밋 포함).
- `volume_profile.top_n` 기본값 5로 수정됨.
- CI (`.github/workflows/ci.yml`) 존재.

---

```
===
[역할]
너는 SajuCandle 프로젝트의 실행자(Executor)다. 설계자는 나(사용자)다.
architect-executor 워크플로우를 엄격히 따른다:
- CLAUDE.md를 최우선으로 읽고 거기 정의된 규칙·용어·컨벤션을 따른다.
- 내가 "구현해"라고 명시적으로 지시하기 전까지 서비스 코드(src/sajucandle/*)를 수정하지 않는다.
- 모든 산출물은 채팅에 장문으로 쓰지 말고 .md 파일로 작성한다.
- 체크리스트/구조가 있을 때만 채팅엔 경로와 요약만 쓴다.

[배경]
Phase 0 (현황 파악) 완료 상태. 산출물:
- docs/planning/research/phase0_current_state.md — 명세↔코드 대조 (94% 일치 확인)
- CLAUDE.md — 프로젝트 지침
이번 Phase 1의 목표는 **백테스트 하네스(backtest harness) 구축**이다. 구축 후 Phase 2~4는 하네스를 이용해 실데이터 기반 설계가 가능해진다.

현재 signal_log 테이블은 운영 시그널만 기록. 백테스트는 `source='backtest'`로 기록하면 동일 테이블 재사용 가능 (Week 8 migration 003에서 source 컬럼 이미 존재).

Phase 0 리서치의 "이후 Phase를 위한 권고사항" 섹션 반드시 먼저 읽을 것. 특히:
- 룩어헤드 방지 (시점 t 기준 과거 OHLCV만 공급)
- 성능 (수년치 × 수십 심볼 반복)
- MFE/MAE 재계산 — run_phase0_tracking 로직 재사용 가능성

[Phase 1 목표]
1. 과거 OHLCV 데이터로 임의 시점 t에 analyze() + _grade_signal()을 호출해 당시 signal을 재생산하는 엔진을 만든다.
2. 각 백테스트 시그널에 대해 MFE/MAE 같은 성과 지표를 계산한다.
3. 결과를 signal_log에 source='backtest'로 기록한다.
4. 집계 쿼리로 등급별 승률/평균 R:R/평균 MFE/MAE를 뽑을 수 있는 상태를 만든다.
5. 서비스 코드 회귀 0 (기존 307 passed 유지).

[산출물]
Phase 1은 설계(spec) → 플랜(plan) → 구현 3단계로 나뉜다. 이번 프롬프트는 **설계까지**다.

다음 한 파일을 작성한다:
- `docs/superpowers/specs/2026-04-20-phase1-backtest-harness-design.md`

설계자 승인 후 별도 지시로 플랜 작성 → 구현 순으로 진행한다.

[작업 순서]

## Step 1: 기존 코드 재확인
다음 파일들을 읽어 Phase 1이 재사용/확장할 접점 파악:
- `src/sajucandle/analysis/composite.py` (analyze 엔트리)
- `src/sajucandle/signal_service.py` (_grade_signal 로직)
- `src/sajucandle/market/router.py` (ticker → provider)
- `src/sajucandle/market/binance.py`, `market/yfinance.py` (과거 OHLCV 조회 가능성)
- `src/sajucandle/repositories.py` (insert_signal_log, update_signal_tracking)
- `src/sajucandle/broadcast.py` (run_phase0_tracking 함수 — 재사용 후보)
- `migrations/003_signal_log.sql`, `004_signal_log_tradesetup.sql` (기존 스키마 확인)

## Step 2: 핵심 설계 결정 7가지
각 항목에 대해 옵션 2~3개와 추천안 + 근거를 spec에 기록한다. 설계자가 채팅으로 A/B/C 답하면 spec에 반영.

1. **시간 스냅샷 메커니즘**:
   - 백테스트 시점 t 기준 과거 OHLCV만 analyze()에 공급해야 룩어헤드 방지.
   - 옵션 A: 시작 시점에 전체 히스토리 한 번에 받고 슬라이싱
   - 옵션 B: 매 시점마다 provider에 `until=t` 파라미터 호출
   - 옵션 C: in-memory cache 후 윈도우만 슬라이싱

2. **타임프레임 전략**:
   - 운영 엔진은 1h/4h/1d 3TF 요구.
   - 옵션 A: 1d 단일 TF로 시작 (성능 우선, Phase 4 튜닝도 1d만)
   - 옵션 B: 3TF 전체 (운영 엔진 그대로 사용)

3. **심볼 범위**:
   - 11종 (crypto 3 + stock 8) 전부 vs 일부

4. **기간**:
   - crypto: Binance는 과거 수년치 조회 가능
   - stock: yfinance 1h은 60일 제한. 1d만 쓰면 수년치 가능.
   - 옵션 A: 최근 1년
   - 옵션 B: 최근 2~3년
   - 옵션 C: 자산별로 다르게 (crypto 3년, stock 2년)

5. **시그널 발생 빈도**:
   - 옵션 A: 매일 1회 (UTC 기준 일봉 종가)
   - 옵션 B: 매 4h마다
   - 옵션 C: 매시간

6. **결과 저장**:
   - 옵션 A: 기존 signal_log 재사용 (source='backtest')
   - 옵션 B: 별도 `backtest_runs` + `backtest_signals` 테이블
   - 기존 signal_log 재사용 시 백테스트 run별 구분 필드 필요 (예: run_id 컬럼 추가 migration)

7. **실행 인터페이스**:
   - 옵션 A: CLI — `python -m sajucandle.backtest <ticker> <from> <to>`
   - 옵션 B: Jupyter/스크립트 기반
   - 옵션 C: API 엔드포인트 (`POST /v1/admin/backtest`)

## Step 3: 설계 스펙 작성
`docs/superpowers/specs/2026-04-20-phase1-backtest-harness-design.md` 구조:

```markdown
# Phase 1 설계 — 백테스트 하네스

- 날짜: 2026-04-20
- 대상: Phase 1 (4주 스프린트 중 백테스트 인프라)
- 상태: Draft (설계자 검토 대기)

## 1. 목적
(3~5줄)

## 2. 목표 / 범위
### 포함
### 범위 밖 (Phase 2~4)

## 3. 설계 결정 (7개)
각 항목: 옵션 A/B/C, 트레이드오프, 추천안, 설계자 선택 기록

## 4. 아키텍처
### 4.1 모듈 구성
### 4.2 데이터 흐름 (ASCII 다이어그램)
### 4.3 핵심 클래스/함수 시그니처

## 5. 데이터 모델
### 5.1 signal_log 확장 (필요 시 migration 005)
### 5.2 BacktestRun / BacktestSignal (필요 시)

## 6. 시간 스냅샷 / 룩어헤드 방지
구체 구현 방식

## 7. 성능
### 7.1 예상 연산량
### 7.2 병렬화 전략

## 8. 집계/분석
### 8.1 승률 계산 공식
### 8.2 등급별 MFE/MAE 분포
### 8.3 결과 조회 SQL 예시

## 9. 테스트 전략
### 9.1 단위 테스트
### 9.2 통합 테스트 (소규모 히스토리로 smoke)
### 9.3 회귀 방어 (CI 반영)

## 10. 관측성
- 진행률 로그
- 실패한 시그널 복구

## 11. 위험과 대응
(최소 5개)

## 12. 완료 기준
체크리스트

## 13. Phase 2 예고
Phase 2에서 하네스를 어떻게 쓸지 미리보기
```

## Step 4: 보고
다음 형식으로 보고하고 대기:

```
Phase 1 설계 스펙 완료.

산출물:
- docs/superpowers/specs/2026-04-20-phase1-backtest-harness-design.md

주요 설계 결정 (7개):
1. 시간 스냅샷: 추천 B (매 시점마다 provider `until=t` 호출)
2. 타임프레임: 추천 A (1d 단일 TF로 시작)
3. ... (각 항목 추천만 1줄)

설계자 판단 필요:
- 7가지 결정 중 추천 그대로 갈지, 특정 항목 변경할지
- "전부 추천대로" or "X는 B로, Y는 C로" 식으로 답

승인 후 Phase 1 플랜 (tasks 분해) 작성으로 진행.
```

[금지 사항]
- 서비스 코드 수정 금지. 파일 생성은 spec .md 하나만.
- 채팅에 spec 내용 전체 장문 금지.
- 설계 결정 임의 확정 금지 — 추천만 제시하고 설계자 판단 기다림.
- 구현 세부 코드 작성 금지 (시그니처만 OK).

[시작]
위 작업을 시작한다. Step 1 코드 재확인부터.
===
```

---

## 이 프롬프트 사용 시 참고

### 실행 방식
1. 프로젝트 루트에서 Claude Code 세션 시작 (`CLAUDE.md` 자동 로드됨)
2. 위 `===` 블록 통째로 붙여넣기
3. Claude Code가 spec 파일을 작성할 때까지 대기 (~10분)
4. spec 열어서 7가지 설계 결정 검토
5. "전부 추천대로" or 특정 항목 변경 지시
6. 설계 확정 후 Phase 1 플랜 프롬프트 작성 (이 채팅에서)

### 다음 단계 (Phase 1 spec 승인 후)
- **Phase 1B 플랜 프롬프트**: spec을 구현 task 리스트로 분해
- **Phase 1C 구현**: subagent-driven으로 task별 구현

### 전체 Phase 맵
- ✅ Phase 0: 현황 파악
- 🔄 **Phase 1: 백테스트 하네스** ← 지금
- Phase 2: 숏 신호 대칭 (5등급)
- Phase 3: 지표 고도화 (RSI divergence, Volatility regime, BREAKOUT 재검증)
- Phase 4: composite 가중치/임계값 튜닝
