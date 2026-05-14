# 사주캔들 배포 설계 스펙

> 작성일: 2026-05-14
> 상태: Approved

## 1. 목표

사주캔들 웹앱을 프로덕션에 배포한다. 백엔드(FastAPI)는 Railway, 프론트엔드(Next.js)는 Vercel에 배포하여 실제 사용자가 접속할 수 있는 상태를 만든다.

## 2. 아키텍처

```
사용자 브라우저
    │
    ├─→ Vercel (프론트엔드)
    │     *.vercel.app
    │     Next.js 16, Static Export
    │     환경변수: NEXT_PUBLIC_API_URL=<Railway URL>
    │
    └─→ Railway (백엔드)
          *.up.railway.app
          FastAPI + uvicorn
          환경변수: ANTHROPIC_API_KEY
          Dockerfile 기반 배포
```

### 배포 흐름

1. GitHub `main` 브랜치에 push
2. Railway: Dockerfile 감지 → 빌드 → 배포 (백엔드)
3. Vercel: `frontend/` 디렉토리 감지 → `next build` → 배포 (프론트엔드)
4. 둘 다 자동 배포 (별도 CI/CD 불필요)

## 3. 백엔드 (Railway)

### 3.1 Dockerfile

프로젝트 루트에 `Dockerfile` 생성:
- 베이스: `python:3.12-slim`
- 의존성: `pip install .` (pyproject.toml 기반)
- 실행: `uvicorn sajucandle.api.main:app --host 0.0.0.0 --port $PORT`
- Railway는 `$PORT` 환경변수를 자동 주입한다

### 3.2 환경변수

| 변수 | 값 | 설명 |
|------|-----|------|
| `ANTHROPIC_API_KEY` | `sk-ant-...` | Claude API 키. Railway 대시보드에서 설정 |
| `PORT` | (Railway 자동) | Railway가 자동 주입 |

### 3.3 CORS

현재 `api/main.py`의 CORS 설정에 Vercel 도메인을 추가해야 한다:
- `https://*.vercel.app` 패턴 허용
- 또는 환경변수 `ALLOWED_ORIGINS`로 동적 설정

구현 방식: 환경변수 `FRONTEND_URL`을 읽어서 CORS origins에 추가. 미설정 시 `http://localhost:3000` 폴백 (로컬 개발).

### 3.4 헬스체크

기존 `GET /health` 엔드포인트를 Railway 헬스체크로 사용.

## 4. 프론트엔드 (Vercel)

### 4.1 설정

- **Root Directory**: `frontend/`
- **Framework Preset**: Next.js (자동 감지)
- **Build Command**: `next build` (기본)
- **Output Directory**: `.next` (기본)

### 4.2 환경변수

| 변수 | 값 | 설명 |
|------|-----|------|
| `NEXT_PUBLIC_API_URL` | `https://<app>.up.railway.app` | Railway 백엔드 URL |

### 4.3 API 호출

현재 `frontend/src/lib/api.ts`에서 `NEXT_PUBLIC_API_URL` 환경변수를 이미 사용 중:
```typescript
const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8001";
```
변경 불필요.

## 5. 필요한 코드 변경

### 5.1 Dockerfile 생성

프로젝트 루트에 `Dockerfile` 신규 생성.

### 5.2 CORS 동적 설정

`src/sajucandle/api/main.py`의 CORS middleware를 수정:
- 환경변수 `FRONTEND_URL`에서 허용 origin 읽기
- 미설정 시 `http://localhost:3000` 폴백
- `localhost` 개발용 origin도 항상 포함

### 5.3 .dockerignore 생성

불필요한 파일 제외: `.venv/`, `frontend/node_modules/`, `data/prices/`, `.bsp` 파일 등.

### 5.4 railway.toml (선택)

Railway 배포 설정 파일. 헬스체크 경로, 재시작 정책 등.

## 6. 배포 순서

1. Dockerfile + .dockerignore + CORS 수정 → 커밋 & 푸시
2. Railway 프로젝트 생성 → GitHub 연동 → 환경변수 설정 → 배포
3. Railway 배포 확인 (`/health` 엔드포인트)
4. Vercel 프로젝트 생성 → GitHub 연동 → Root Directory `frontend/` → 환경변수 설정 → 배포
5. Vercel에서 프론트엔드 접속 확인
6. E2E 검증: 온보딩 → 프로필 → 일일 운세 → 감정서 생성

## 7. 스코프 외

- 커스텀 도메인 연결 (추후 도메인 구매 시)
- SSL 인증서 (Vercel/Railway 모두 자동 제공)
- CI/CD 파이프라인 (GitHub push 자동배포로 충분)
- 모니터링/알림 (Railway 내장 로그로 시작)
- 서버 DB (현재 localStorage 유지)
- CDN/캐싱 최적화
