# 사주캔들 배포 구현 플랜

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 사주캔들을 Railway(백엔드) + Vercel(프론트엔드)에 프로덕션 배포하여 실제 사용자가 접속 가능하게 만든다.

**Architecture:** 기존 Dockerfile을 Railway 호환으로 수정 ($PORT 동적 바인딩), CORS를 환경변수 기반으로 전환, .dockerignore에 frontend 추가. Railway에 백엔드 배포 후 Vercel에 프론트엔드 배포. GitHub push 자동배포.

**Tech Stack:** Docker, Railway, Vercel, FastAPI, Next.js 16

**Spec:** `docs/superpowers/specs/2026-05-14-deployment-design.md`

---

## 파일 구조

| 파일 | 역할 | 상태 |
|------|------|------|
| `Dockerfile` | Railway 배포용 컨테이너 이미지 | 수정 (PORT 동적화) |
| `.dockerignore` | Docker 빌드 제외 파일 | 수정 (frontend/ 추가) |
| `src/sajucandle/api/main.py:241-247` | CORS middleware 설정 | 수정 (환경변수 기반) |
| `tests/test_cors.py` | CORS 설정 테스트 | 신규 |

---

### Task 1: Dockerfile Railway 호환 수정

**Files:**
- Modify: `Dockerfile`
- Modify: `.dockerignore`

현재 Dockerfile은 포트 8000 하드코딩. Railway는 `$PORT` 환경변수를 주입하므로 이를 사용하도록 변경해야 한다.

- [ ] **Step 1: Dockerfile 수정 — $PORT 동적 바인딩**

`Dockerfile` 전체를 다음으로 교체:

```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml ./
COPY src/ ./src/
RUN pip install --no-cache-dir .

COPY data/tickers/ ./data/tickers/
COPY data/manseryeok/ ./data/manseryeok/
COPY data/solar_terms/ ./data/solar_terms/

ENV PYTHONUNBUFFERED=1
ENV PORT=8000

CMD uvicorn sajucandle.api.main:app --host 0.0.0.0 --port $PORT
```

변경점:
- `pip install -e .` → `pip install .` (프로덕션에서 editable 불필요)
- `CMD` JSON 형식 → shell 형식 (`$PORT` 환경변수 치환 필요)
- `ENV PORT=8000` 기본값 (Railway 미사용 시 폴백)

- [ ] **Step 2: .dockerignore에 frontend/ 추가**

`.dockerignore` 끝에 추가:

```
frontend/
data/prices/
data/signals/
*.bsp
```

- [ ] **Step 3: Docker 빌드 테스트**

Run: `docker build -t sajucandle-test .`
Expected: 빌드 성공, 이미지 생성

Run: `docker run --rm -e PORT=8001 -p 8001:8001 sajucandle-test &`
Run: `curl http://localhost:8001/health`
Expected: `{"status":"ok"}` 응답

(Docker 미설치 시 이 검증은 건너뛰고 Railway 배포로 확인)

- [ ] **Step 4: Commit**

```bash
git add Dockerfile .dockerignore
git commit -m "chore(deploy): Dockerfile Railway 호환 수정 + dockerignore 보강"
```

---

### Task 2: CORS 환경변수 기반 전환

**Files:**
- Modify: `src/sajucandle/api/main.py:241-247`
- Create: `tests/test_cors.py`

현재 CORS는 `allow_origins=["*"]`로 모든 origin을 허용한다. 프로덕션에서는 Vercel 도메인만 허용하되, 로컬 개발도 지원해야 한다.

- [ ] **Step 1: 테스트 작성**

`tests/test_cors.py` 생성:

```python
"""CORS 설정 테스트."""
from __future__ import annotations

import os
from unittest.mock import patch

import pytest


def test_cors_includes_localhost_by_default():
    """FRONTEND_URL 미설정 시 localhost:3000 포함."""
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("FRONTEND_URL", None)
        # 모듈 재로드하여 origins 재계산
        from sajucandle.api import main as api_main
        import importlib
        importlib.reload(api_main)

        # CORSMiddleware의 allow_origins 확인
        for mw in api_main.app.user_middleware:
            if mw.cls.__name__ == "CORSMiddleware":
                origins = mw.kwargs.get("allow_origins", [])
                assert "http://localhost:3000" in origins
                return
        pytest.fail("CORSMiddleware not found")


def test_cors_includes_frontend_url():
    """FRONTEND_URL 설정 시 해당 origin 포함."""
    with patch.dict(os.environ, {"FRONTEND_URL": "https://myapp.vercel.app"}):
        from sajucandle.api import main as api_main
        import importlib
        importlib.reload(api_main)

        for mw in api_main.app.user_middleware:
            if mw.cls.__name__ == "CORSMiddleware":
                origins = mw.kwargs.get("allow_origins", [])
                assert "https://myapp.vercel.app" in origins
                assert "http://localhost:3000" in origins
                return
        pytest.fail("CORSMiddleware not found")
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `PYTHONPATH=src ./.venv/Scripts/python.exe -m pytest tests/test_cors.py -v`
Expected: FAIL (현재 `allow_origins=["*"]`이므로 localhost가 명시적으로 포함되지 않음)

- [ ] **Step 3: CORS 설정 수정**

`src/sajucandle/api/main.py`에서 현재 CORS 블록:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

다음으로 교체:

```python
def _build_cors_origins() -> list[str]:
    """환경변수 기반 CORS origin 목록 구성."""
    origins = [
        "http://localhost:3000",
        "http://localhost:3001",
    ]
    frontend_url = os.environ.get("FRONTEND_URL")
    if frontend_url:
        origins.append(frontend_url.rstrip("/"))
    return origins

