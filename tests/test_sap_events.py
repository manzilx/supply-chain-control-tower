"""SAP inbound webhook: auth, replay-safety, reversals, no status regressions."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app import sourcing
from tests.test_store_grn import make_po


def _project(client: TestClient, headers: dict[str, str]) -> str:
    return next(
        p["project_id"] for p in client.get("/api/projects", headers=headers).json()
        if p["project_id"].startswith("PRJ-AF")
    )


def _event(po_no: str, kind: str, **extra) -> dict:
    return {
        "kind": kind, "sap_doc_no": po_no, "ct_ref": po_no,
        "occurred_at": extra.pop("occurred_at", datetime.now(timezone.utc).isoformat()),
        **extra,
    }


def _post(client: TestClient, body: dict, **headers: str):
    return client.post("/api/integrations/sap/event", json=body, headers=headers)


def test_replayed_goods_receipt_is_applied_once(client: TestClient, head_headers: dict[str, str]) -> None:
    po = make_po(client, head_headers, _project(client, head_headers), 10)
    gr = _event(po["po_no"], "gr_posted", quantity=4)

    first = _post(client, gr)
    replay = _post(client, gr)  # same payload, e.g. a CPI retry
    assert first.json()["accepted"] and replay.json()["accepted"]
    assert "duplicate" in replay.json()["note"]
    assert sourcing._pos[po["po_no"]].sap_gr_qty == 4

    # Same document id on a different timestamp is still the same event.
    by_id = _event(po["po_no"], "gr_posted", quantity=3, event_id="5000001234")
    _post(client, by_id)
    _post(client, {**by_id, "occurred_at": datetime.now(timezone.utc).isoformat()})
    assert sourcing._pos[po["po_no"]].sap_gr_qty == 7


def test_over_receipt_flagged_and_reversal_undoes_delivery(
    client: TestClient, head_headers: dict[str, str]
) -> None:
    po = make_po(client, head_headers, _project(client, head_headers), 10)
    over = _post(client, _event(po["po_no"], "gr_posted", quantity=12, event_id="GR-1"))
    assert "over-receipt" in over.json()["note"]
    assert sourcing._pos[po["po_no"]].status == "delivered"

    _post(client, _event(po["po_no"], "gr_posted", quantity=-12, event_id="GR-1-REV"))
    stored = sourcing._pos[po["po_no"]]
    assert stored.sap_gr_qty == 0
    assert stored.status == "released"


def test_release_events_never_regress_status(client: TestClient, head_headers: dict[str, str]) -> None:
    po = make_po(client, head_headers, _project(client, head_headers), 10)
    _post(client, _event(po["po_no"], "gr_posted", quantity=10, event_id="GR-full"))
    assert sourcing._pos[po["po_no"]].status == "delivered"
    _post(client, _event(po["po_no"], "po_released", event_id="REL-late"))
    assert sourcing._pos[po["po_no"]].status == "delivered"

    pr = sourcing._prs[po["pr_no"]]
    assert pr.status == "po_created"
    _post(client, {**_event(pr.pr_no, "pr_released", event_id="PR-REL"), "sap_doc_no": "X", "ct_ref": pr.pr_no})
    assert sourcing._prs[pr.pr_no].status == "po_created"


def test_webhook_needs_token_outside_demo(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    body = _event("SPO-NOPE", "po_closed")
    monkeypatch.setenv("DEMO_LOGIN", "0")
    monkeypatch.delenv("SAP_WEBHOOK_TOKEN", raising=False)
    assert _post(client, body).status_code == 503

    monkeypatch.setenv("SAP_WEBHOOK_TOKEN", "cpi-test-token")
    assert _post(client, body).status_code == 401
    assert _post(client, body, **{"X-CPI-Token": "wrong"}).status_code == 401
    assert _post(client, body, **{"X-CPI-Token": "cpi-test-token"}).status_code == 200


def test_resync_is_tenant_scoped_and_mock_invents_nothing(
    client: TestClient, head_headers: dict[str, str], admin_headers: dict[str, str]
) -> None:
    from tests.conftest import headers_for_user

    po = make_po(client, head_headers, _project(client, head_headers), 10)
    sourcing._pos[po["po_no"]].sap_po_no = "4500000999"
    before = sourcing._pos[po["po_no"]].sap_gr_qty

    for _ in range(5):
        res = client.post("/api/integrations/sap/resync", headers=admin_headers)
        assert res.status_code == 200
    assert res.json()["mode"] == "mock"
    assert sourcing._pos[po["po_no"]].sap_gr_qty == before

    northwind = client.post("/api/integrations/sap/resync", headers=headers_for_user("northwind-admin-01")).json()
    arcforge_synced = sum(1 for p in sourcing._pos.values() if p.sap_po_no and p.tenant_id == "arcforge")
    assert res.json()["pos_reconciled"] == arcforge_synced
    assert northwind["pos_reconciled"] == sum(
        1 for p in sourcing._pos.values() if p.sap_po_no and p.tenant_id == "northwind"
    )


def test_short_closed_po_stays_delivered(client: TestClient, head_headers: dict[str, str]) -> None:
    po = make_po(client, head_headers, _project(client, head_headers), 10)
    _post(client, _event(po["po_no"], "gr_posted", quantity=8, event_id="GR-8"))
    assert sourcing._pos[po["po_no"]].status == "released"
    _post(client, _event(po["po_no"], "po_closed", event_id="CLOSE"))
    assert sourcing._pos[po["po_no"]].status == "delivered"

    # A later correction must not reopen a PO SAP closed short.
    _post(client, _event(po["po_no"], "gr_posted", quantity=-1, event_id="GR-8-REV1"))
    assert sourcing._pos[po["po_no"]].status == "delivered"
