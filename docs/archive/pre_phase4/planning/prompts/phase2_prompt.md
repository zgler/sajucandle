# Phase 2 프롬프트 (Claude Code용) — 숏 대칭 + 5등급

**사용법**: 아래 `===` 블록 전체를 Claude Code에 복붙. 프로젝트 루트(`D:\사주캔들`)에서 실행.

**선행 조건**:
- Phase 1 완료. `docs/superpowers/specs/2026-04-20-phase1-backtest-harness-design.md` + `docs/superpowers/plans/2026-04-20-phase1-backtest-harness-plan.md` 존재.
- Commit: `8b71d8f` (또는 그 이상) — Phase 1 push 완료.
- `src/sajucandle/backtest/` 패키지 9개 모듈 존재. `migrations/005_signal_log_run_id.sql` 존재.
- (가능하면) Phase 1 스모크 백테스트 결과 `phase1-smoke-prod` run 존재 — 있으면 baseline으로 참조.

---

```
===
[역할]
너는 SajuCandle 프로젝트의 실행자(Executor). 설계자는 나(사용자).
architect-executor 워크플로우 엄격히 따른다:
- CLAUDE.md 최우선 읽기.
- 내가 "구현해"라고 명시 지시하기 전까지 서비스 코드(src/sajucandle/*) 수정 금지.
- 모든 산출물은 .md 파일로 작성. 채팅에 장문 금지.
- 체크리스트/구조 있을 때만 경로+요약만 채팅에.

[배경]
Phase 0 (현황) + Phase 1 (백테스트 하네스) 완료 상태. 주요 산출물:
- docs/planning/research/phase0_current_state.md
- docs/superpowers/specs/2026-04-20-phase1-backtest-harness-design.md (Approved)
- docs/superpowers/plans/2026-04-20-phase1-backtest-harness-plan.md (12 Task 완료)
- CLAUDE.md
- migrations/005_signal_log_run_id.sql (운영 DB에 적용됨)
- src/sajucandle/backtest/ (9 modules)

Phase 2 목표: **숏(하락) 신호 대칭화 + 5등급 체계**.

현재 상태 (Week 10 Phase 2 롱 전용):
- signal_grade: 강진입/진입/관망/회피 — 전부 롱 관점
- DOWNTREND/BREAKDOWN은 "진입"→"관망"으로 downgrade만 됨. 숏 신호는 발생 안 함.
- TradeSetup도 entry < SL < TP (롱만).

Phase 2 목표 상태:
1. 양방향 5등급: 강진입_L / 진입_L / 관망 / 진입_S / 강진입_S
2. DOWNTREND/BREAKDOWN + RSI overbought → 숏 신호화
3. TradeSetup 숏 버전 (entry > SL > TP)
4. Telegram 카드에 방향(L/S) 표시
5. Phase 1 하네스로 롱전용 vs 대칭 A/B 비교 가능하게
6. 회귀 0.

[산출물]
이번 프롬프트는 **설계 spec까지**.
- `docs/superpowers/specs/2026-05-XX-phase2-short-symmetric-design.md` (날짜는 오늘)

설계자 승인 후 별도 지시로 플랜 작성 → 구현 순으로.

[작업 순서]

## Step 1: 기존 코드 재확인
다음 파일들을 읽어 대칭화 접점 파악:
- `src/sajucandle/signal_service.py` — _grade_signal 현재 로직 (_compute_grade, DOWNTREND downgrade 포함)
- `src/sajucandle/analysis/composite.py` — analyze() 출력 (AnalysisResult fields)
- `src/sajucandle/analysis/structure.py` — MarketStructure enum + score 계산
- `src/sajucandle/analysis/trade_setup.py` — 현재 롱 전용 ATR + S/R 융합
- `src/sajucandle/format.py` / `handlers.py` — 카드 포맷 (DISCLAIMER 포함)
- `src/sajucandle/repositories.py` — signal_log INSERT 컬럼
- `migrations/003_signal_log.sql`, `004_signal_log_tradesetup.sql`, `005_signal_log_run_id.sql`

## Step 2: 핵심 설계 결정 8가지
각 항목 옵션 2~3개 + 추천안 + 근거를 spec에 기록.

1. **등급 체계**:
   - 옵션 A: 5등급 (강진입_L/진입_L/관망/진입_S/강진입_S) — 강도×방향 분리
   - 옵션 B: 7등급 (+ 약진입_L/약진입_S)
   - 옵션 C: 방향 분리 컬럼 — grade(강/중/약/회피) + direction(L/S/NEUTRAL) 2D
   - 각 장단: DB 저장/쿼리/카드 표시/백테스트 집계 관점

2. **판정 기준**:
   - 현재: final_score 단일 스칼라 → 구간 판정
   - 숏은 어떻게? 
     - 옵션 A: final_score 유지 + structure가 DOWN*면 숏 구간으로 재매핑
     - 옵션 B: long_score, short_score 2개 별도 계산 → 큰 쪽 방향 + 강도
     - 옵션 C: composite.py의 내부 신호들을 롱/숏 양방향 점수로 재구성

3. **structure_state와 direction의 관계**:
   - UPTREND + BULLISH alignment → L 유력
   - DOWNTREND + BEARISH alignment → S 유력
   - BREAKOUT/BREAKDOWN — 방향 각각 명확
   - RANGE는 NEUTRAL(관망) 고정? 아니면 RSI/MA-slope로 미세 편향 허용?

4. **RSI/오실레이터 대칭화**:
   - 현재 RSI 점수는 oversold(≤30) 가점 편향
   - 숏은 overbought(≥70) 가점으로 대칭
   - RSI divergence(Phase 3에서 도입 예정)와의 충돌/병행

5. **TradeSetup 숏 버전**:
   - entry > SL > TP (방향만 뒤집기)
   - ATR 배수/S-R tolerance/R:R 공식은 롱과 동일하게 대칭인지, 비대칭 조정(숏은 상승반전 위험 ↑)
   - `_SL_ATR_MULT` / `_TP1_ATR_MULT` / `_TP2_ATR_MULT` 상수 L/S 분리 여부

6. **DB 스키마**:
   - 옵션 A: signal_grade만 확장 (값 종류 늘림) — 기존 컬럼 그대로
   - 옵션 B: signal_direction 컬럼 신설 (LONG/SHORT/NEUTRAL) — migration 006
   - 옵션 C: 둘 다 (grade 5종 + direction 3종, redundant but query 편함)
   - Phase 1 백테스트 row 호환성 (기존 롱 데이터 유지)

7. **Telegram 카드 변경**:
   - 등급 표시: "🟢 진입 (롱)" / "🔴 진입 (숏)" 이모지+텍스트
   - TradeSetup 방향 표시: "↑ 상승 베팅" / "↓ 하락 베팅"
   - DISCLAIMER 유지
   - `/card`, `/signal`, 브로드캐스트 카드 일관성

8. **백테스트 검증 전략**:
   - Phase 1 run_id 체계 활용: `phase2-<sha>-longonly` vs `phase2-<sha>-symmetric`
   - 동일 기간/심볼로 비교
   - 등급별 승률/MFE/MAE 비교 — symmetric이 longonly 대비 관망 비율 감소 + 하락장에서 유효 신호 증가 기대
   - 회귀 방어: 기존 롱 signal은 Phase 2 이후에도 동일 grade가 나와야 함

## Step 3: spec 구조

`docs/superpowers/specs/YYYY-MM-DD-phase2-short-symmetric-design.md`:

```markdown
# Phase 2 설계 — 숏 대칭 + 5등급

