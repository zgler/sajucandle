"""tests/test_api_saju.py — 사주 운세 API 엔드포인트 테스트."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sajucandle.api.main import app


@pytest.fixture
def client():
    return TestClient(app)


class TestProfileEndpoint:
    def test_profile_returns_200(self, client: TestClient):
        resp = client.post("/api/saju/profile", json={
            "year": 1985, "month": 3, "day": 15,
            "hour": 14, "gender": "M",
        })
        assert resp.status_code == 200

    def test_profile_response_shape(self, client: TestClient):
        resp = client.post("/api/saju/profile", json={
            "year": 1985, "month": 3, "day": 15,
            "hour": 14, "gender": "M",
        })
        data = resp.json()
        assert "investor_type" in data
        assert "day_master" in data
        assert "saju" in data
        assert "element_distribution" in data
        assert "description" in data

    def test_profile_without_hour(self, client: TestClient):
        resp = client.post("/api/saju/profile", json={
            "year": 1985, "month": 3, "day": 15,
            "gender": "F",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["saju"]["hour_pillar"] == ""


class TestDailyEndpoint:
    def test_daily_returns_200(self, client: TestClient):
        resp = client.get("/api/saju/daily", params={
            "year": 1985, "month": 3, "day": 15,
            "hour": 14, "gender": "M",
        })
        assert resp.status_code == 200

    def test_daily_response_shape(self, client: TestClient):
        resp = client.get("/api/saju/daily", params={
            "year": 1985, "month": 3, "day": 15,
            "hour": 14, "gender": "M",
        })
        data = resp.json()
        assert "judgment_score" in data
        assert "execution_score" in data
        assert "patience_score" in data
        assert "tengod_label" in data
        assert "coaching" in data

    def test_daily_with_specific_date(self, client: TestClient):
        resp = client.get("/api/saju/daily", params={
            "year": 1985, "month": 3, "day": 15,
            "hour": 14, "gender": "M",
            "date": "2026-05-13",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["date"] == "2026-05-13"


class TestYearlyEndpoint:
    def test_yearly_returns_200(self, client: TestClient):
        resp = client.get("/api/saju/yearly", params={
            "year": 1985, "month": 3, "day": 15,
            "hour": 14, "gender": "M",
        })
        assert resp.status_code == 200

    def test_yearly_response_shape(self, client: TestClient):
        resp = client.get("/api/saju/yearly", params={
            "year": 1985, "month": 3, "day": 15,
            "hour": 14, "gender": "M",
        })
        data = resp.json()
        assert "sewoon_pillar" in data
        assert "sewoon_tengod" in data
        assert "sewoon_message" in data
        assert "daeun" in data
