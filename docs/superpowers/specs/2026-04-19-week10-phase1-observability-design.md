# Week 10 Phase 1 설계 — 관측성 도구 (signal_log 집계)

- 날짜: 2026-04-19
- 대상 주차: Week 10 Phase 1 (Phase 2는 데이터 쌓인 후 별도)
- 상태: Draft (자율 판단 기반, 사용자 피드백 시 수정)

## 1. 목적

Week 9에서 signal_log DB 기록 + Phase 0 MFE/MAE 추적을 완성했지만, **사용자가 누적 상황을 쉽게 확인할 수단이 없다.** 매번 Supabase SQL Editor에서 쿼리 치는 건 불편.

Week 10 Phase 1은 **관측 도구만** 먼저 만들어서 사용자가 3~5일 데이터 쌓이는 동안 매일 `/stats` 한 번으로 진행상황 확인할 수 있게 한다. Phase 2(발송 거부 규칙, 카드 튜닝)는 데이터 + 본인 피드백 쌓인 뒤 별도 설계.

## 2. 목표 / 범위

### 포함 (Phase 1)

1. `GET /v1/admin/signal-stats?ticker=&grade=&since=` 엔드포인트
2. `repositories.aggregate_signal_stats()` — 집계 쿼리
3. `ApiClient.get_signal_stats()` 메서드
4. 봇 `/stats [심볼] [등급]` 명령 — admin chat_id만 허용
5. 집계 카드 포맷 (등급별 count + MFE/MAE 통계 + 추적 완료 수)

### 범위 밖 (Phase 2+)

- 발송 거부 규칙 (BREAKDOWN 강진입 차단)
- 카드 세밀 조정 (이모지, 정렬, 에러 메시지)
- 온보딩 flow
- 백테스트 엔진
- 적중률 카드 노출

## 3. 설계 결정 (자율 판단)

| # | 주제 | 결정 | 근거 |
|---|------|------|------|
| 1 | `/stats` 권한 | `SAJUCANDLE_ADMIN_CHAT_ID` env 기반 admin만 | 일반 사용자에게 관리자 통계 노출 X, Week 7 기존 env 재사용 |
| 2 | 기본 since | 30일 전 | 충분히 길되 과도한 DB 부하 방지 |
| 3 | MFE/MAE 집계 대상 | `tracking_done=TRUE` 건만 | 진행 중 row는 최종값 아니라 통계 왜곡 |
| 4 | 카드 길이 | 10줄 이내 | 모바일 가독성 |
| 5 | 필터 파라미터 | ticker(선택), grade(선택), since(선택) 조합 | 필요 최소한 (YAGNI) |

## 4. 아키텍처

### 4.1 API 엔드포인트

```
GET /v1/admin/signal-stats
  auth: X-SAJUCANDLE-KEY
  params:
    ticker  (optional) — "BTCUSDT", "AAPL", ... (MarketRouter 검증 X, freeform)
    grade   (optional) — "강진입"|"진입"|"관망"|"회피"
    since   (optional, ISO 8601) — default: now - 30d
  응답:
    {
      "since": "2026-03-20T00:00:00+00:00",
      "filters": {"ticker": null, "grade": null},
      "total": 42,
      "by_grade": {
        "강진입": 5, "진입": 12, "관망": 20, "회피": 5
      },
      "tracking": {
        "completed": 15,
        "pending": 27
      },
      "mfe_mae": {
        "sample_size": 15,  -- tracking_done=TRUE만 집계
        "mfe_avg": 2.8,
        "mfe_median": 2.3,
        "mae_avg": -1.4,
        "mae_median": -1.1
      }
    }
```

### 4.2 Repository 함수

```python
# repositories.py
async def aggregate_signal_stats(
    conn: asyncpg.Connection,
    *,
    since: datetime,
    ticker: Optional[str] = None,
    grade: Optional[str] = None,
) -> dict:
    """signal_log 집계 — WHERE 조합 동적.

    반환 dict:
      total, by_grade(dict[str, int]),
      tracking_completed, tracking_pending,
      mfe_avg, mfe_median, mae_avg, mae_median, sample_size
    """
```

