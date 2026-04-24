# Week 10 Phase 2 설계 — 게이팅 강화 + /guide + 에러 개선

- 날짜: 2026-04-19
- 대상: Week 10 Phase 2 (Phase 1 관측성 완료 후)
- 상태: Draft (자율 판단)

## 1. 목적

데이터 쌓이기 전이라도 **근거 있는 품질 개선**:
1. 구조적으로 매수 시그널이 안 나와야 할 상태(하락추세/이탈)에서 "진입" 차단 — 승률 기대치 보호
2. 사용자가 카드 해석법을 알아야 "정보 제공" 가치 실현 → `/guide`
3. 에러 메시지를 원인별로 분리해 복구 가이드 제공

## 2. 포함 / 범위 밖

### 포함
1. `signal_service._grade_signal`에 "진입" 차단 조건 추가
2. `/guide` 봇 명령 + 카드 (등급 4종, 구조 5종, 정렬 해석, 세팅 블록 읽는 법)
3. `/help`에 `/guide` 노출, admin에게만 `/stats` 추가 안내
4. 에러 메시지 원인별 분리 (타임아웃/DB/네트워크/서버)

### 범위 밖
- 카드 세밀 조정 (이모지/정렬) — 실사용 피드백 필요
- 등급 임계값 재조정 — Week 11 백테스트
- Rate limiting — 사용자 수 증가 후

## 3. 설계 결정

| # | 주제 | 결정 |
|---|------|------|
| 1 | 진입 게이팅 | `DOWNTREND` + `BREAKDOWN` 구조에서는 점수≥60여도 "관망"으로 다운그레이드 |
| 2 | 강진입 게이팅 | 기존 그대로 (score≥75 + aligned + UPTREND/BREAKOUT) |
| 3 | `/guide` 텍스트 | 하드코딩 상수, 다국어 없음 (YAGNI) |
| 4 | `/guide` 길이 | 텔레그램 메시지 한 통 (~15줄) |
| 5 | 에러 분리 세분화 | timeout / transport / 500 / 502 / 503 / 기타 |

## 4. 아키텍처

### 4.1 `signal_service._grade_signal` 수정

```python
def _grade_signal(score: int, analysis: AnalysisResult) -> str:
    state = analysis.structure.state
    aligned = analysis.alignment.aligned

    # 강진입: 기존 (변경 없음)
    if (score >= 75 and aligned
            and state in (MarketStructure.UPTREND, MarketStructure.BREAKOUT)):
        return "강진입"

    # Week 10 Phase 2: 하락/이탈 구조에서 진입 차단
    if state in (MarketStructure.DOWNTREND, MarketStructure.BREAKDOWN):
        # 점수 높아도 구조 역행 → 최소 관망
        if score >= 60:
            return "관망"

    # 일반 진입
    if score >= 60:
        return "진입"
    if score >= 40:
        return "관망"
    return "회피"
```

**효과:**
- BTC 하락추세 중에도 사주+RSI+거래량으로 점수 65 나올 수 있음 → Week 9까진 "진입" → 이젠 "관망"
- 구조가 뒷받침하는 장에서만 "진입" 허용

### 4.2 `/guide` 명령

`handlers.py`에 `guide_command` 추가. 응답 문자열 상수로:

```
📖 사주캔들 가이드
─────────────

[등급]
🔥 강진입: 점수 75+ AND 3TF 정렬 AND 상승추세
👍 진입: 점수 60+ AND 우호 구조
😐 관망: 점수 40-59 또는 하락추세
🛑 회피: 점수 40 미만

[구조]
상승추세 (HH-HL): 지속 매수 유리
하락추세 (LH-LL): 매수 불리, 관망
횡보 (박스): 레벨 반응 대기
상승 돌파: 추세 전환 가능성
하락 이탈: 지지선 붕괴, 약세

[정렬 (1d/4h/1h)]
↑↑↑ 강정렬: 상위 TF가 일관된 방향
↑→↓ 혼조: TF 간 불일치, 진입 리스크↑

[세팅 블록 (진입 등급만)]
진입 = 현재가
손절 = 리스크 시작선
익절1/2 = 부분 익절 가격
R:R = 손실 1 대비 기대 수익
리스크 = 진입~손절 거리 %

계좌의 1~2%만 리스크로 배팅 권장.

※ 정보 제공 목적. 투자 판단과 손실 책임은 본인에게 있습니다.
```

### 4.3 `/help` 업데이트

기존 목록 마지막에 추가:
- `/guide — 카드 해석법`

관리자 전용 `/stats`는 `/help`에 노출 안 함 (일반 사용자 혼란 방지).

### 4.4 에러 메시지 분리

기존 `signal_command`의 에러 분기 개선:

```python
except httpx.TimeoutException:
    await update.message.reply_text(
        "⏱️ 서버 응답 지연 (타임아웃). 잠시 후 다시 시도하세요."
    )
except httpx.TransportError:
    await update.message.reply_text(
        "🔌 네트워크 연결 실패. 인터넷 상태 확인 후 재시도."
    )
except ApiError as e:
    if e.status == 502:
        await update.message.reply_text(
            "📉 시장 데이터 소스 일시 불가 (Binance/yfinance). 1~2분 후 재시도."
        )
    elif e.status == 503:
        await update.message.reply_text(
            "🛠️ 일시 점검 중. 잠시 후 다시 시도하세요."
        )
    elif e.status == 400 and "unsupported" in (e.detail or "").lower():
        # 기존 로직 유지
        ...
    elif e.status >= 500:
        await update.message.reply_text(
            f"⚠️ 서버 오류 ({e.status}). 지속되면 관리자에게 문의."
        )
    else:
        await update.message.reply_text(f"요청 오류 ({e.status}).")
```

동일 패턴을 `/score`, `/watch`, `/unwatch`, `/watchlist` 명령에도 일관 적용.

## 5. 테스트 전략

| 파일 | 커버리지 |
|------|----------|
| `tests/test_signal_service.py` (수정) | DOWNTREND + score 65 → "관망", BREAKDOWN + score 70 → "관망", UPTREND + score 65 → "진입" (기존 통과) |
| `tests/test_handlers.py` (수정) | /guide 명령 카드 내용 (등급/구조 문구 포함), 타임아웃 메시지 |

## 6. 배포

1. 코드 push → Railway 자동 재배포.
2. DB 변경 없음.
3. 스모크: `/guide`, `/signal` 에러 상황 시뮬 어려우니 `/guide` + `/help`만 확인.

## 7. 완료 기준

- [ ] DOWNTREND/BREAKDOWN 진입 차단 동작 (단위 테스트)
- [ ] `/guide` 명령 카드 응답
- [ ] `/help`에 `/guide` 추가
- [ ] 에러 메시지 원인별 분리 (최소 signal_command)
- [ ] 기존 Week 1-10 Phase 1 테스트 회귀 0
