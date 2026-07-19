"""Pending vendor onboarding should surface in the head's alert feed."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app._cache import invalidate_all
from app.alerts import build_alert_feed
from app.tenants import get_user
from tests.conftest import BUYER_ID, HEAD_ID, headers_for_user


def test_vendor_onboarding_pending_appears_in_head_alerts(client: TestClient) -> None:
    buyer = headers_for_user(BUYER_ID)
    name = "Alert Feed Valve Co"
    res = client.post(
        "/api/vendors",
        headers=buyer,
        json={
            "name": name,
            "category": "Forged valves",
            "country": "Norway",
            "lead_time_days": 40,
            "on_time_delivery_pct": 92.0,
            "quality_ppm": 400,
            "annual_spend_usd": 120000.0,
            "approved_alternatives": 1,
            "risk_flags": ["new supplier"],
        },
    )
    assert res.status_code == 200
    assert res.json()["status"] == "pending_approval"

    invalidate_all()
    head = get_user(HEAD_ID)
    assert head is not None
    feed = build_alert_feed(head)
    titles = [a.title for a in feed.alerts]
    assert any(name in t and "Approval needed" in t for t in titles), titles
    assert any(a.category == "approval" and a.href == "/approvals" for a in feed.alerts)
