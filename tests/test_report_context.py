"""tests/test_report_context.py — 감정서 컨텍스트 수집 테스트."""
from __future__ import annotations

import pytest
from sajucandle.saju.report_context import collect_report_context


class TestCollectReportContext:
    """collect_report_context가 올바른 구조를 반환하는지 검증."""

    def test_returns_dict(self):
        ctx = collect_report_context(1985, 3, 15, 14, "M", 2026)
        assert isinstance(ctx, dict)

    def test_birth_section(self):
        ctx = collect_report_context(1985, 3, 15, 14, "M", 2026)
        birth = ctx["birth"]
        assert birth["year"] == 1985
        assert birth["month"] == 3
        assert birth["day"] == 15
        assert birth["hour"] == 14
        assert birth["gender"] == "M"

    def test_pillars_section(self):
        ctx = collect_report_context(1985, 3, 15, 14, "M", 2026)
        pillars = ctx["pillars"]
        for key in ("year", "month", "day", "hour"):
            p = pillars[key]
            assert "pillar" in p
            assert "stem" in p
            assert "branch" in p
            assert len(p["pillar"]) == 2

    def test_day_master_section(self):
        ctx = collect_report_context(1985, 3, 15, 14, "M", 2026)
        dm = ctx["day_master"]
        assert "stem" in dm
        assert "element" in dm
        assert dm["element"] in ("木", "火", "土", "金", "水")
        assert "yin_yang" in dm
        assert dm["yin_yang"] in ("양", "음")

    def test_tengod_distribution(self):
        ctx = collect_report_context(1985, 3, 15, 14, "M", 2026)
        td = ctx["tengod_distribution"]
        for group in ("비겁", "식상", "재성", "관성", "인성"):
            assert group in td
            assert isinstance(td[group], int)

    def test_element_balance(self):
        ctx = collect_report_context(1985, 3, 15, 14, "M", 2026)
        eb = ctx["element_balance"]
        for elem in ("木", "火", "土", "金", "水"):
            assert elem in eb

    def test_investor_type(self):
        ctx = collect_report_context(1985, 3, 15, 14, "M", 2026)
        assert ctx["investor_type"] in ("독립형", "직감형", "실리형", "원칙형", "분석형")
        assert isinstance(ctx["dominant_group"], str)

    def test_sewoon(self):
        ctx = collect_report_context(1985, 3, 15, 14, "M", 2026)
        sewoon = ctx["sewoon"]
        assert "pillar" in sewoon
        assert "stem" in sewoon
        assert "tengod" in sewoon

    def test_monthly_pillars_count(self):
        ctx = collect_report_context(1985, 3, 15, 14, "M", 2026)
        mp = ctx["monthly_pillars"]
        assert len(mp) == 12
        assert mp[0]["month"] == 1
        assert mp[11]["month"] == 12
        for entry in mp:
            assert "pillar" in entry
            assert "stem" in entry
            assert "tengod" in entry

    def test_current_daeun(self):
        ctx = collect_report_context(1985, 3, 15, 14, "M", 2026)
        daeun = ctx["current_daeun"]
        assert "pillar" in daeun
        assert "stem" in daeun
        assert "tengod" in daeun
        assert "start_age" in daeun
        assert "end_age" in daeun

    def test_shinsal(self):
        ctx = collect_report_context(1985, 3, 15, 14, "M", 2026)
        assert isinstance(ctx["shinsal"], list)

    def test_relations(self):
        ctx = collect_report_context(1985, 3, 15, 14, "M", 2026)
        rels = ctx["relations"]
        assert "day_sewoon" in rels
        assert "day_daeun" in rels
        for key in ("day_sewoon", "day_daeun"):
            assert "pros" in rels[key]
            assert "cons" in rels[key]

    def test_hour_none(self):
        """시주 없는 경우에도 정상 작동."""
        ctx = collect_report_context(1985, 3, 15, None, "F", 2026)
        assert ctx["birth"]["hour"] is None
        assert ctx["pillars"]["hour"] is None


class TestCollectReportContextEdgeCases:
    def test_female_gender(self):
        ctx = collect_report_context(1990, 7, 20, 8, "F", 2026)
        assert ctx["birth"]["gender"] == "F"
        assert isinstance(ctx["current_daeun"], dict)

    def test_different_target_year(self):
        ctx = collect_report_context(1985, 3, 15, 14, "M", 2027)
        assert ctx["sewoon"]["pillar"]  # 다른 연도여도 세운 존재