PostgreSQL `percentile_cont` 사용해 median 계산. `FILTER (WHERE tracking_done)` 로 MFE/MAE는 완료 row만.

### 4.3 api_client

```python
async def get_signal_stats(
    self,
    *,
    ticker: Optional[str] = None,
    grade: Optional[str] = None,
    since: Optional[str] = None,
) -> dict:
    """GET /v1/admin/signal-stats."""
```

### 4.4 봇 `/stats` 명령

```
사용법:
  /stats                   → 전체 30일
  /stats AAPL              → AAPL 30일
  /stats AAPL 진입         → AAPL 진입 등급 30일
  /stats BTCUSDT 관망      → BTCUSDT 관망 등급 30일
```

권한: `update.effective_chat.id == SAJUCANDLE_ADMIN_CHAT_ID` 만 허용. 아니면 "권한 없음" 응답.

### 4.5 카드 포맷

```
📊 신호 통계 (최근 30일)
─────────────
필터: 전체
총 발송: 42건

등급별:
  강진입  5건
  진입    12건
  관망    20건
  회피    5건

추적 완료: 15/42 (35%)

MFE/MAE 평균 (n=15):
  MFE  +2.8% (중앙 +2.3%)
  MAE  -1.4% (중앙 -1.1%)
```

필터가 있으면 "필터: AAPL · 진입" 표시.

## 5. 에러 매트릭스

| 상황 | HTTP | 봇 응답 |
|------|------|---------|
| 인증 실패 (API) | 401 | N/A (직접 호출 시) |
| `/stats` 호출한 chat_id ≠ admin | - | "관리자 전용 명령입니다." |
| DB 미연결 | 503 | "서버 오류 (503)." |
| since 파싱 실패 | 400 | "날짜 형식 오류." |
| tracking_done 건 0개 | 200 | MFE/MAE 섹션 "샘플 부족 (추적 완료 0건)" |
| 전체 0건 | 200 | "해당 조건의 발송 이력이 없습니다." |

## 6. 테스트 전략

| 파일 | 커버리지 |
|------|----------|
| `tests/test_repositories.py` (수정) | aggregate_signal_stats — 빈 결과, ticker/grade 필터, tracking_done filter, median 계산 (DB 통합, TEST_DATABASE_URL 필요) |
| `tests/test_api_stats.py` (신규) | 엔드포인트 인증, 필터 파라미터, 빈 결과, since 파싱 |
| `tests/test_api_client.py` (수정) | get_signal_stats respx mock |
| `tests/test_handlers.py` (수정) | /stats admin only, 인자 파싱, 카드 포맷, 빈 결과 메시지 |

## 7. 관측성

- `logger.info("signal stats ticker=%s grade=%s since=%s total=%s", ...)`

## 8. 배포

1. 코드 push → Railway 자동 재배포.
2. DB 마이그레이션 불필요 (기존 signal_log만 읽음).
3. 운영 스모크:
   - `/stats` 봇 명령 → 현재 시점 관망 1~2건 + 추적 0건 예상
   - 매일 아침 broadcast 후 다시 쳐보면서 tracking 증가 확인

## 9. 완료 기준

- [ ] `aggregate_signal_stats()` 구현 + 단위 테스트 통과
- [ ] `GET /v1/admin/signal-stats` 엔드포인트 동작
- [ ] `ApiClient.get_signal_stats()` 구현
- [ ] `/stats` 봇 명령 admin only + 카드 포맷
- [ ] /help 에 `/stats` 추가 (admin에게만? 아니면 그냥 노출?) — **결정: 일반 /help에는 숨김** (admin만 아는 명령)
- [ ] 배포 후 `/stats` 성공

## 10. Phase 2 예고

3~5일 데이터 축적 + 본인 피드백 수집 후:
- 발송 거부 규칙 (BREAKDOWN 매수 차단)
- 카드 세밀 조정
- 에러 메시지 개선

Phase 2는 별도 스펙.
