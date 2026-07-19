"""Vendor onboarding approval gate — POST /api/vendors."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import BUYER_ID, HEAD_ID, buyer_headers, head_headers


def _supplier(name: str) -> dict:
    return {
        "name": name,
        "category": "Test widgets",
        "country": "Norway",
        "lead_time_days": 45,
        "on_time_delivery_pct": 92.0,
        "quality_ppm": 400,
        "annual_spend_usd": 250_000.0,
        "approved_alternatives": 1,
        "risk_flags": ["new supplier"],
    }


def _vendor_names(client: TestClient, headers: dict[str, str]) -> set[str]:
    res = client.get("/api/vendors/intel", headers=headers)
    assert res.status_code == 200
    return {v["vendor"] for v in res.json()}


def test_buyer_create_vendor_pending_not_in_intel(client: TestClient, buyer_headers: dict[str, str]) -> None:
    name = "Cycle3 Buyer Pending Vendor"
    body = _supplier(name)

    res = client.post("/api/vendors", json=body, headers=buyer_headers)
    assert res.status_code == 200
    reply = res.json()
    assert reply["status"] == "pending_approval"
    assert reply["approval"]["kind"] == "vendor_onboarding"
    assert reply["approval"]["status"] == "pending"
    assert reply.get("scorecard") is None

    names = _vendor_names(client, buyer_headers)
    assert name not in names


def test_head_create_vendor_applied_visible(client: TestClient, head_headers: dict[str, str]) -> None:
    name = "Cycle3 Head Applied Vendor"
    body = _supplier(name)

    res = client.post("/api/vendors", json=body, headers=head_headers)
    assert res.status_code == 200
    reply = res.json()
    assert reply["status"] == "applied"
    assert reply["scorecard"]["vendor"] == name
    assert reply.get("approval") is None

    names = _vendor_names(client, head_headers)
    assert name in names


def test_head_approves_buyer_pending_vendor(client: TestClient, buyer_headers: dict[str, str], head_headers: dict[str, str]) -> None:
    name = "Cycle3 Approved Later Vendor"
    body = _supplier(name)

    pending = client.post("/api/vendors", json=body, headers=buyer_headers)
    assert pending.status_code == 200
    approval_id = pending.json()["approval"]["approval_id"]

    assert name not in _vendor_names(client, buyer_headers)

    decided = client.post(f"/api/approvals/{approval_id}/approve", json={}, headers=head_headers)
    assert decided.status_code == 200
    assert decided.json()["status"] == "approved"
    assert decided.json()["result_ref"] == name

    assert name in _vendor_names(client, head_headers)
