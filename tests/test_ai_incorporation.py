"""AI incorporation: agent tools for approvals/GRN, tenant-safe weekly plan, explain GRN.

Hard rules under test:
- Agent can list pending approvals and the GRN queue, tenant-scoped.
- Deterministic router answers the copilot prompts that previously had no tool.
- Weekly plan RFQs do not leak across tenants.
- Weekly plan raises P1s from pending approvals and unmatched GRNs.
- Explain GRN is tenant-scoped and never implies stock was posted.
- Vision stays off; matcher is not an LLM.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app._cache import invalidate_all
from app.agent import dispatch_deterministic
from app.agent_tools import TOOLS, invoke, reset_tool_user, set_tool_user
from app.llm import vision_enabled
from app.store import matching
from app.tenants import get_user
from app.weekly_plan import build_weekly_plan
from tests.conftest import BUYER_ID, HEAD_ID, TENANT, headers_for_user
from tests.test_ai_propose_vendor import _supplier
from tests.test_store_grn import enrol, make_store, sync_grn


def test_vision_stays_off_and_matcher_has_no_llm() -> None:
    assert vision_enabled() is False
    assert not hasattr(matching, "grok_json")
    assert not hasattr(matching, "chat_completions")
    assert "get_pending_approvals" in TOOLS
    assert "get_grn_queue" in TOOLS


def test_deterministic_router_hits_approvals_and_grn_tools() -> None:
    user = get_user(HEAD_ID)
    assert user is not None
    token = set_tool_user(user)
    try:
        approvals = dispatch_deterministic("What's awaiting approval?")
        grns = dispatch_deterministic("Which GRNs still need a PO match?")
    finally:
        reset_tool_user(token)

    assert [c.tool for c in approvals.tool_calls] == ["get_pending_approvals"]
    assert [c.tool for c in grns.tool_calls] == ["get_grn_queue"]
    assert "auto-post" in grns.reply.lower() or "/store/grn-triage" in grns.reply


def test_pending_approvals_tool_is_tenant_scoped(
    client: TestClient,
    buyer_headers: dict[str, str],
) -> None:
    name = "AI Queue Vendor Arcforge"
    res = client.post("/api/ai/propose-vendor", json=_supplier(name), headers=buyer_headers)
    assert res.status_code == 200
    approval_id = res.json()["approval"]["approval_id"]

    helios_buyer = get_user("helios-buyer-01")
    assert helios_buyer is not None
    token = set_tool_user(helios_buyer)
    try:
        record = invoke("get_pending_approvals", {})
    finally:
        reset_tool_user(token)
    preview = record.output_preview
    assert isinstance(preview, list)
    assert approval_id not in {row.get("approval_id") for row in preview}

    arcforge_head = get_user(HEAD_ID)
    assert arcforge_head is not None
    token = set_tool_user(arcforge_head)
    try:
        record = invoke("get_pending_approvals", {})
    finally:
        reset_tool_user(token)
    ids = {row.get("approval_id") for row in record.output_preview}  # type: ignore[union-attr]
    assert approval_id in ids


def test_weekly_plan_rfqs_and_approvals_are_tenant_scoped(
    client: TestClient,
    buyer_headers: dict[str, str],
) -> None:
    name = "AI Plan Vendor Arcforge"
    pending = client.post("/api/ai/propose-vendor", json=_supplier(name), headers=buyer_headers)
    assert pending.status_code == 200

    helios = headers_for_user("helios-head-01")
    projects = client.get("/api/projects", headers=helios)
    assert projects.status_code == 200
    helios_projects = projects.json()
    assert helios_projects
    pid = helios_projects[0]["project_id"]
    pr = client.post(
        "/api/prs",
        headers=helios,
        json={"project_id": pid, "code": "HE-AI-PIPE", "description": "Helios AI test pipe", "quantity": 2, "uom": "EA"},
    )
    assert pr.status_code == 200, pr.text
    rfq = client.post(
        "/api/rfqs",
        headers=helios,
        json={"pr_no": pr.json()["pr_no"], "vendors": ["NorthCable Subsea"], "due_in_days": 10},
    )
    assert rfq.status_code == 200, rfq.text
    helios_rfq = rfq.json()["rfq_no"]

    from app.sourcing import list_rfqs

    invalidate_all()
    arcforge_plan = build_weekly_plan(tenant_id=TENANT)
    helios_plan = build_weekly_plan(tenant_id="helios")

    arcforge_refs = [ref for item in arcforge_plan.items for ref in item.supporting_refs]
    assert helios_rfq not in arcforge_refs
    assert any(item.title.startswith("Decide ") for item in arcforge_plan.items)
    assert not any(item.title.startswith("Decide ") for item in helios_plan.items)
    assert any(ref.startswith("approval:") for ref in arcforge_refs)
    assert any(r.rfq_no == helios_rfq for r in list_rfqs(tenant_id="helios"))
    assert not any(r.rfq_no == helios_rfq for r in list_rfqs(tenant_id="arcforge"))


def test_grn_queue_tool_and_explain_are_tenant_scoped(
    client: TestClient,
    admin_headers: dict[str, str],
) -> None:
    store_id = make_store(client, admin_headers)
    device_headers, _ = enrol(client, admin_headers, store_id)
    synced = sync_grn(client, device_headers)
    assert synced.status_code == 200, synced.text
    grn_id = synced.json()["grn_id"]

    user = get_user(f"{TENANT}-admin-01")
    assert user is not None
    token = set_tool_user(user)
    try:
        record = invoke("get_grn_queue", {})
    finally:
        reset_tool_user(token)
    preview = record.output_preview
    assert isinstance(preview, list)
    ids = {row.get("grn_id") for row in preview}
    assert grn_id in ids

    helios_admin = get_user("helios-admin-01")
    assert helios_admin is not None
    token = set_tool_user(helios_admin)
    try:
        other = invoke("get_grn_queue", {})
    finally:
        reset_tool_user(token)
    other_ids = {row.get("grn_id") for row in other.output_preview}  # type: ignore[union-attr]
    assert grn_id not in other_ids

    explained = client.post(
        "/api/explain",
        headers=admin_headers,
        json={"kind": "grn", "id": grn_id},
    )
    assert explained.status_code == 200, explained.text
    body = explained.json()
    assert body["kind"] == "grn"
    assert "auto-post" in body["body"].lower() or "does not auto-post" in body["body"].lower()
    assert body["source"] == "deterministic"

    leaked = client.post(
        "/api/explain",
        headers=headers_for_user("helios-admin-01"),
        json={"kind": "grn", "id": grn_id},
    )
    assert leaked.status_code == 200
    assert "not found" in leaked.json()["headline"].lower()

    invalidate_all()
    plan = build_weekly_plan(tenant_id=TENANT)
    assert any("GRN" in item.title for item in plan.items)
