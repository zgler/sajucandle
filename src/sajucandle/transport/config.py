"""Transport 계층 설정 — .env → TransportConfig 매핑."""

from __future__ import annotations

import os

from pydantic import BaseModel, SecretStr


class TransportConfig(BaseModel):
    enabled: bool = False
    telegram_bot_token: SecretStr | None = None
    telegram_admin_chat_id: str | None = None
    telegram_api_base: str = "https://api.telegram.org"

    @classmethod
    def from_env(cls) -> TransportConfig:
        raw_token = os.getenv("TELEGRAM_BOT_TOKEN")
        return cls(
            enabled=os.getenv("TRANSPORT_ENABLED", "false").lower() == "true",
            telegram_bot_token=SecretStr(raw_token) if raw_token else None,
            telegram_admin_chat_id=os.getenv("TELEGRAM_ADMIN_CHAT_ID") or None,
            telegram_api_base=os.getenv(
                "TELEGRAM_API_BASE", "https://api.telegram.org"
            ),
        )

    def is_telegram_ready(self) -> bool:
        return (
            self.enabled
            and self.telegram_bot_token is not None
            and bool(self.telegram_admin_chat_id)
        )
