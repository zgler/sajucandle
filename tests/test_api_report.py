"""tests/test_api_report.py — POST /api/saju/report 엔드포인트 테스트."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import anthropic
import pytest
from fastapi.testclient import TestClient
from sajucandle.api.main import app


@pytest.fixture
def client():
    return TestClient(app)


MOCK_SECTIONS = [
    {"id": i, "title": f"섹션{i}", "content": f"내용{i}", "highlight": f"핵심{i}"}
    for i in range(1, 8)
]


class TestReportEndpoint:
    def test_report_returns_200(self, client: TestClient):
        with patch("sajucandle.api.main._has_anthropic_key", return_value=True), \
             patch("sajucandle.api.main.collect_report_context", return_value={}), \
             patch("sajucandle.api.main.generate_report",
                    new_callable=AsyncMock, return_value=MOCK_SECTIONS):
            resp = client.post("/api/saju/report", json={
                "year": 1985, "month": 3, "day": 15,
                "hour": 14, "gender": "M",
            })
        assert resp.status_code == 200

    def test_report_response_shape(self, client: TestClient):
        with patch("sajucandle.api.main._has_anthropic_key", return_value=True), \
             patch("sajucandle.api.main.collect_report_context", return_value={}), \
             patch("sajucandle.api.main.generate_report",
                    new_callable=AsyncMock, return_value=MOCK_SECTIONS):
            resp = client.post("/api/saju/report", json={
                "year": 1985, "month": 3, "day": 15,
                "hour": 14, "gender": "M",
            })
        data = resp.json()
        assert "report_id" in data
        assert "target_year" in data
        assert "tier" in data
        assert "sections" in data
        assert len(data["sections"]) == 7
        for sec in data["sections"]:
            assert "locked" in sec

    def test_sections_1_2_unlocked_with_content(self, client: TestClient):
        with patch("sajucandle.api.main._has_anthropic_key", return_value=True), \
             patch("sajucandle.api.main.collect_report_context", return_value={}), \
             patch("sajucandle.api.main.generate_report",
                    new_callable=AsyncMock, return_value=MOCK_SECTIONS):
            resp = client.post("/api/saju/report", json={
                "year": 1985, "month": 3, "day": 15,
                "hour": 14, "gender": "M",
            })
        data = resp.json()
        for sec in data["sections"][:2]:
            assert sec["locked"] is False
            assert sec["content"] != ""

    def test_sections_3_to_7_locked_no_content(self, client: TestClient):
        with patch("sajucandle.api.main._has_anthropic_key", return_value=True), \
             patch("sajucandle.api.main.collect_report_context", return_value={}), \
             patch("sajucandle.api.main.generate_report",
                    new_callable=AsyncMock, return_value=MOCK_SECTIONS):
            resp = client.post("/api/saju/report", json={
                "year": 1985, "month": 3, "day": 15,
                "hour": 14, "gender": "M",
            })
        data = resp.json()
        for sec in data["sections"][2:]:
            assert sec["locked"] is True
            assert sec["content"] == ""
            assert sec["title"] != ""
            assert sec["highlight"] != ""

    def test_report_id_format(self, client: TestClient):
        with patch("sajucandle.api.main._has_anthropic_key", return_value=True), \
             patch("sajucandle.api.main.collect_report_context", return_value={}), \
             patch("sajucandle.api.main.generate_report",
                    new_callable=AsyncMock, return_value=MOCK_SECTIONS):
            resp = client.post("/api/saju/report", json={
                "year": 1985, "month": 3, "day": 15,
                "hour": 14, "gender": "M",
            })
        data = resp.json()
        assert data["report_id"].startswith("rpt_")
        assert "M" in data["report_id"]

    def test_report_without_hour(self, client: TestClient):
        with patch("sajucandle.api.main._has_anthropic_key", return_value=True), \
             patch("sajucandle.api.main.collect_report_context", return_value={}), \
             patch("sajucandle.api.main.generate_report",
                    new_callable=AsyncMock, return_value=MOCK_SECTIONS):
            resp = client.post("/api/saju/report", json={
                "year": 1985, "month": 3, "day": 15,
                "gender": "F",
            })
        assert resp.status_code == 200
        data = resp.json()
        assert "00F" in data["report_id"]

    def test_report_no_api_key_returns_503(self, client: TestClient):
        with patch("sajucandle.api.main._has_anthropic_key", return_value=False):
            resp = client.post("/api/saju/report", json={
                "year": 1985, "month": 3, "day": 15,
                "gender": "M",
            })
        assert resp.status_code == 503

    def test_report_parse_error_returns_502(self, client: TestClient):
        with patch("sajucandle.api.main._has_anthropic_key", return_value=True), \
             patch("sajucandle.api.main.collect_report_context", return_value={}), \
             patch("sajucandle.api.main.generate_report",
                        new_callable=AsyncMock,
                        side_effect=ValueError("파싱 실패")):
            resp = client.post("/api/saju/report", json={
                "year": 1985, "month": 3, "day": 15,
                "gender": "M",
            })
        assert resp.status_code == 502

    def test_report_timeout_returns_504(self, client: TestClient):
        with patch("sajucandle.api.main._has_anthropic_key", return_value=True), \
             patch("sajucandle.api.main.collect_report_context", return_value={}), \
             patch("sajucandle.api.main.generate_report",
                        new_callable=AsyncMock,
                        side_effect=anthropic.APITimeoutError(request=None)):
            resp = client.post("/api/saju/report", json={
                "year": 1985, "month": 3, "day": 15,
                "gender": "M",
            })
        assert resp.status_code == 504
