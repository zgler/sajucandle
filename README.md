# 사주캔들 (SajuCandle)

사주 일진(日辰) 점수와 기술적 차트 분석을 결합해 개인별 매매 진입 시점을 추천하는 서비스.
현재는 MVP 초기 단계 — Telegram 봇 + FastAPI 백엔드 + Redis 캐시.

> **엔터테인먼트 목적. 투자 추천 아님.**

---

## 아키텍처

```
[Telegram 사용자]
      │ /start, /score, /me, /forget, /help
      ▼
┌─────────────────────────┐
│  Railway: sajucandle-bot │ (worker — python -m sajucandle.bot)
│  python-telegram-bot 21  │
└──────────┬──────────────┘
           │ httpx AsyncClient
           │ X-SAJUCANDLE-KEY
           ▼
┌─────────────────────────┐     ┌────────────────────────┐
│  Railway: sajucandle-api │────▶│  Upstash Redis         │
│  FastAPI + uvicorn       │     │  bazi:* , score:*      │
│  ScoreService + Engine   │     └────────────────────────┘
└──────────┬──────────────┘
           │ asyncpg Pool
           ▼
┌─────────────────────────┐
│  Supabase PostgreSQL     │
│  users, user_bazi        │
└─────────────────────────┘
```

두 Railway 서비스는 같은 GitHub repo + 같은 Dockerfile + 같은 `REDIS_URL`을 공유한다. 봇은 API에 HTTP로만 접근하고 엔진/DB를 직접 건드리지 않는다.

---

## 로컬 개발

### 설치
```bash
python -m venv .venv
.venv/Scripts/activate  # Windows
# source .venv/bin/activate  # macOS/Linux
pip install -e ".[dev]"
```

### 테스트
```bash
pytest -v
```
Week 3 기준 48 passed + 18 skipped (DB 연결 없을 때). DB 테스트는 `TEST_DATABASE_URL` 환경변수 있을 때만 실행.

### 봇 로컬 실행
```bash
export BOT_TOKEN=...  # BotFather
# export REDIS_URL=rediss://...  # 선택 — 없으면 캐시 비활성
python -m sajucandle.bot
```

### API 로컬 실행
```bash
export SAJUCANDLE_API_KEY=local-dev-key
# export REDIS_URL=rediss://...  # 선택
python -m uvicorn sajucandle.api:app --host 127.0.0.1 --port 8000 --reload
```

테스트 호출:
```bash
curl http://127.0.0.1:8000/health
curl -X POST http://127.0.0.1:8000/v1/bazi \
  -H "Content-Type: application/json" \
  -H "X-SAJUCANDLE-KEY: local-dev-key" \
  -d '{"year":1990,"month":3,"day":15,"hour":14}'
```

자동 생성 OpenAPI 문서: http://127.0.0.1:8000/docs

---

## 배포 (Railway)

