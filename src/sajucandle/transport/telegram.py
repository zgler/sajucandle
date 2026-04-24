"""Telegram Bot API를 통한 관리자 메시지 전송.

사용:
    from sajucandle.transport.telegram import send_message
    send_message(render_telegram(report))
"""

from __future__ import annotations

import logging
import time

import httpx

from .config import TransportConfig

log = logging.getLogger(__name__)

MDV2_CHUNK_LIMIT = 4096
_HTTP_TIMEOUT = 10.0
_MAX_RETRIES = 2
_RETRY_STATUS = {408, 429, 500, 502, 503, 504}


def send_message(text: str, cfg: TransportConfig | None = None) -> bool:
    """텔레그램 관리자에게 MDv2 메시지 전송.

    반환: 모든 chunk 전송 성공 시 True, 하나라도 실패/비활성화 시 False.
    """
    cfg = cfg or TransportConfig.from_env()
    if not cfg.is_telegram_ready():
        log.info("Telegram 전송 skip (TRANSPORT_ENABLED=false 또는 creds 누락)")
        return False

    assert cfg.telegram_bot_token is not None
    assert cfg.telegram_admin_chat_id is not None

    chunks = _chunk_text(text, MDV2_CHUNK_LIMIT)
    token = cfg.telegram_bot_token.get_secret_value()
    url = f"{cfg.telegram_api_base}/bot{token}/sendMessage"

    with httpx.Client(timeout=_HTTP_TIMEOUT) as client:
        for i, chunk in enumerate(chunks, 1):
            payload = {
                "chat_id": cfg.telegram_admin_chat_id,
                "text": chunk,
                "parse_mode": "MarkdownV2",
                "disable_web_page_preview": True,
            }
            if not _post_with_retry(client, url, payload, chunk_idx=i, total=len(chunks)):
                return False

    log.info(
        f"Telegram 전송 완료 (chat_id={cfg.telegram_admin_chat_id}, {len(chunks)} chunks)"
    )
    return True


def _chunk_text(text: str, limit: int) -> list[str]:
    """줄 경계 기준으로 텍스트를 limit 이하 chunk로 분할.

    단일 줄이 limit 초과 시 limit 단위로 강제 컷.
    """
    if len(text) <= limit:
        return [text]

    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    for line in text.splitlines(keepends=True):
        if len(line) > limit:
            if current:
                chunks.append("".join(current))
                current, current_len = [], 0
            for i in range(0, len(line), limit):
                chunks.append(line[i : i + limit])
            continue
        if current_len + len(line) > limit:
            chunks.append("".join(current))
            current, current_len = [line], len(line)
        else:
            current.append(line)
            current_len += len(line)
    if current:
        chunks.append("".join(current))
    return chunks


def _post_with_retry(
    client: httpx.Client,
    url: str,
    payload: dict,
    *,
    chunk_idx: int,
    total: int,
) -> bool:
    """2xx 성공, 5xx/408/429 retry, 4xx(기타) 즉시 실패."""
    for attempt in range(_MAX_RETRIES + 1):
        try:
            r = client.post(url, json=payload)
        except httpx.RequestError as e:
            log.warning(
                f"Telegram 연결 오류 (chunk {chunk_idx}/{total}, attempt {attempt + 1}): {e}"
            )
            if attempt >= _MAX_RETRIES:
                log.error(f"Telegram 전송 실패 (chunk {chunk_idx}/{total}): 연결 오류")
                return False
            time.sleep(1.0 * (attempt + 1))
            continue

        if 200 <= r.status_code < 300:
            return True
        if r.status_code in _RETRY_STATUS and attempt < _MAX_RETRIES:
            log.warning(
                f"Telegram {r.status_code} (chunk {chunk_idx}/{total}, attempt {attempt + 1}) — retry"
            )
            time.sleep(1.0 * (attempt + 1))
            continue
        log.error(
            f"Telegram 전송 실패 status={r.status_code} body={r.text[:200]}"
        )
        return False

    return False
