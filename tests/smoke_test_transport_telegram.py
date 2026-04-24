"""Telegram sender 검증 — httpx.MockTransport 사용."""

from __future__ import annotations

import sys
from unittest.mock import patch

sys.stdout.reconfigure(encoding="utf-8")

import httpx
from pydantic import SecretStr

from sajucandle.transport import telegram as tg_mod
from sajucandle.transport.config import TransportConfig


def _cfg() -> TransportConfig:
    return TransportConfig(
        enabled=True,
        telegram_bot_token=SecretStr("abc:def"),
        telegram_admin_chat_id="123",
        telegram_api_base="https://api.telegram.org",
    )


def _run_with_handler(text: str, handler) -> bool:
    """httpx.Client를 MockTransport 주입 버전으로 monkey-patch 후 send_message 호출."""
    transport = httpx.MockTransport(handler)
    real_client = httpx.Client

    def _mock_client(*args, **kwargs):
        kwargs["transport"] = transport
        return real_client(*args, **kwargs)

    with patch.object(tg_mod.httpx, "Client", _mock_client):
        # retry 대기시간 제거 (테스트 고속화)
        with patch.object(tg_mod.time, "sleep", lambda _: None):
            return tg_mod.send_message(text, cfg=_cfg())


# ── Case 1: 200 OK ────────────────────────────────────────────────────────
def h_ok(req: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json={"ok": True})


# ── Case 2: 429 → 200 (retry) ─────────────────────────────────────────────
_retry_state = {"count": 0}


def h_retry(req: httpx.Request) -> httpx.Response:
    _retry_state["count"] += 1
    if _retry_state["count"] == 1:
        return httpx.Response(429, json={"ok": False, "description": "Too Many Requests"})
    return httpx.Response(200, json={"ok": True})


# ── Case 3: 403 (no retry) ───────────────────────────────────────────────
_403_state = {"count": 0}


def h_403(req: httpx.Request) -> httpx.Response:
    _403_state["count"] += 1
    return httpx.Response(403, json={"ok": False, "description": "Forbidden"})


# ── Case 4: 4096 초과 → chunks ────────────────────────────────────────────
_chunk_state = {"count": 0}


def h_chunks(req: httpx.Request) -> httpx.Response:
    _chunk_state["count"] += 1
    return httpx.Response(200, json={"ok": True})


# ── 실행 ──────────────────────────────────────────────────────────────────
results = []

print("Case 1: 200 OK")
r = _run_with_handler("hello", h_ok)
print(f"  result={r}")
results.append(("200 OK", r, True))

print("Case 2: 429 → 200 (retry)")
_retry_state["count"] = 0
r = _run_with_handler("hello", h_retry)
print(f"  result={r}, attempts={_retry_state['count']}")
results.append(("429 retry", r, True))
assert _retry_state["count"] == 2, f"retry 1회 후 성공 기대, 실제 {_retry_state['count']}"

print("Case 3: 403 (no retry)")
_403_state["count"] = 0
r = _run_with_handler("hello", h_403)
print(f"  result={r}, attempts={_403_state['count']}")
results.append(("403 fail", r, False))
assert _403_state["count"] == 1, f"retry 없어야 함, 실제 {_403_state['count']}"

print("Case 4: 4096 초과 → chunk 분할")
long_text = "\n".join([f"line{i}" for i in range(1500)])
_chunk_state["count"] = 0
r = _run_with_handler(long_text, h_chunks)
print(f"  result={r}, post_count={_chunk_state['count']}")
results.append(("chunk split", r, True))
assert _chunk_state["count"] >= 2, f"chunk 분할 실패, 실제 {_chunk_state['count']}"

failed = sum(1 for _, actual, expected in results if actual != expected)
if failed:
    print(f"\n❌ {failed}/{len(results)} FAIL")
    sys.exit(1)
print(f"\n✓ {len(results)}/{len(results)} PASS")