app.add_middleware(
    CORSMiddleware,
    allow_origins=_build_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

파일 상단에 `import os`가 없으면 추가한다.

- [ ] **Step 4: 테스트 통과 확인**

Run: `PYTHONPATH=src ./.venv/Scripts/python.exe -m pytest tests/test_cors.py -v`
Expected: 2 passed

- [ ] **Step 5: 기존 테스트 회귀 확인**

Run: `PYTHONPATH=src ./.venv/Scripts/python.exe -m pytest tests/ -v --ignore=tests/e2e_report.py --ignore=tests/smoke_test_oos_validation.py --ignore=tests/smoke_test_regime_engine.py --ignore=tests/smoke_test_coin_v2.py --ignore=tests/smoke_test_nulltest_v2.py --ignore=tests/smoke_test_signal_engine.py -x`
Expected: 전체 PASS (기존 테스트 깨지지 않음)

- [ ] **Step 6: Commit**

```bash
git add src/sajucandle/api/main.py tests/test_cors.py
git commit -m "feat(api): CORS를 환경변수 기반으로 전환 (FRONTEND_URL)"
```

---

### Task 3: Railway 배포

**Files:** 없음 (플랫폼 설정)

Railway 대시보드에서 프로젝트를 생성하고 GitHub 리포를 연결한다.

- [ ] **Step 1: 코드 푸시**

```bash
git push origin main
```

- [ ] **Step 2: Railway 프로젝트 생성**

1. https://railway.app 접속 → New Project
2. "Deploy from GitHub repo" 선택
3. `zgler/sajucandle` 리포지토리 연결
4. Railway가 Dockerfile을 자동 감지

- [ ] **Step 3: 환경변수 설정**

Railway 대시보드 → Variables 탭:

| 변수 | 값 |
|------|-----|
| `ANTHROPIC_API_KEY` | (사용자의 API 키) |
| `FRONTEND_URL` | (Vercel 배포 후 설정 — Task 4 완료 후) |

- [ ] **Step 4: 배포 확인**

Railway가 자동 빌드 & 배포. 완료 후:

1. Railway 대시보드에서 public URL 확인 (예: `https://sajucandle-production.up.railway.app`)
2. 브라우저에서 `https://<railway-url>/health` 접속
3. Expected: `{"status":"ok"}`

- [ ] **Step 5: API 엔드포인트 테스트**

```bash
curl -X POST https://<railway-url>/api/saju/profile \
  -H "Content-Type: application/json" \
  -d '{"year":1996,"month":1,"day":23,"hour":3,"gender":"M"}'
```

Expected: 프로필 JSON 응답 (pillars, investor_type 등)

---

### Task 4: Vercel 배포

**Files:** 없음 (플랫폼 설정)

Vercel 대시보드에서 프로젝트를 생성하고 GitHub 리포를 연결한다.

- [ ] **Step 1: Vercel 프로젝트 생성**

1. https://vercel.com 접속 → New Project
2. `zgler/sajucandle` 리포지토리 import
3. **Root Directory**: `frontend` 로 설정 (Configure Project 단계에서)
4. **Framework Preset**: Next.js (자동 감지)

- [ ] **Step 2: 환경변수 설정**

Vercel 대시보드 → Settings → Environment Variables:

| 변수 | 값 | Environment |
|------|-----|-------------|
| `NEXT_PUBLIC_API_URL` | `https://<railway-url>` (Task 3에서 확인한 URL) | Production, Preview, Development |

- [ ] **Step 3: 배포 트리거**

Vercel이 자동으로 `next build`를 실행하여 배포.

- [ ] **Step 4: 배포 확인**

1. Vercel 대시보드에서 URL 확인 (예: `https://sajucandle.vercel.app`)
2. 브라우저에서 접속 → 온보딩 폼 표시 확인

- [ ] **Step 5: Railway에 FRONTEND_URL 추가**

Task 3에서 보류했던 환경변수 설정:

Railway 대시보드 → Variables:

| 변수 | 값 |
|------|-----|
| `FRONTEND_URL` | `https://sajucandle.vercel.app` (또는 실제 Vercel URL) |

Railway가 자동 재배포.

---

### Task 5: E2E 프로덕션 검증

**Files:** 없음 (수동 검증)

프로덕션 환경에서 전체 사용자 플로우를 검증한다.

- [ ] **Step 1: 온보딩 플로우**

1. Vercel URL 접속
2. 출생연도(2010→1920 내림차순 확인), 월, 일, 시간, 성별 입력
3. "내 투자 체질 알아보기" 클릭
4. Expected: 프로필 카드 표시 (투자 유형, 사주 4주, 오행 분포)

- [ ] **Step 2: 일일 운세**

1. "오늘" 탭 클릭
2. Expected: 오늘의 매매 기운 (판단운/실행운/인내운 점수, 코칭 메시지)

- [ ] **Step 3: 감정서 생성**

1. 프로필 페이지 → 감정서 진입
2. 로딩 애니메이션 표시 (2~3분 소요)
3. Expected: 7섹션 감정서 렌더링
   - 섹션 1-2: 내용 표시 (unlocked)
   - 섹션 3-7: 잠금 상태 (封 봉인 스탬프, 블러)
   - 페이월 CTA: "990원으로 봉인 해제"

- [ ] **Step 4: 검증 완료 기록**

모든 플로우가 정상이면 완료. 문제 발견 시 기록하고 수정.
