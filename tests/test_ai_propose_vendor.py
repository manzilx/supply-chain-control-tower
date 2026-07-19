"""AI propose-vendor path — REST + agent tool with approval gate."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.agent_tools import invoke, reset_tool_user, set_tool_user
from app.tenants import get_user
from tests.conftest import BUYER_ID, HEAD_ID, buyer_headers, head_headers


def _supplier(name: str) -> dict:
    return {
        "name": name,
        "category": "Forged valves",
        "country": "Norway",
        "lead_time_days": 42,
        "on_time_delivery_pct": 91.0,
        "quality_ppm": 600,
        "annual_spend_usd": 180_000.0,
        "approved_alternatives": 1,
        "risk_flags": ["new supplier"],
    }


def _vendor_names(client: TestClient, headers: dict[str, str]) -> set[str]:
    res = client.get("/api/vendors/intel", headers=headers)
    assert res.status_code == 200
    return {v["vendor"] for v in res.json()}


def test_buyer_propose_vendor_pending_not_in_intel(
    client: TestClient,
    buyer_headers: dict[str, str],
) -> None:
    name = "Cycle5 AI Propose Vendor"
    body = _supplier(name)

    res = client.post("/api/ai/propose-vendor", json=body, headers=buyer_headers)
    assert res.status_code == 200
    reply = res.json()
    assert reply["status"] == "pending_approval"
    assert reply["approval"]["kind"] == "vendor_onboarding"
    assert reply["approval"]["status"] == "pending"
    assert reply.get("scorecard") is None

    assert name not in _vendor_names(client, buyer_headers)


def test_head_approves_ai_proposed_vendor_with_audit(
    client: TestClient,
    buyer_headers: dict[str, str],
    head_headers: dict[str, str],
) -> None:
    name = "Cycle5 AI Approved Vendor"
    body = _supplier(name)

    pending = client.post("/api/ai/propose-vendor", json=body, headers=buyer_headers)
    assert pending.status_code == 200
    approval_id = pending.json()["approval"]["approval_id"]

    assert name not in _vendor_names(client, buyer_headers)

    decided = client.post(f"/api/approvals/{approval_id}/approve", json={}, headers=head_headers)
    assert decided.status_code == 200
    assert decided.json()["status"] == "approved"
    assert decided.json()["result_ref"] == name

    assert name in _vendor_names(client, head_headers)

    audit = client.get(f"/api/audit/entity/vendor/{name}", headers=head_headers)
    assert audit.status_code == 200
    events = audit.json()
    assert any(e.get("action") == "created" and e.get("entity_id") == name for e in events)


def test_tool_propose_vendor_with_context_buyer_pending() -> None:
    buyer = get_user(BUYER_ID)
    assert buyer is not None
    name = "Cycle5 Tool Context Vendor"
    token = set_tool_user(buyer)
    try:
        record = invoke(
            "propose_vendor_onboarding",
            {
                "name": name,
                "category": "Forged valves",
                "country": "Norway",
            },
        )
    finally:
        reset_tool_user(token)

    assert "Submitted vendor" in record.output_summary
    assert record.output_summary.startswith(f"Submitted vendor {name}")
    preview = record.output_preview
    assert isinstance(preview, dict)
    assert preview.get("status") == "pending_approval"
