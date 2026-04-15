# 사주캔들 (SajuCandle)

사주 일진(日辰) 점수와 기술적 차트 분석을 결합해 개인별 매매 진입 시점을 추천하는 서비스.
현재는 MVP 초기 단계 — Telegram 봇 + FastAPI 백엔드 + Redis 캐시.

> **엔터테인먼트 목적. 투자 추천 아님.**

---

## 아키텍처

```
[Telegram 사용자]
      │ /start 1990-03-15 14:00
      ▼
┌─────────────────────────┐
│  Railway: sajucandle-bot │ (worker — python -m sajucandle.bot)
│  python-telegram-bot 21  │
└──────────┬──────────────┘
           │ 직접 엔진 호출 (현재)
           │ 추후 HTTP로 전환 예정
           ▼
┌─────────────────────────┐     ┌────────────────────────┐
│  SajuEngine + Cache      │────▶│  Upstash Redis         │
│  (lunar_python)          │     │  bazi:YYYYMMDDHH       │
└─────────────────────────┘     └────────────────────────┘
           ▲
           │
┌─────────────────────────┐
│  Railway: sajucandle-api │ (web — uvicorn sajucandle.api:app)
│  FastAPI                 │
│  POST /v1/bazi           │
│  GET  /health            │
└─────────────────────────┘
```

두 Railway 서비스는 같은 GitHub repo + 같은 Dockerfile + 같은 `REDIS_URL`을 공유한다. `startCommand`만 서비스별로 오버라이드.

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
(26 tests: cache 4 / cached_engine 4 / format 4 / handlers 8 / api 6)

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
├── bot.py              # Telegram 봇 엔트리
├── handlers.py         # /start 핸들러 + 인자 파싱
├── format.py           # 명식 카드 텍스트 렌더러
├── saju_engine.py      # 명리 계산 엔진 (lunar_python)
├── cache.py            # Redis 캐시 래퍼
├── cached_engine.py    # SajuEngine + BaziCache
├── api.py              # FastAPI 앱 + 엔드포인트
└── models.py           # Pydantic 요청/응답 모델

tests/
├── test_cache.py
├── test_cached_engine.py
├── test_format.py
├── test_handlers.py
└── test_api.py

docs/superpowers/
├── specs/              # 설계 문서
└── plans/              # 주차별 구현 플랜
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