- 날짜: YYYY-MM-DD
- 대상: Phase 2 (4주 스프린트 중 숏 대칭)
- 상태: Draft (설계자 검토 대기)

## 1. 목적
(3~5줄)

## 2. 목표 / 범위
### 포함
### 범위 밖 (Phase 3~4)

## 3. 설계 결정 (8개)
각 항목: 옵션 A/B/C, 트레이드오프, 추천안, 설계자 선택

## 4. 아키텍처
### 4.1 변경 모듈
### 4.2 분류 로직 흐름 (ASCII)
### 4.3 핵심 함수 시그니처 변경

## 5. 데이터 모델
### 5.1 signal_log 확장 (migration 006 여부)
### 5.2 하위호환 / 마이그레이션 경로

## 6. 등급 판정 규칙
### 6.1 Long 진입 조건 (기존 유지)
### 6.2 Short 진입 조건 (신규)
### 6.3 관망 폴백

## 7. TradeSetup 대칭
### 7.1 숏 버전 공식
### 7.2 L/S 상수 분리 여부

## 8. UI / 출력
### 8.1 Telegram 카드 변경
### 8.2 등급 이모지/라벨

## 9. 테스트 전략
### 9.1 단위 테스트 (_grade_signal 대칭)
### 9.2 통합 (analyze → grade → TradeSetup)
### 9.3 백테스트 A/B (Phase 1 하네스)

