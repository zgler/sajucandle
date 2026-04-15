# Week 3 — 사주 점수 API + `/score` 봇 커맨드 설계

**날짜:** 2026-04-16
**범위:** MVP 기획서 v0.1 §3 (4-축 점수), §5 (데이터 모델), §6 (API)
**전제:** Week 1 (봇 + 명식), Week 2 (FastAPI + Redis 캐시) 완료.

---

## 1. 목표

- 사용자가 생년월일시를 한 번만 등록하면 매일 `/score`로 그날 일진 점수를 받는다.
- 점수 계산은 백엔드 `SajuEngine.calc_daily_score()`에 이미 있으므로, 이번 주는 **영속 저장 + API 노출 + 봇 통합**에 집중한다.
- 봇은 엔진/DB를 직접 건드리지 않고 HTTP로만 API를 호출한다 (아키텍처 일원화).

---

## 2. 아키텍처

```
[Telegram]
   │ /start 1990-03-15 14:00
   │ /score
   ▼
┌─────────────────────┐       ┌──────────────────────┐
│ sajucandle-bot       │──────▶│ sajucandle-api        │
│ python-telegram-bot  │ httpx │ FastAPI               │
│ api_client.py        │       │ + SajuEngine          │
└─────────────────────┘       │ + db.py (asyncpg)     │
                              │ + repositories.py     │
                              └──────┬────────┬───────┘
                                     │        │
                                     ▼        ▼
                              ┌──────────┐ ┌──────────┐
                              │ Supabase │ │ Upstash  │
                              │ Postgres │ │ Redis    │
                              └──────────┘ └──────────┘
```

- **봇은 DB에 직접 연결하지 않음.** API가 진입점.
- 기존 `bazi:YYYYMMDDHH` 캐시는 그대로 재사용.
- 신규 `score:{chat_id}:{date}:{asset}` 캐시는 KST 자정 TTL.

---

## 3. 데이터 모델 (Supabase PostgreSQL)

**스택:** asyncpg + 수기 SQL 마이그레이션 (`migrations/001_init.sql`). ORM 없음.

```sql
CREATE TABLE users (
    telegram_chat_id BIGINT PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE user_bazi (
    telegram_chat_id BIGINT PRIMARY KEY
        REFERENCES users(telegram_chat_id) ON DELETE CASCADE,
    birth_year  INT  NOT NULL,
    birth_month INT  NOT NULL,
    birth_day   INT  NOT NULL,
    birth_hour  INT  NOT NULL,
    birth_minute INT NOT NULL DEFAULT 0,
    asset_class_pref TEXT NOT NULL DEFAULT 'swing',  -- 'swing'|'scalp'|'position'
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

이유:
- `user_bazi`를 분리해 두면 나중에 2차 명식(배우자, 다중 프로필) 추가가 쉽다.
- `chat_id`가 PK라 사용자 식별이 깔끔 (Telegram이 unique 보장).
- ON DELETE CASCADE로 `/forget` 한 방에 사용자 데이터 모두 삭제.
- 로그/점수 히스토리 테이블은 이번 주 out of scope (YAGNI).

**마이그레이션 실행:** 사용자가 Supabase Studio SQL editor에서 `migrations/001_init.sql` 실행. 자동 러너는 나중에.

---

## 4. API 엔드포인트 (4개만)

모두 `X-SAJUCANDLE-KEY` 필수. `Content-Type: application/json`.

| Method | Path | 설명 |
|---|---|---|
| `PUT`    | `/v1/users/{chat_id}` | 프로필 upsert (생년월일시 + asset_class) |
| `GET`    | `/v1/users/{chat_id}` | 프로필 조회 |
| `DELETE` | `/v1/users/{chat_id}` | 프로필 삭제 (`/forget`) |
| `GET`    | `/v1/users/{chat_id}/score?date=YYYY-MM-DD&asset=swing` | 그날 점수 |

### 4.1 `PUT /v1/users/{chat_id}`

**Request:**
```json
{
  "birth_year": 1990,
  "birth_month": 3,
  "birth_day": 15,
  "birth_hour": 14,
  "birth_minute": 0,
  "asset_class_pref": "swing"
}
```

**Response 200:** `UserProfileResponse` (같은 필드 + `created_at`, `updated_at`)

이미 존재하는 chat_id면 갱신, 아니면 삽입. 단일 트랜잭션으로 users + user_bazi 동시 upsert.

### 4.2 `GET /v1/users/{chat_id}`

- 200 → `UserProfileResponse`
- 404 → `{"detail": "user not found"}`

### 4.3 `DELETE /v1/users/{chat_id}`

- 204 (없어도 204 — 멱등)

### 4.4 `GET /v1/users/{chat_id}/score`

**Query params:**
- `date` — optional, `YYYY-MM-DD`, 기본값 = KST 오늘
- `asset` — optional, `swing`|`scalp`|`position`, 기본값 = 프로필의 `asset_class_pref`

**Response 200:** `SajuScoreResponse`
```json
{
  "chat_id": 12345,
  "date": "2026-04-16",
  "asset_class": "swing",
  "composite_score": 72,
  "grade": "ENTRY",
  "axes": {
    "wealth":    { "score": 78, "reason": "일간 갑목에 재성 투간" },
    "decision":  { "score": 65, "reason": "..." },
    "volatility":{ "score": 70, "reason": "..." },
    "flow":      { "score": 75, "reason": "..." }
  },
  "best_hours": [
    { "start": "09:30", "end": "11:30", "note": "사시(巳時) 합" },
    { "start": "13:30", "end": "15:30", "note": "미시(未時) 생조" }
  ]
}
```

- 404 — 프로필 없음
- 400 — 잘못된 date/asset
- grade 5단계: `STRONG_ENTRY / ENTRY / NEUTRAL / AVOID / STRONG_AVOID` (기획서 §3)

---

## 5. 봇 커맨드 (5개)

| Command | 동작 |
|---|---|
| `/start YYYY-MM-DD HH:MM` | 인자 있으면 PUT /users/{chat_id}, 없으면 안내 |
| `/score [asset]` | GET /users/{chat_id}/score, 없으면 "먼저 /start 로 등록" |
| `/me` | GET /users/{chat_id}, 저장된 명식 카드 표시 |
| `/forget` | DELETE /users/{chat_id} |
| `/help` | 사용법 |

- 봇은 `api_client.py` 하나로 모든 API 호출.
- 기존 `/start`의 즉석 계산 동작은 유지하되, 결과를 DB에 저장하도록 바꾼다.
- 404/타임아웃/네트워크 에러는 사용자 친화적 메시지로 변환.

---

## 6. 신규 파일

```
src/sajucandle/
├── db.py               # asyncpg Pool 싱글톤, 연결/해제
├── repositories.py     # users / user_bazi CRUD
├── api_client.py       # 봇용 httpx AsyncClient 래퍼
└── api.py              # (수정) 신규 엔드포인트 + DB lifespan

