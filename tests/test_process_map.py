"""Per-project SCM process map and risk register."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.process_map import STAGE_ORDER, _classify
from app.schemas import BOMItem, PurchaseRequisition, RFQ
from tests.conftest import headers_for_user


PROJECT = "PRJ-RB-660"


def test_process_map_buckets_every_bom_line(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    res = client.get(f"/api/projects/{PROJECT}/process-map", headers=auth_headers)
    assert res.status_code == 200
    body = res.json()
    assert body["project_id"] == PROJECT
    assert body["bom_total"] > 0
    current = sum(s["current"] for s in body["stages"])
    assert current == body["bom_total"]
    assert [s["stage"] for s in body["stages"]] == list(STAGE_ORDER)
    seen: set[str] = set()
    for stage in body["stages"]:
        for item in stage["items"]:
            assert item["bom_item_id"] not in seen
            seen.add(item["bom_item_id"])
    assert len(seen) == body["bom_total"]


def test_missing_spec_buckets_and_seeds_risk(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    bom = client.get(f"/api/projects/{PROJECT}/bom", headers=auth_headers)
    assert bom.status_code == 200
    missing = [b for b in bom.json() if b["status"] == "spec_missing"]
    assert missing, "Riverbank fixture should have spec_missing lines"

    res = client.get(f"/api/projects/{PROJECT}/process-map", headers=auth_headers)
    assert res.status_code == 200
    body = res.json()
    spec = next(s for s in body["stages"] if s["stage"] == "spec")
    spec_ids = {i["bom_item_id"] for i in spec["items"]}
    for item in missing:
        assert item["bom_item_id"] in spec_ids

    keys = {r["signal_key"] for r in body["risks"]}
    for item in missing:
        assert f"spec:{item['bom_item_id']}" in keys
    live_spec = next(r for r in body["risks"] if r["signal_key"] == f"spec:{missing[0]['bom_item_id']}")
    assert live_spec["source"] == "live"
    assert live_spec["live"] is True
    assert live_spec["process_stage"] == "spec"


def test_patch_status_survives_reseed(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    first = client.get(f"/api/projects/{PROJECT}/process-map", headers=auth_headers)
    assert first.status_code == 200
    risk = next(r for r in first.json()["risks"] if r["signal_key"] and r["signal_key"].startswith("spec:"))
    patched = client.patch(
        f"/api/projects/{PROJECT}/risks/{risk['risk_id']}",
        headers=auth_headers,
        json={"status": "mitigating", "owner": "Buyer One", "mitigation": "Chase engineering"},
    )
    assert patched.status_code == 200
    assert patched.json()["status"] == "mitigating"
    assert patched.json()["owner"] == "Buyer One"

    second = client.get(f"/api/projects/{PROJECT}/process-map", headers=auth_headers)
    assert second.status_code == 200
    again = next(r for r in second.json()["risks"] if r["risk_id"] == risk["risk_id"])
    assert again["status"] == "mitigating"
    assert again["owner"] == "Buyer One"
    assert again["mitigation"] == "Chase engineering"
    assert again["live"] is True
    assert again["signal_key"] == risk["signal_key"]


def test_process_map_cross_tenant_404(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    res = client.get("/api/projects/PRJ-HE-WIND/process-map", headers=auth_headers)
    assert res.status_code == 404


def test_helios_can_read_own_process_map(client: TestClient) -> None:
    headers = headers_for_user("helios-buyer-01")
    res = client.get("/api/projects/PRJ-HE-WIND/process-map", headers=headers)
    assert res.status_code == 200
    assert res.json()["project_id"] == "PRJ-HE-WIND"


def _planned_bom_item(client: TestClient, headers: dict[str, str]) -> dict:
    from app.sourcing import list_prs

    taken = {
        p.bom_item_id
        for p in list_prs(tenant_id="arcforge")
        if p.project_id == PROJECT and p.bom_item_id
    }
    bom = client.get(f"/api/projects/{PROJECT}/bom", headers=headers)
    assert bom.status_code == 200
    item = next(
        b for b in bom.json()
        if b["status"] == "planned" and b["bom_item_id"] not in taken
    )
    return item


def _find_line(body: dict, bom_item_id: str) -> dict:
    for stage in body["stages"]:
        for item in stage["items"]:
            if item["bom_item_id"] == bom_item_id:
                return {"stage": stage["stage"], **item}
    raise AssertionError(f"{bom_item_id} missing from process map")


def test_reissued_rfq_uses_pr_pointer(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    item = _planned_bom_item(client, auth_headers)
    pr = client.post(
        "/api/prs",
        headers=auth_headers,
        json={"project_id": PROJECT, "bom_item_id": item["bom_item_id"]},
    )
    assert pr.status_code == 200
    pr_no = pr.json()["pr_no"]

    first = client.post(
        "/api/rfqs",
        headers=auth_headers,
        json={"pr_no": pr_no, "vendors": ["Helios Cast & Forge"], "due_in_days": 7},
    )
    assert first.status_code == 200
    old_rfq = first.json()["rfq_no"]

    second = client.post(
        "/api/rfqs",
        headers=auth_headers,
        json={"pr_no": pr_no, "vendors": ["Helios Cast & Forge"], "due_in_days": 7},
    )
    assert second.status_code == 200
    new_rfq = second.json()["rfq_no"]
    assert new_rfq != old_rfq

    mapped = client.get(f"/api/projects/{PROJECT}/process-map", headers=auth_headers)
    assert mapped.status_code == 200
    line = _find_line(mapped.json(), item["bom_item_id"])
    assert line["stage"] == "rfq"
    assert line["entity_id"] == new_rfq
    assert line["href"] == f"/sourcing/rfqs/{new_rfq}"


def test_newer_draft_pr_does_not_hide_po(
    client: TestClient,
    head_headers: dict[str, str],
) -> None:
    item = _planned_bom_item(client, head_headers)
    pr = client.post(
        "/api/prs",
        headers=head_headers,
        json={
            "project_id": PROJECT,
            "bom_item_id": item["bom_item_id"],
            "budget_value_usd": 1_000_000,
        },
    )
    assert pr.status_code == 200
    pr_no = pr.json()["pr_no"]

    rfq = client.post(
        "/api/rfqs",
        headers=head_headers,
        json={"pr_no": pr_no, "vendors": ["Helios Cast & Forge"], "due_in_days": 7},
    )
    assert rfq.status_code == 200
    rfq_no = rfq.json()["rfq_no"]

    quote = client.post(
        f"/api/rfqs/{rfq_no}/quotes",
        headers=head_headers,
        json={
            "vendor": "Helios Cast & Forge",
            "unit_price_usd": 10.0,
            "lead_time_days": 30,
            "quantity": 1,
        },
    )
    assert quote.status_code == 200
    assert quote.json()["status"] == "applied"
    quote_id = quote.json()["quote"]["quote_id"]

    award = client.post(
        f"/api/rfqs/{rfq_no}/award",
        headers=head_headers,
        json={"quote_id": quote_id, "rationale": "process-map test"},
    )
    assert award.status_code == 200
    po_no = award.json()["po"]["po_no"]

    second = client.post(
        "/api/prs",
        headers=head_headers,
        json={"project_id": PROJECT, "bom_item_id": item["bom_item_id"]},
    )
    assert second.status_code == 200
    assert second.json()["pr_no"] != pr_no

    mapped = client.get(f"/api/projects/{PROJECT}/process-map", headers=head_headers)
    assert mapped.status_code == 200
    line = _find_line(mapped.json(), item["bom_item_id"])
    assert line["stage"] == "po"
    assert line["entity_id"] == po_no


def test_awarded_rfq_with_quotes_buckets_award() -> None:
    now = datetime.now(timezone.utc)
    item = BOMItem(
        bom_item_id="BOM-T",
        project_id=PROJECT,
        code="T-1",
        description="test",
        quantity=1,
        status="requisitioned",
    )
    pr = PurchaseRequisition(
        pr_no="PR-T",
        project_id=PROJECT,
        code="T-1",
        description="test",
        quantity=1,
        created_at=now,
        status="quoted",
        rfq_no="RFQ-T",
    )
    rfq = RFQ(
        rfq_no="RFQ-T",
        pr_no="PR-T",
        project_id=PROJECT,
        code="T-1",
        description="test",
        quantity=1,
        issued_at=now,
        due_at=now,
        status="awarded",
    )
    stage, _, _, label = _classify(item, pr, rfq, None, None, False, 2, None)
    assert stage == "award"
    assert label == "awarded"


def test_overdue_milestone_stays_live(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    from app.planning import get_project

    project = get_project(PROJECT, tenant_id="arcforge")
    assert project is not None
    milestone = project.milestones[0]
    original = milestone.required_on_site_date
    milestone.required_on_site_date = date.today() - timedelta(days=3)
    try:
        res = client.get(f"/api/projects/{PROJECT}/process-map", headers=auth_headers)
        assert res.status_code == 200
        key = f"milestone:{milestone.code}"
        risk = next(r for r in res.json()["risks"] if r["signal_key"] == key)
        assert risk["live"] is True
        assert risk["severity"] == "critical"
        assert "overdue" in risk["title"]
    finally:
        milestone.required_on_site_date = original


def test_commercial_collector_failure_keeps_live_risks(client: TestClient) -> None:
    from app import risk_register

    with risk_register._lock:
        risk_register._upsert_live(
            tenant_id="arcforge",
            project_id=PROJECT,
            signal_key="commercial:TEST-1",
            title="Over budget: TEST",
            detail="+20% variance on TEST",
            severity="high",
            category="commercial",
            process_stage="award",
            href="/commercial",
        )

    with patch("app.commercial.build_commercial_lines", side_effect=RuntimeError("boom")):
        risk_register.seed_project(PROJECT, "arcforge")

    row = next(
        r for r in risk_register.list_project_risks(PROJECT, "arcforge")
        if r.signal_key == "commercial:TEST-1"
    )
    assert row.live is True


def test_seed_does_not_bump_updated_at_when_signal_unchanged(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    first = client.get(f"/api/projects/{PROJECT}/process-map", headers=auth_headers)
    assert first.status_code == 200
    risk = next(r for r in first.json()["risks"] if r["signal_key"] and r["signal_key"].startswith("spec:"))
    second = client.get(f"/api/projects/{PROJECT}/process-map", headers=auth_headers)
    assert second.status_code == 200
    again = next(r for r in second.json()["risks"] if r["risk_id"] == risk["risk_id"])
    assert again["updated_at"] == risk["updated_at"]


def test_seed_flushes_risks(client: TestClient, auth_headers: dict[str, str]) -> None:
    from app.persistence import STATE_DIR

    res = client.get(f"/api/projects/{PROJECT}/process-map", headers=auth_headers)
    assert res.status_code == 200
    path = STATE_DIR / "risks.json"
    assert path.exists()
    data = json.loads(path.read_text())
    assert int(data["counter"]["risk"]) > 0
    assert any(
        r.get("project_id") == PROJECT
        for bucket in data["risks"].values()
        for r in bucket.values()
    )
