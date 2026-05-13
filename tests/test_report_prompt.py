"""tests/test_report_prompt.py — 프롬프트 조립 테스트."""
from __future__ import annotations

import json
from sajucandle.saju.report_prompt import build_messages


SAMPLE_CONTEXT = {
    "birth": {"year": 1985, "month": 3, "day": 15, "hour": 14, "gender": "M"},
    "pillars": {
        "year": {"pillar": "乙丑", "stem": "乙", "branch": "丑"},
        "month": {"pillar": "己卯", "stem": "己", "branch": "卯"},
        "day": {"pillar": "癸丑", "stem": "癸", "branch": "丑"},
        "hour": {"pillar": "己未", "stem": "己", "branch": "未"},
    },
    "day_master": {"stem": "癸", "element": "水", "yin_yang": "음"},
    "tengod_distribution": {"비겁": 2, "식상": 0, "재성": 1, "관성": 2, "인성": 1},
    "element_balance": {"木": 2, "火": 0, "土": 3, "金": 0, "水": 1},
    "dominant_group": "관성",
    "investor_type": "원칙형",
    "sewoon": {"pillar": "丙午", "stem": "丙", "tengod": "정재"},
    "monthly_pillars": [
        {"month": i, "pillar": "己丑", "stem": "己", "tengod": "편관"}
        for i in range(1, 13)
    ],
    "current_daeun": {
        "pillar": "乙亥", "stem": "乙",
        "tengod": "식신", "start_age": 33, "end_age": 43,
    },
    "shinsal": ["천을귀인", "역마살"],
    "relations": {
        "day_sewoon": {"pros": ["육합"], "cons": []},
        "day_daeun": {"pros": [], "cons": ["충"]},
    },
}


class TestBuildMessages:
    def test_returns_two_messages(self):
        msgs = build_messages(SAMPLE_CONTEXT)
        assert len(msgs) == 2

    def test_system_message_role(self):
        msgs = build_messages(SAMPLE_CONTEXT)
        assert msgs[0]["role"] == "system"

    def test_user_message_role(self):
        msgs = build_messages(SAMPLE_CONTEXT)
        assert msgs[1]["role"] == "user"

    def test_system_contains_role_definition(self):
        msgs = build_messages(SAMPLE_CONTEXT)
        system_text = msgs[0]["content"]
        assert "투자" in system_text
        assert "감정사" in system_text or "감정서" in system_text

    def test_system_contains_output_format(self):
        msgs = build_messages(SAMPLE_CONTEXT)
        system_text = msgs[0]["content"]
        assert "sections" in system_text
        assert "JSON" in system_text

    def test_system_contains_disclaimer(self):
        msgs = build_messages(SAMPLE_CONTEXT)
        system_text = msgs[0]["content"]
        assert "투자 권유" in system_text or "투자 조언" in system_text

    def test_user_contains_context_json(self):
        msgs = build_messages(SAMPLE_CONTEXT)
        user_text = msgs[1]["content"]
        assert "癸" in user_text
        assert "원칙형" in user_text
        assert "丙午" in user_text

    def test_user_message_parseable_json_block(self):
        """유저 메시지 안에 컨텍스트 JSON이 파싱 가능해야 한다."""
        msgs = build_messages(SAMPLE_CONTEXT)
        user_text = msgs[1]["content"]
        start = user_text.find("{")
        end = user_text.rfind("}") + 1
        assert start >= 0
        parsed = json.loads(user_text[start:end])
        assert parsed["day_master"]["stem"] == "癸"

    def test_seven_section_guide_present(self):
        msgs = build_messages(SAMPLE_CONTEXT)
        system_text = msgs[0]["content"]
        assert "명식 해석" in system_text
        assert "투자 DNA" in system_text
        assert "세운 전략" in system_text
        assert "월별 타이밍" in system_text
        assert "현재 대운" in system_text
        assert "투자 스타일" in system_text
        assert "투자 함정" in system_text