migrations/
└── 001_init.sql        # users + user_bazi 스키마

tests/
├── test_db.py          # asyncpg 연결 & 트랜잭션 롤백 fixture
├── test_repositories.py # CRUD 단위
├── test_api_users.py   # PUT/GET/DELETE /v1/users
├── test_api_score.py   # GET /v1/users/.../score
├── test_api_client.py  # httpx 클라이언트 (respx mock)
└── test_handlers_v2.py # /score, /me, /forget, /help
```

`models.py`에 추가: `UserProfileRequest`, `UserProfileResponse`, `AxisScore`, `HourRecommendation`, `SajuScoreResponse`.

---

## 7. 캐싱

- **기존 `bazi:YYYYMMDDHH`** — 명식 자체는 불변이므로 30일 TTL 그대로.
- **신규 `score:{chat_id}:{date}:{asset}`** — 일진 점수 결과. TTL = KST 자정까지의 초.
  - 이유: 점수는 `date` 바뀌면 재계산. 같은 날 여러 번 `/score` 눌러도 DB + 엔진 재호출 없이 캐시 히트.
  - chat_id를 키에 넣는 이유: 다른 사용자와 섞이지 않게.

---

## 8. 인증 & 시크릿

- API 키: 기존 `SAJUCANDLE_API_KEY` 그대로 (봇도 이 키 하나로 API 호출).
- 봇 env에 추가: `SAJUCANDLE_API_BASE_URL` (`https://sajucandle-api-production.up.railway.app`).
- API env에 추가: `DATABASE_URL` (Supabase → Settings → Database → Connection string → URI 모드).

---

## 9. 에러 처리

- DB 연결 실패 → API `/health`는 DB 핑 포함해서 503. 봇은 `/score`에서 "잠시 후 다시" 메시지.
- Redis 없으면 캐시 우회 (Week 2와 동일 정책).
- 사용자 없음 → 봇: "먼저 `/start 1990-03-15 14:00` 으로 등록하세요".
- 엔진 예외 → 400 + 축약 메시지 (스택트레이스 노출 금지, Week 2와 동일).

---

## 10. 테스트 전략

- **Unit (repositories, db.py):** asyncpg + 트랜잭션 롤백 fixture. Supabase 테스트 DB 또는 로컬 Postgres Docker.
- **API:** httpx AsyncClient + FastAPI TestClient. DB는 fixture로 초기화.
- **봇 핸들러:** python-telegram-bot Update 목 + respx로 API 목.
- **목표 커버리지:** 새로 추가되는 모듈 모두 >=90%, 기존 26개 테스트는 green 유지.

---

## 11. 단계별 구현 순서 (다음 플랜 문서에서 상세화)

1. migrations/001_init.sql + db.py + repositories.py + 테스트
2. Pydantic 모델 추가
3. `/v1/users/*` 엔드포인트 3개
4. `/v1/users/{chat_id}/score` + score 캐시
5. api_client.py
6. 봇 핸들러 리팩터링 (`/start`, `/score`, `/me`, `/forget`, `/help`)
7. Supabase 프로젝트 생성 + DATABASE_URL 주입 + 마이그레이션 실행 (사용자 수동)
8. Railway 배포 + 실제 기기 테스트

---

## 12. Out of Scope (Week 4 이후)

- 점수 이력 테이블, 주간 리포트
- 다중 명식 (배우자/가족)
- 마이그레이션 자동 러너 (Alembic 또는 수기 러너)
- 종목 심볼별 가중치 튜닝
- 결제/Subscription

---

## 변경 이력

- 2026-04-16: 초안. 사용자 Q&A 6건 (B/B/A/B/A/A)로 scope 확정.