### 사전 준비
1. **Upstash Redis 생성** → `REDIS_URL` (rediss://...) 복사
2. **API 키 발급** → `openssl rand -hex 32` 로 `SAJUCANDLE_API_KEY` 생성

### 서비스 1: sajucandle-bot (기존)
- GitHub repo 연결
- Environment:
  - `BOT_TOKEN` = BotFather 토큰
  - `REDIS_URL` = Upstash URL
- Start Command (railway.toml 기본값): `python -m sajucandle.bot`

### 서비스 2: sajucandle-api (신규)
- 같은 GitHub repo에 새 서비스 추가
- Environment:
  - `SAJUCANDLE_API_KEY` = 위에서 생성한 키
  - `REDIS_URL` = Upstash URL (봇과 동일)
- Start Command Override: `python -m uvicorn sajucandle.api:app --host 0.0.0.0 --port $PORT`
- Networking → Generate Domain

### 헬스체크
```bash
curl https://<api-domain>.up.railway.app/health
```

---

## 프로젝트 구조

```
src/sajucandle/
├── bot.py              # Telegram 봇 엔트리 포인트
├── handlers.py         # /start /score /me /forget /help 핸들러
├── api_client.py       # 봇 → API httpx 래퍼 (NotFoundError/ApiError)
├── format.py           # 명식 카드 텍스트 렌더러
├── saju_engine.py      # 명리 계산 엔진 (lunar_python)
├── cache.py            # Redis 캐시 래퍼
├── cached_engine.py    # SajuEngine + BaziCache
├── score_service.py    # 일일 점수 + KST 자정 TTL 캐시
├── api.py              # FastAPI 앱 + 엔드포인트
├── api_main.py         # uvicorn 엔트리 (Railway PORT 읽기)
├── models.py           # Pydantic 요청/응답 모델
├── db.py               # asyncpg Pool 싱글톤
└── repositories.py     # users + user_bazi CRUD

migrations/
└── 001_init.sql        # Supabase 초기 스키마

tests/
├── test_api.py / test_api_users.py / test_api_score.py / test_api_client.py
├── test_cache.py / test_cached_engine.py
├── test_db.py / test_repositories.py
├── test_format.py / test_handlers.py / test_score_service.py
└── conftest.py         # db_pool, db_conn 롤백 fixture

docs/superpowers/
├── specs/              # 설계 문서 (v0.1 기획서, Week 3 design)
└── plans/              # 주차별 구현 플랜
```

---

## Week 3 기능 (사주 점수)

### 봇 커맨드
| Command | 설명 |
|---------|------|
| `/start YYYY-MM-DD HH:MM` | 생년월일시 등록 (upsert) |
| `/score [swing\|scalp\|long]` | 오늘의 일진 점수 카드 |
| `/me` | 등록된 내 정보 |
| `/forget` | 내 정보 삭제 (멱등) |
| `/help` | 명령어 도움말 |

### 신규 API 엔드포인트
- `PUT    /v1/users/{chat_id}` — 프로필 upsert
- `GET    /v1/users/{chat_id}` — 조회 (없으면 404)
- `DELETE /v1/users/{chat_id}` — 삭제 (멱등, 204)
- `GET    /v1/users/{chat_id}/score?date=YYYY-MM-DD&asset=swing` — 일일 4축 + 종합 점수 + 추천 시진

점수 응답은 `score:{chat_id}:{date}:{asset}` 키로 Redis에 캐싱되고, TTL은 **KST 자정까지** (최소 60초)이다.

### DB 초기화
Supabase Studio → SQL Editor → `migrations/001_init.sql` 전체 붙여넣고 Run. `users`, `user_bazi` 두 테이블이 생긴다.

### 신규 환경변수
| 서비스 | 변수 | 예 |
|--------|------|-----|
| sajucandle-api | `DATABASE_URL` | `postgresql://postgres.<ref>:<pw>@aws-X-<region>.pooler.supabase.com:5432/postgres` |
| sajucandle-bot | `SAJUCANDLE_API_BASE_URL` | `https://sajucandle-api-production.up.railway.app` |
| sajucandle-bot | `SAJUCANDLE_API_KEY` | (API 서비스와 동일) |

`DATABASE_URL`이 없으면 API는 `/v1/users/*`, `/v1/users/{chat_id}/score`를 503으로 응답하고 `/health`의 `db` 필드가 `"down"`이 된다. `/v1/bazi`는 DB 없이 동작.

### 테스트 DB
통합 테스트(`test_repositories.py`, `test_api_users.py`, `test_api_score.py`)는 `TEST_DATABASE_URL`이 없으면 스킵된다. 실행 시:
```powershell
$env:TEST_DATABASE_URL = "postgresql://..."
pytest -v
```

---

## 주요 명령 정리

| 목적 | 명령 |
|------|------|
| 설치 | `pip install -e ".[dev]"` |
| 테스트 | `pytest -v` |
| 봇 실행 | `python -m sajucandle.bot` |
| API 실행 | `python -m uvicorn sajucandle.api:app --host 0.0.0.0 --port 8000` |
| 린트 | `ruff check .` |
