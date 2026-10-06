"""A granted approval whose commit failed can be retried."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import approvals, vendor_store
from tests.conftest import TENANT


def _vendor(name: str) -> dict:
    return {
        "name": name, "category": "Valves", "country": "India", "lead_time_days": 30,
        "on_time_delivery_pct": 95, "quality_ppm": 100, "annual_spend_usd": 1000,
    }


def test_retry_applies_after_transient_failure(
    client: TestClient,
    buyer_headers: dict[str, str],
    head_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pending = client.post("/api/vendors", headers=buyer_headers, json=_vendor("Retry Valves"))
    approval_id = pending.json()["approval"]["approval_id"]

    real = approvals._committers["vendor_onboarding"]
    calls = {"n": 0}

    def flaky(payload: dict, tenant_id: str):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("store temporarily unavailable")
        return real(payload, tenant_id)

    monkeypatch.setitem(approvals._committers, "vendor_onboarding", flaky)

    first = client.post(f"/api/approvals/{approval_id}/approve", headers=head_headers)
    assert first.json()["status"] == "failed"
    assert not any(s.name == "Retry Valves" for s in vendor_store._runtime.get(TENANT, []))

    # Buyers can't retry; heads can.
    assert client.post(f"/api/approvals/{approval_id}/retry", headers=buyer_headers).status_code == 403
    retried = client.post(f"/api/approvals/{approval_id}/retry", headers=head_headers)
    assert retried.status_code == 200
    body = retried.json()
    assert body["status"] == "approved"
    assert body["result_ref"] == "Retry Valves"
    assert "retried by" in body["decision_note"]
    assert any(s.name == "Retry Valves" for s in vendor_store._runtime.get(TENANT, []))

    # Only failed approvals can be retried.
    assert client.post(f"/api/approvals/{approval_id}/retry", headers=head_headers).status_code == 409