## 10. 관측성
로그 / 신호 분포 모니터링

## 11. 위험과 대응
(최소 5개. 숏 추가로 false positive 증가 우려, RANGE에서 방향 판정 민감도, 기존 운영 signal 호환 등)

## 12. 완료 기준
체크리스트

## 13. Phase 3 예고
RSI divergence / Volatility regime / BREAKOUT 재검증
```

## Step 4: 보고

```
Phase 2 설계 스펙 완료.

산출물:
- docs/superpowers/specs/YYYY-MM-DD-phase2-short-symmetric-design.md

주요 설계 결정 (8개):
1. 등급 체계: 추천 A (5등급 강진입_L/진입_L/관망/진입_S/강진입_S)
2. 판정 기준: ...
(각 항목 추천만 1줄)

설계자 판단 필요:
- 8가지 결정 중 추천 그대로 갈지, 특정 항목 변경할지
```

[금지 사항]
- 서비스 코드 수정 금지. 파일 생성은 spec .md 하나만.
- 채팅에 spec 내용 전체 장문 금지.
- 설계 결정 임의 확정 금지.
- 구현 세부 코드 작성 금지 (시그니처만 OK).

[시작]
Step 1부터 시작.
===
```

---

## 이 프롬프트 사용 방법

### 실행 방식
1. 프로젝트 루트(`D:\사주캔들`)에서 Claude Code 세션 시작.
2. 위 `===` 블록 전체 복붙.
3. Claude Code가 spec 작성할 때까지 대기 (~10~15분).
4. spec 열어서 8가지 설계 결정 검토.
5. "전부 추천대로" or 특정 항목 변경 지시.
6. 이 채팅(본 세션)에 spec 결과 공유 → 제가 검토 → Phase 2 plan 프롬프트 작성.

### 전체 Phase 맵
- ✅ Phase 0: 현황 파악
- ✅ Phase 1: 백테스트 하네스 (2026-04-20, 13 commits)
- 🔄 **Phase 2: 숏 대칭 + 5등급** ← 지금
- Phase 3: 지표 고도화 (RSI divergence, Volatility regime, BREAKOUT 재검증)
- Phase 4: composite 가중치/임계값 튜닝

### 참고: Phase 1에서 배운 것
- subagent-driven-development 12 Task 45~60분에 완료 가능
- 플랜에 예시 코드 포함하면 agent의 해석 편차 감소
- `TEST_DATABASE_URL` 없이도 DB 통합 테스트는 skip 처리 → 로컬 개발 OK
- CI (`.github/workflows/ci.yml`)는 매 PR/push마다 검증
- 서비스 코드 변경은 spec에서 명시 허가 받아야 함 (insert/aggregate/api 3건)
