"""tests/test_report_generator.py — Claude API 호출 + 파싱 테스트 (mock)."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch, MagicMock

import pytest
from sajucandle.saju.report_generator import generate_report, parse_sections


VALID_SECTIONS = {
    "sections": [
        {"id": i, "title": f"섹션{i}", "content": f"내용{i}", "highlight": f"핵심{i}"}
        for i in range(1, 8)
    ]
}

VALID_JSON_STR = json.dumps(VALID_SECTIONS, ensure_ascii=False)


class TestParseSections:
    def test_parse_clean_json(self):
        result = parse_sections(VALID_JSON_STR)
        assert len(result) == 7
        assert result[0]["id"] == 1
        assert result[6]["id"] == 7

    def test_parse_json_in_code_block(self):
        text = f"```json\n{VALID_JSON_STR}\n```"
        result = parse_sections(text)
        assert len(result) == 7

    def test_parse_json_with_surrounding_text(self):
        text = f"분석 결과입니다:\n{VALID_JSON_STR}\n\n감사합니다."
        result = parse_sections(text)
        assert len(result) == 7

    def test_parse_invalid_json_raises(self):
        with pytest.raises(ValueError, match="JSON"):
            parse_sections("이것은 JSON이 아닙니다")

    def test_parse_missing_sections_key_raises(self):
        with pytest.raises(ValueError, match="sections"):
            parse_sections('{"data": []}')

    def test_parse_wrong_section_count_raises(self):
        bad = {"sections": [{"id": 1, "title": "a", "content": "b", "highlight": "c"}]}
        with pytest.raises(ValueError, match="7"):
            parse_sections(json.dumps(bad))


SAMPLE_CONTEXT = {
    "birth": {"year": 1985, "month": 3, "day": 15, "hour": 14, "gender": "M"},
    "day_master": {"stem": "癸", "element": "水", "yin_yang": "음"},
}


class TestGenerateReport:
    @pytest.mark.asyncio
    async def test_successful_generation(self):
        mock_message = MagicMock()
        mock_message.content = [MagicMock(text=VALID_JSON_STR)]

        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(return_value=mock_message)

        with patch("sajucandle.saju.report_generator.anthropic.AsyncAnthropic",
                    return_value=mock_client):
            sections = await generate_report(SAMPLE_CONTEXT)

        assert len(sections) == 7
        assert sections[0]["id"] == 1

    @pytest.mark.asyncio
    async def test_retry_on_parse_failure(self):
        """첫 번째 시도 파싱 실패 → 재시도 성공."""
        bad_message = MagicMock()
        bad_message.content = [MagicMock(text="잘못된 응답")]

        good_message = MagicMock()
        good_message.content = [MagicMock(text=VALID_JSON_STR)]

        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(
            side_effect=[bad_message, good_message]
        )

        with patch("sajucandle.saju.report_generator.anthropic.AsyncAnthropic",
                    return_value=mock_client):
            sections = await generate_report(SAMPLE_CONTEXT)

        assert len(sections) == 7
        assert mock_client.messages.create.call_count == 2

    @pytest.mark.asyncio
    async def test_raises_after_all_retries_fail(self):
        bad_message = MagicMock()
        bad_message.content = [MagicMock(text="잘못된 응답")]

        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(return_value=bad_message)

        with patch("sajucandle.saju.report_generator.anthropic.AsyncAnthropic",
                    return_value=mock_client):
            with pytest.raises(ValueError):
                await generate_report(SAMPLE_CONTEXT)

    @pytest.mark.asyncio
    async def test_uses_sonnet_for_standard_tier(self):
        mock_message = MagicMock()
        mock_message.content = [MagicMock(text=VALID_JSON_STR)]

        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(return_value=mock_message)

        with patch("sajucandle.saju.report_generator.anthropic.AsyncAnthropic",
                    return_value=mock_client):
            await generate_report(SAMPLE_CONTEXT, tier="standard")

        call_kwargs = mock_client.messages.create.call_args[1]
        assert "sonnet" in call_kwargs["model"]
