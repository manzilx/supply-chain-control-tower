"""Write-through persistence for critical stores (approvals, audit, vendors, sourcing)."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from app import approvals, audit, sourcing, vendor_store
from app.persistence import STATE_DIR, restore_all
from tests.conftest import TENANT


def _supplier(name: str) -> dict:
    return {
        "name": name,
        "category": "Write-through widgets",
        "country": "Sweden",
        "lead_time_days": 30,
        "on_time_delivery_pct": 95.0,
        "quality_ppm": 200,
        "annual_spend_usd": 100_000.0,
        "approved_alternatives": 2,
        "risk_flags": ["pilot"],
    }


def test_write_through_vendor_restore_after_restart(
    client: TestClient,
    head_headers: dict[str, str],
) -> None:
    name = "Cycle4 WriteThrough Vendor"

    res = client.post("/api/vendors", json=_supplier(name), headers=head_headers)
    assert res.status_code == 200
    reply = res.json()
    assert reply["status"] == "applied"
    assert reply["scorecard"]["vendor"] == name

    vendors_path = STATE_DIR / "vendors.json"
    approvals_path = STATE_DIR / "approvals.json"
    audit_path = STATE_DIR / "audit.json"
    version_path = STATE_DIR / ".version"

    assert vendors_path.exists(), "vendors.json should be flushed immediately"
    assert approvals_path.exists(), "approvals.json should be flushed immediately"
    assert version_path.exists(), "flush_critical should write .version for restore_all"

    vendors_data = json.loads(vendors_path.read_text())
    assert TENANT in vendors_data
    assert any(item["name"] == name for item in vendors_data[TENANT])

    approvals_data = json.loads(approvals_path.read_text())
    tenant_approvals = approvals_data.get("approvals", {}).get(TENANT, {})
    assert any(
        a.get("kind") == "vendor_onboarding" and name in (a.get("title") or "")
        for a in tenant_approvals.values()
    )

    assert audit_path.exists(), "audit.json should be flushed after vendor create"
    audit_data = json.loads(audit_path.read_text())
    assert any(
        e.get("entity_kind") == "vendor" and e.get("entity_id") == name
        for e in audit_data
    )

    # Simulate process restart: wipe in-memory critical stores.
    vendor_store._runtime.clear()
    approvals._approvals.clear()
    approvals._counter["approval"] = 0
    audit._events.clear()

    restored = restore_all()
    assert restored.get("restored") is True

    scorecard = client.get(f"/api/vendors/intel/{name}", headers=head_headers)
    assert scorecard.status_code == 200
    assert scorecard.json()["vendor"] == name

    intel = client.get("/api/vendors/intel", headers=head_headers)
    assert intel.status_code == 200
    assert name in {v["vendor"] for v in intel.json()}


def test_write_through_sourcing_pr_on_disk(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    """PR create emits audit → flush_critical must also snap sourcing.json."""
    projects = client.get("/api/projects", headers=auth_headers)
    assert projects.status_code == 200
    project = next(p for p in projects.json() if p["project_id"].startswith("PRJ-AF"))
    bom = client.get(f"/api/projects/{project['project_id']}/bom", headers=auth_headers)
    assert bom.status_code == 200
    bom_item = bom.json()[0]

    pr_res = client.post(
        "/api/prs",
        headers=auth_headers,
        json={
            "project_id": project["project_id"],
            "bom_item_id": bom_item["bom_item_id"],
            "budget_value_usd": 2500.0,
            "buyer": "Write-through Buyer",
        },
    )
    assert pr_res.status_code == 200
    pr_no = pr_res.json()["pr_no"]

    sourcing_path = STATE_DIR / "sourcing.json"
    assert sourcing_path.exists(), "sourcing.json should flush with critical stores"
    data = json.loads(sourcing_path.read_text())
    assert pr_no in data.get("prs", {})

    del sourcing._prs[pr_no]  # type: ignore[attr-defined]
    restored = restore_all()
    assert restored.get("restored") is True
    assert sourcing.get_pr(pr_no, tenant_id=TENANT) is not None
