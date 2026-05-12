"""감정서 생성기 — Anthropic Claude API 호출 + JSON 파싱."""
from __future__ import annotations

import json
import re
from typing import Any

import anthropic

from sajucandle.saju.report_prompt import build_messages

MODEL_STANDARD = "claude-sonnet-4-6"
MODEL_PREMIUM = "claude-opus-4-6"
MAX_TOKENS = 4096
TIMEOUT = 60.0
MAX_RETRIES = 2


def parse_sections(text: str) -> list[dict[str, Any]]:
    """Claude 응답 텍스트에서 7섹션 JSON을 추출한다."""
    code_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if code_match:
        text = code_match.group(1)

    brace_start = text.find("{")
    brace_end = text.rfind("}") + 1
    if brace_start < 0 or brace_end <= brace_start:
        raise ValueError("JSON 객체를 찾을 수 없습니다")

    try:
        parsed = json.loads(text[brace_start:brace_end])
    except json.JSONDecodeError as e:
        raise ValueError(f"JSON 파싱 실패: {e}") from e

    if "sections" not in parsed:
        raise ValueError("'sections' 키가 없습니다")

    sections = parsed["sections"]
    if len(sections) != 7:
        raise ValueError(f"섹션 수가 7개가 아닙니다: {len(sections)}")

    required_keys = {"id", "title", "content", "highlight"}
    for i, sec in enumerate(sections):
        missing = required_keys - set(sec.keys())
        if missing:
            raise ValueError(f"섹션 {i+1}에 필수 키 누락: {missing}")

    return sections


async def generate_report(
    context: dict[str, Any],
    tier: str = "standard",
) -> list[dict[str, Any]]:
    """Claude API를 호출하여 7섹션 감정서를 생성한다."""
    model = MODEL_STANDARD if tier == "standard" else MODEL_PREMIUM
    messages = build_messages(context)

    client = anthropic.AsyncAnthropic()

    last_error: Exception | None = None
    for attempt in range(MAX_RETRIES):
        response = await client.messages.create(
            model=model,
            max_tokens=MAX_TOKENS,
            system=messages[0]["content"],
            messages=[{"role": "user", "content": messages[1]["content"]}],
            timeout=TIMEOUT,
        )

        response_text = response.content[0].text
        try:
            return parse_sections(response_text)
        except ValueError as e:
            last_error = e
            continue

    raise ValueError(f"감정서 파싱 실패 ({MAX_RETRIES}회 시도): {last_error}")
