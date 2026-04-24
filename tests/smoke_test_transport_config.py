"""Transport config env 로드 검증."""

from __future__ import annotations

import os
import sys

sys.stdout.reconfigure(encoding="utf-8")

from sajucandle.transport.config import TransportConfig


_KEYS = (
    "TRANSPORT_ENABLED",
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_ADMIN_CHAT_ID",
    "TELEGRAM_API_BASE",
)


def _set_env(**kwargs: str | None) -> None:
    for k in _KEYS:
        os.environ.pop(k, None)
    for k, v in kwargs.items():
        if v is not None:
            os.environ[k] = v


cases = [
    (
        "전부 설정",
        dict(
            TRANSPORT_ENABLED="true",
            TELEGRAM_BOT_TOKEN="abc:def",
            TELEGRAM_ADMIN_CHAT_ID="123",
        ),
        True,
    ),
    (
        "disabled",
        dict(
            TRANSPORT_ENABLED="false",
            TELEGRAM_BOT_TOKEN="abc:def",
            TELEGRAM_ADMIN_CHAT_ID="123",
        ),
        False,
    ),
    (
        "token 누락",
        dict(TRANSPORT_ENABLED="true", TELEGRAM_ADMIN_CHAT_ID="123"),
        False,
    ),
    (
        "chat_id 누락",
        dict(TRANSPORT_ENABLED="true", TELEGRAM_BOT_TOKEN="abc:def"),
        False,
    ),
]

failed = 0
for name, env, expected in cases:
    _set_env(**env)
    cfg = TransportConfig.from_env()
    actual = cfg.is_telegram_ready()
    mark = "✓" if actual == expected else "✗"
    print(f"  {mark} {name:12s} ready={actual} (expected {expected})")
    if actual != expected:
        failed += 1

if failed:
    print(f"\n❌ {failed}/{len(cases)} FAIL")
    sys.exit(1)
print(f"\n✓ {len(cases)}/{len(cases)} PASS")
