# Python → TS 엔진 포팅 전략 설계

- **날짜:** 2026-04-15
- **상태:** APPROVED
- **관련 문서:** `C:\Users\user\.gstack\projects\sajucandle\user-main-design-20260415-223601.md` (B+C 하이브리드 실행 계획)

## 1. 결론

**포팅 안 한다.** Python을 단일 소스로 두고 웹은 서버에서 API로만 호출한다.

- 프로토타입 100% 보존
- 로직 드리프트 위험 0
- Week 3부터 웹 UI 연결 가능

선택지 비교:

| 옵션 | 판정 | 이유 |
|------|------|------|
| X) 쌍둥이 엔진 (Python+TS) | 보류 | 만세력 TS 포팅 리스크, equivalence CI 부담, 이 타임라인에 과함 |
| **Y) Python 표준** | **채택** | 포팅 공수 0, 단일 소스, 빠른 출시 |
| Z) TS 표준 | 기각 | 프로토타입 폐기 + 봇 재작성, 빌더 모드에 역행 |

## 2. 아키텍처

```
[Telegram Bot (python-telegram-bot)]  ─┐
                                       ├─► [FastAPI on Railway] ─► [Upstash Redis] (만세력 캐시)
[Next.js API Routes (Vercel)]         ─┘            │
        ▲                                           ├─► yfinance (미국주식)
        │                                           ├─► KIS OpenAPI (국내주식, Week 3+)
[Browser]                                           └─► Supabase Postgres (사용자/저장)
```

### 책임 경계

- **FastAPI (Railway):** saju_engine, chart_engine, 가격 데이터 fetch, Redis 캐싱, Railway cron 잡
- **Next.js (Vercel):** UI, 인증(Supabase Auth), 서버 라우트에서만 FastAPI 호출
- **Telegram Bot (Railway, FastAPI와 같은 프로세스에서 시작):** 커맨드 파싱, FastAPI 결과 카드 렌더링
- **공유 규약:** 내부 인증 토큰 1개 (`X-SAJUCANDLE-KEY`), Railway env로만 전달. 브라우저 노출 금지.

## 3. API 계약 (초안)

```
POST /api/v1/bazi           { birth_datetime } → { chart, day_pillar }
POST /api/v1/saju-score     { birth_datetime, asset_class } → ScoreCard
POST /api/v1/recommend      { birth_datetime, symbol, asset_class } → Recommendation
GET  /api/v1/health
POST /internal/cron/precompute-daily    (Railway cron only)
POST /internal/cron/morning-push        (Railway cron only)
```

### 타입 공유

- FastAPI에서 Pydantic 모델 → OpenAPI 스키마 자동 생성
- `openapi-typescript`로 Next.js TS 타입 생성 (빌드 스크립트 1줄)
- 수동 타입 중복 0

## 4. 만세력 캐싱 전략

- 소스: `lunar_python` 런타임 계산
- 캐시: Upstash Redis
- Key: `bazi:{YYYYMMDDHH}` (시진 단위)
- TTL: 30일
- 위치: `SajuEngine.calc_bazi` 앞단 wrapper. 미스 시 계산 → set.
- 일일 신규 사용자 N명 기준 ~N회 미스, 이후 전원 hit

향후 옵션 (P2+): Redis hit ratio가 낮아지거나 부하 이슈 생기면 SQLite 1900-2100 프리컴퓨트로 이전 검토.

## 5. 콜드 스타트 완화

- Railway Hobby: FastAPI를 `gunicorn --workers 1 --timeout 60`, keep-alive
- 07:00 푸시 크론이 자연스러운 warm-up 역할
- UptimeRobot 또는 Railway health check로 5분 간격 `/health` ping
- Pro 업그레이드($20/mo)는 유료 전환 신호 나오면 검토

## 6. 개발 순서 (3개월 재배치)

| 주차 | 트랙 | 작업 |
|------|------|------|
| 1 | C | git init, BotFather, Railway 세팅, `/start` 핸들러, KIS 신청 |
| 2 | C | FastAPI 분리 시작 (bot 프로세스와 동거 OK), `/bazi` `/saju-score` 노출, Redis 캐싱 |
| 3 | B | Next.js 스캐폴딩, Supabase Auth, `/recommend` 붙이고 명식 카드 UI |
| 4 | B | yfinance 미국주식 4-5종, 일일 추천 카드 완성 |
| 5 | C+B | Railway cron 잡 (06:00/07:00), Telegram 푸시 |
| 6-8 | B | KIS 연동, 국내주식 추가, 럭키 캘린더 |
| 9-12 | B | 저장/히스토리, 웹 푸시, 정식 런칭 준비 |

## 7. 배치 잡 (Railway Cron)

| 시각 (KST) | 잡 | 내용 |
|-----------|-----|------|
| 06:00 | precompute-daily | 구독자 전원의 일일 saju 점수 사전 계산, Redis 저장 |
| 06:30 | (포함) | 인기 심볼 차트 분석 prefetch |
| 07:00 | morning-push | Telegram/웹 푸시 발송 |
| 매시 | chart-refresh | 활성 심볼 차트 점수 갱신 |
| 주 1회 | lucky-calendar-rebuild | 7일 럭키 캘린더 계산 |

## 8. 위험과 대응

| 위험 | 대응 |
|------|------|
| Railway 다운 → 봇+웹 둘 다 사망 | Week 5 이후 health check + Supabase에 최근 24h 추천 스냅샷 저장해 정적 fallback |
| yfinance rate limit | 5분 캐시 + 인기 심볼 prefetch |
| KIS API 지연 | Week 3 전에 신청, 지연 시 Week 4까지 yfinance 전용으로 런칭 |
| FastAPI 인증 토큰 누수 | Vercel/Railway env에만, 코드 커밋 금지. `.env.example`만 |
| lunar_python 정확도 의심 | Week 2 내에 손계산 10개로 검증 (갑자~계해 샘플) |

## 9. 프로토타입 정리 숙제

- `saju_engine.py:596` 하드코딩 `Solar.fromYmd(2026, 4, 15)` 제거
- `ASSET_WEIGHTS["scalp"]` 휴면 (코인/선물 제외 결정) — 주석으로 표시, 삭제 보류

## 10. 범위 밖 (P2 이후)

- TS 포팅 (부하 또는 UX 실측 이슈 전엔 검토 안 함)
- SQLite 만세력 프리컴퓨트 (Redis hit ratio 데이터 확보 후 재평가)
- 선물/코인 자산군
- RN 모바일 앱
- 다국어 (영어 등)

## 11. 성공 기준 (엔진 전략 관점)

- Week 8까지: 봇과 웹 모두에서 동일 입력 → 동일 추천 카드 (단일 소스 원칙 검증)
- Week 12까지: p95 `/recommend` 응답 < 1.5s (Redis warm 상태)
- 전 기간: 엔진 로직 관련 버그 수정이 1개 PR로 끝나야 함 (봇+웹 동시 반영)
