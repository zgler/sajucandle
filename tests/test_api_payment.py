"""tests/test_api_payment.py — POST /api/payments/confirm 엔드포인트 테스트."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

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

BASE_PAYLOAD = {
    "payment_key": "pk_test_abc123",
    "order_id": "order_20260514_001",
    "amount": 990,
    "year": 1985,
    "month": 3,
    "day": 15,
    "hour": 14,
    "gender": "M",
    "tier": "standard",
}


class TestPaymentConfirmValidation:
    def test_standard_tier_wrong_amount_returns_400(self, client: TestClient):
        payload = {**BASE_PAYLOAD, "tier": "standard", "amount": 9900}
        resp = client.post("/api/payments/confirm", json=payload)
        assert resp.status_code == 400

    def test_premium_tier_wrong_amount_returns_400(self, client: TestClient):
        payload = {**BASE_PAYLOAD, "tier": "premium", "amount": 990}
        resp = client.post("/api/payments/confirm", json=payload)
        assert resp.status_code == 400

    def test_invalid_tier_returns_400(self, client: TestClient):
        payload = {**BASE_PAYLOAD, "tier": "vip", "amount": 990}
        resp = client.post("/api/payments/confirm", json=payload)
        assert resp.status_code == 400


class TestPaymentConfirmSuccess:
    def _mock_toss_response(self, status_code: int = 200):
        mock_resp = MagicMock()
        mock_resp.status_code = status_code
        mock_resp.json.return_value = {"paymentKey": "pk_test_abc123", "status": "DONE"}
        return mock_resp

    def test_standard_payment_success(self, client: TestClient):
        mock_resp = self._mock_toss_response(200)
        with patch("sajucandle.api.main.os.environ.get", return_value="test_secret_key"), \
             patch("sajucandle.api.main.httpx.post", return_value=mock_resp), \
             patch("sajucandle.api.main.collect_report_context", return_value={}), \
             patch("sajucandle.api.main.generate_report",
                   new_callable=AsyncMock, return_value=MOCK_SECTIONS):
            payload = {**BASE_PAYLOAD, "tier": "standard", "amount": 990}
            resp = client.post("/api/payments/confirm", json=payload)

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["payment"]["tier"] == "standard"
        assert data["payment"]["amount"] == 990
        assert data["payment"]["order_id"] == payload["order_id"]
        assert "report" in data
        assert all(sec["locked"] is False for sec in data["report"]["sections"])

    def test_premium_payment_success(self, client: TestClient):
        mock_resp = self._mock_toss_response(200)
        with patch("sajucandle.api.main.os.environ.get", return_value="test_secret_key"), \
             patch("sajucandle.api.main.httpx.post", return_value=mock_resp), \
             patch("sajucandle.api.main.collect_report_context", return_value={}), \
             patch("sajucandle.api.main.generate_report",
                   new_callable=AsyncMock, return_value=MOCK_SECTIONS):
            payload = {**BASE_PAYLOAD, "tier": "premium", "amount": 9900}
            resp = client.post("/api/payments/confirm", json=payload)

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["payment"]["tier"] == "premium"
        assert data["payment"]["amount"] == 9900
        assert all(sec["locked"] is False for sec in data["report"]["sections"])


class TestPaymentConfirmFailure:
    def test_toss_rejection_returns_400(self, client: TestClient):
        mock_resp = MagicMock()
        mock_resp.status_code = 400
        mock_resp.json.return_value = {"code": "INVALID_PAYMENT", "message": "결제 실패"}

        with patch("sajucandle.api.main.os.environ.get", return_value="test_secret_key"), \
             patch("sajucandle.api.main.httpx.post", return_value=mock_resp):
            resp = client.post("/api/payments/confirm", json=BASE_PAYLOAD)

        assert resp.status_code == 400
        data = resp.json()
        assert data["detail"]["success"] is False

    def test_no_toss_secret_key_returns_503(self, client: TestClient):
        with patch("sajucandle.api.main.os.environ.get", return_value=None):
            resp = client.post("/api/payments/confirm", json=BASE_PAYLOAD)

        assert resp.status_code == 503
