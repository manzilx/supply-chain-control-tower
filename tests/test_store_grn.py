"""Storemark field-capture API tests: enrolment, sync idempotency, matching
degrade paths, office/device confirm parity, revocation, RBAC scoping, and
the downstream (ledger/PO/audit/expediting) effects of a confirmed GRN.

XAI_API_KEY is popped for the whole module so every GRN takes the
extraction-off ("skipped") path: matching.apply_bands() runs synchronously
inside create_from_sync(), so there is nothing async to await in a test.
"""

from __future__ import annotations

import hashlib
import itertools
import json
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from tests.conftest import TENANT


STOREKEEPER_ID = f"{TENANT}-store-01"

_seq_counter = itertools.count(1)


@pytest.fixture(autouse=True)
def _no_xai_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Extraction must always take the LLM-off path so matching runs
    synchronously and deterministically for every test in this module."""
    monkeypatch.delenv("XAI_API_KEY", raising=False)


# --- Shared helpers -----------------------------------------------------------


def make_store(client: TestClient, admin_headers: dict[str, str]) -> str:
    projects = client.get("/api/projects", headers=admin_headers)
    assert projects.status_code == 200
    project = projects.json()[0]
    res = client.post(
        "/api/store/stores",
        headers=admin_headers,
        json={"project_id": project["project_id"], "name": f"Site Store {uuid4().hex[:10]}"},
    )
    assert res.status_code == 200
    return res.json()["store_id"]


def enrol(
    client: TestClient,
    admin_headers: dict[str, str],
    store_id: str,
    role: str = "storekeeper",
) -> tuple[dict[str, str], str]:
    invite = client.post(
        "/api/field-admin/enrolments",
        headers=admin_headers,
        json={"store_id": store_id, "person_name": f"Field Tester {uuid4().hex[:6]}", "person_role": role},
    )
    assert invite.status_code == 200
    device_id = uuid4().hex
    reply = client.post(
        "/api/v1/field/enrol",
        json={"code": invite.json()["code"], "device_id": device_id, "model": "pytest-rig", "app_version": "1.0.0"},
    )
    assert reply.status_code == 200
    token = reply.json()["token"]
    return {"Authorization": f"Bearer {token}"}, device_id


def sync_grn(
    client: TestClient,
    device_headers: dict[str, str],
    lines: Optional[list[dict]] = None,
    photo: bytes = b"fake-jpeg-bytes",
    **overrides,
):
    grn_id = overrides.pop("grn_id", uuid4().hex)
    sequence_no = overrides.pop("sequence_no", next(_seq_counter))
    record = {
        "grn_id": grn_id,
        "sequence_no": sequence_no,
        "source_kind": "contractor",
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "photo_sha256": hashlib.sha256(photo).hexdigest(),
        "challan_no": f"CH-{grn_id[:8]}",
        "lines": lines if lines is not None else [
            {
                "line_no": 1,
                "description_raw": "Misc site material",
                "qty_received": 10.0,
                "uom_raw": "EA",
            }
        ],
    }
    record.update(overrides)
    return client.post(
        "/api/v1/field/grns",
        headers=device_headers,
        files={"photo": ("challan.jpg", photo, "image/jpeg")},
        data={"record": json.dumps(record)},
    )


def make_po(
    client: TestClient,
    head_headers: dict[str, str],
    project_id: str,
    quantity: float,
    *,
    bom_item_id: Optional[str] = None,
    code: Optional[str] = None,
    description: Optional[str] = None,
    uom: str = "EA",
    vendor: Optional[str] = None,
    unit_price: float = 100.0,
) -> dict:
    """Walk PR -> RFQ -> quote -> award -> PO as procurement_head (who can
    self-approve every gate), then release the PO via the SAP-CPI inbound
    webhook so it lands in the (released, in_transit) matching pool. Returns
    the SourcingPO dict from the award reply (status is still 'draft' there
    — callers re-fetch /api/sourcing-pos/{po_no} for the post-release state).
    """
    vendor = vendor or f"Storemark Vendor {uuid4().hex[:6]}"
    pr_body: dict = {"project_id": project_id, "quantity": quantity, "uom": uom}
    if bom_item_id:
        pr_body["bom_item_id"] = bom_item_id
    else:
        pr_body["code"] = code or f"SM-{uuid4().hex[:8].upper()}"
        pr_body["description"] = description or "Storemark test material"
    pr_res = client.post("/api/prs", headers=head_headers, json=pr_body)
    assert pr_res.status_code == 200
    pr_no = pr_res.json()["pr_no"]

    rfq_res = client.post(
        "/api/rfqs", headers=head_headers,
        json={"pr_no": pr_no, "vendors": [vendor], "due_in_days": 10},
    )
    assert rfq_res.status_code == 200
    rfq_no = rfq_res.json()["rfq_no"]

    quote_res = client.post(
        f"/api/rfqs/{rfq_no}/quotes", headers=head_headers,
        json={"vendor": vendor, "unit_price_usd": unit_price, "lead_time_days": 30, "quantity": quantity},
    )
    assert quote_res.status_code == 200
    quote_reply = quote_res.json()
    assert quote_reply["status"] == "applied"
    quote_id = quote_reply["quote"]["quote_id"]

    award_res = client.post(
        f"/api/rfqs/{rfq_no}/award", headers=head_headers,
        json={"quote_id": quote_id, "rationale": "Storemark test award"},
    )
    assert award_res.status_code == 200
    award_reply = award_res.json()
    assert award_reply["status"] == "applied"
    po = award_reply["po"]
    assert po is not None

    release_res = client.post(
        "/api/integrations/sap/event",
        json={
            "kind": "po_released",
            "sap_doc_no": po["po_no"],
            "ct_ref": po["po_no"],
            "occurred_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    assert release_res.status_code == 200
    assert release_res.json()["accepted"] is True

    return po


# --- 1. Enrolment flow ---------------------------------------------------------


def test_enrolment_flow_context_has_no_pricing_and_invite_is_single_use(
    client: TestClient,
    admin_headers: dict[str, str],
) -> None:
    store_id = make_store(client, admin_headers)
    device_headers, _device_id = enrol(client, admin_headers, store_id)

    ctx = client.get("/api/v1/field/context", headers=device_headers)
    assert ctx.status_code == 200
    body = ctx.json()
    assert "pos" in body
    assert isinstance(body["pos"], list)
    for po in body["pos"]:
        for key in po:
            lowered = key.lower()
            assert "price" not in lowered, f"pricing field leaked to field device: {key}"
            assert "value_usd" not in lowered, f"value field leaked to field device: {key}"

    invite = client.post(
        "/api/field-admin/enrolments",
        headers=admin_headers,
        json={"store_id": store_id, "person_name": "Reuse Tester", "person_role": "storekeeper"},
    )
    assert invite.status_code == 200
    code = invite.json()["code"]

    first = client.post("/api/v1/field/enrol", json={"code": code, "device_id": uuid4().hex})
    assert first.status_code == 200

    reused = client.post("/api/v1/field/enrol", json={"code": code, "device_id": uuid4().hex})
    assert 400 <= reused.status_code < 500


# --- 2. Sync idempotency -------------------------------------------------------


def test_sync_idempotency_and_single_ledger_row(
    client: TestClient,
    admin_headers: dict[str, str],
) -> None:
    store_id = make_store(client, admin_headers)
    device_headers, _ = enrol(client, admin_headers, store_id)

    grn_id = uuid4().hex
    code = f"IDEMP-{uuid4().hex[:8]}"
    lines = [{"line_no": 1, "description_raw": "Cement bags", "code": code, "qty_received": 20.0, "uom_raw": "BAG"}]

    first = sync_grn(client, device_headers, lines=lines, grn_id=grn_id, sequence_no=1)
    assert first.status_code == 200
    assert first.json()["duplicate"] is False

    second = sync_grn(client, device_headers, lines=lines, grn_id=grn_id, sequence_no=1)
    assert second.status_code == 200
    assert second.json()["duplicate"] is True

    confirm = client.post(
        f"/api/store/grns/{grn_id}/confirm",
        headers=admin_headers,
        json={"lines": [{"line_no": 1, "no_po": True, "qty_received": 20.0}]},
    )
    assert confirm.status_code == 200

    ledger = client.get(
        f"/api/store/stock/{code}/ledger", headers=admin_headers, params={"store_id": store_id}
    )
    assert ledger.status_code == 200
    matching_rows = [r for r in ledger.json() if r["ref_id"] == grn_id]
    assert len(matching_rows) == 1


# --- 3. sha256 mismatch ---------------------------------------------------------


def test_photo_sha256_mismatch_rejected_and_nothing_persisted(
    client: TestClient,
    admin_headers: dict[str, str],
) -> None:
    store_id = make_store(client, admin_headers)
    device_headers, _ = enrol(client, admin_headers, store_id)

    grn_id = uuid4().hex
    res = sync_grn(client, device_headers, grn_id=grn_id, photo_sha256="0" * 64)
    assert res.status_code == 422

    office = client.get(f"/api/store/grns/{grn_id}", headers=admin_headers)
    assert office.status_code == 404


# --- 4. Manual-keyed degrade ----------------------------------------------------


def test_manual_keyed_lines_skip_extraction_and_confirm_succeeds(
    client: TestClient,
    admin_headers: dict[str, str],
) -> None:
    store_id = make_store(client, admin_headers)
    device_headers, _ = enrol(client, admin_headers, store_id)

    lines = [{"line_no": 1, "description_raw": "Unmatched widget", "qty_received": 5.0, "uom_raw": "EA"}]
    sync_res = sync_grn(client, device_headers, lines=lines)
    assert sync_res.status_code == 200
    grn_id = sync_res.json()["grn_id"]

    detail = client.get(f"/api/store/grns/{grn_id}", headers=admin_headers)
    assert detail.status_code == 200
    assert detail.json()["extraction_status"] == "skipped"

    confirm = client.post(
        f"/api/v1/field/grns/{grn_id}/confirm",
        headers=device_headers,
        json={"lines": [{"line_no": 1, "no_po": True, "qty_received": 5.0}]},
    )
    assert confirm.status_code == 200


# --- 5. Full loop: PO delivery, audit trail, expediting, partial-then-full ------


def test_full_loop_delivers_po_and_partial_then_full_delivery(
    client: TestClient,
    admin_headers: dict[str, str],
    head_headers: dict[str, str],
) -> None:
    store_id = make_store(client, admin_headers)
    device_headers, _ = enrol(client, admin_headers, store_id)

    projects = client.get("/api/projects", headers=admin_headers)
    assert projects.status_code == 200
    project_id = projects.json()[0]["project_id"]

    bom = client.get(f"/api/projects/{project_id}/bom", headers=admin_headers)
    assert bom.status_code == 200
    bom_item = bom.json()[0]

    # --- Primary PO: single GRN delivers the full quantity -----------------
    po1 = make_po(client, head_headers, project_id, quantity=12.0, bom_item_id=bom_item["bom_item_id"])
    po1_no = po1["po_no"]

    sync1 = sync_grn(
        client, device_headers,
        lines=[{
            "line_no": 1, "description_raw": po1["description"], "code": po1["code"],
            "uom_raw": po1["uom"], "qty_received": 12.0,
        }],
        vendor_name_raw=po1["vendor"],
    )
    assert sync1.status_code == 200
    grn1_id = sync1.json()["grn_id"]

    confirm1 = client.post(
        f"/api/v1/field/grns/{grn1_id}/confirm",
        headers=device_headers,
        json={"lines": [{"line_no": 1, "po_no": po1_no, "qty_received": 12.0}]},
    )
    assert confirm1.status_code == 200
    assert po1_no in confirm1.json()["pos_delivered"]

    po1_after = client.get(f"/api/sourcing-pos/{po1_no}", headers=head_headers)
    assert po1_after.status_code == 200
    po1_after_body = po1_after.json()
    assert po1_after_body["ct_gr_qty"] == 12.0
    assert po1_after_body["status"] == "delivered"

    trace = client.get(f"/api/audit/trace/po/{po1_no}", headers=head_headers)
    assert trace.status_code == 200
    assert "grn_confirmed" in trace.text
    assert "gr_posted" in trace.text
    # ...and specifically because the site_grn stage carries both events.
    site_grn = next(s for s in trace.json()["stages"] if s["stage"] == "site_grn")
    assert site_grn["payload"]["ct_gr_qty"] == 12.0
    assert site_grn["complete"] is True
    assert {e["action"] for e in site_grn["payload"]["events"]} == {"gr_posted", "grn_confirmed"}

    queue = client.get("/api/expediting/queue", headers=head_headers)
    assert queue.status_code == 200
    assert all(item["po_number"] != po1_no for item in queue.json()["items"])

    # --- Second PO: two half-quantity GRNs -> released/in_transit, then delivered
    po2 = make_po(
        client, head_headers, project_id, quantity=20.0,
        code=f"SM-PARTIAL-{uuid4().hex[:6]}", description="Storemark partial-delivery test material",
    )
    po2_no = po2["po_no"]

    sync2a = sync_grn(
        client, device_headers,
        lines=[{
            "line_no": 1, "description_raw": po2["description"], "code": po2["code"],
            "uom_raw": po2["uom"], "qty_received": 10.0,
        }],
        vendor_name_raw=po2["vendor"],
    )
    assert sync2a.status_code == 200
    grn2a_id = sync2a.json()["grn_id"]
    confirm2a = client.post(
        f"/api/v1/field/grns/{grn2a_id}/confirm",
        headers=device_headers,
        json={"lines": [{"line_no": 1, "po_no": po2_no, "qty_received": 10.0}]},
    )
    assert confirm2a.status_code == 200
    assert po2_no not in confirm2a.json()["pos_delivered"]

    po2_mid = client.get(f"/api/sourcing-pos/{po2_no}", headers=head_headers).json()
    assert po2_mid["ct_gr_qty"] == 10.0
    assert po2_mid["status"] in ("released", "in_transit")

    sync2b = sync_grn(
        client, device_headers,
        lines=[{
            "line_no": 1, "description_raw": po2["description"], "code": po2["code"],
            "uom_raw": po2["uom"], "qty_received": 10.0,
        }],
        vendor_name_raw=po2["vendor"],
    )
    assert sync2b.status_code == 200
    grn2b_id = sync2b.json()["grn_id"]
    confirm2b = client.post(
        f"/api/v1/field/grns/{grn2b_id}/confirm",
        headers=device_headers,
        json={"lines": [{"line_no": 1, "po_no": po2_no, "qty_received": 10.0}]},
    )
    assert confirm2b.status_code == 200
    assert po2_no in confirm2b.json()["pos_delivered"]

    po2_final = client.get(f"/api/sourcing-pos/{po2_no}", headers=head_headers).json()
    assert po2_final["ct_gr_qty"] == 20.0
    assert po2_final["status"] == "delivered"


# --- 6. Office-first conflict, then identical-content replay -------------------


def test_office_confirm_then_device_conflict_then_identical_replay(
    client: TestClient,
    admin_headers: dict[str, str],
) -> None:
    store_id = make_store(client, admin_headers)
    device_headers, _ = enrol(client, admin_headers, store_id)

    lines = [{"line_no": 1, "description_raw": "Conflict widget", "qty_received": 5.0, "uom_raw": "EA"}]
    sync_res = sync_grn(client, device_headers, lines=lines)
    assert sync_res.status_code == 200
    grn_id = sync_res.json()["grn_id"]

    office_confirm = client.post(
        f"/api/store/grns/{grn_id}/confirm",
        headers=admin_headers,
        json={"lines": [{"line_no": 1, "no_po": True, "qty_received": 5.0}]},
    )
    assert office_confirm.status_code == 200

    device_conflict = client.post(
        f"/api/v1/field/grns/{grn_id}/confirm",
        headers=device_headers,
        json={"lines": [{"line_no": 1, "no_po": True, "qty_received": 7.0}]},
    )
    assert device_conflict.status_code == 409

    device_replay = client.post(
        f"/api/v1/field/grns/{grn_id}/confirm",
        headers=device_headers,
        json={"lines": [{"line_no": 1, "no_po": True, "qty_received": 5.0}]},
    )
    assert device_replay.status_code == 200
    assert device_replay.json()["status"] == "confirmed"


# --- 7. Revocation ---------------------------------------------------------------


def test_revoked_device_forbidden_on_field_routes(
    client: TestClient,
    admin_headers: dict[str, str],
) -> None:
    store_id = make_store(client, admin_headers)
    device_headers, device_id = enrol(client, admin_headers, store_id)

    revoke = client.post(f"/api/field-admin/devices/{device_id}/revoke", headers=admin_headers)
    assert revoke.status_code == 200

    ctx = client.get("/api/v1/field/context", headers=device_headers)
    assert ctx.status_code == 403


# --- 8. Foreman device is not a storekeeper -------------------------------------


def test_foreman_device_forbidden_from_storekeeper_routes(
    client: TestClient,
    admin_headers: dict[str, str],
) -> None:
    store_id = make_store(client, admin_headers)
    device_headers, _ = enrol(client, admin_headers, store_id, role="foreman")

    ctx = client.get("/api/v1/field/context", headers=device_headers)
    assert ctx.status_code == 403

    sync_res = sync_grn(client, device_headers)
    assert sync_res.status_code == 403


# --- 9. Storekeeper JWT is scoped, not a device token ---------------------------


def test_storekeeper_jwt_scoped_permissions(
    client: TestClient,
    login,
    head_headers: dict[str, str],
) -> None:
    headers = login(STOREKEEPER_ID)

    rfqs = client.get("/api/rfqs", headers=headers)
    assert rfqs.status_code == 403

    grns = client.get("/api/store/grns", headers=headers)
    assert grns.status_code == 200

    # Storekeeper is the first role without '*:read' — the commercial reads
    # must be permission-guarded, not merely authenticated.
    assert client.get("/api/rfqs/RFQ-00001/quotes", headers=headers).status_code == 403
    assert client.get("/api/awards", headers=headers).status_code == 403
    assert client.get("/api/awards", headers=head_headers).status_code == 200


# --- 10. Free-issue credits free_issue_qty, not contractor_qty -----------------


def test_free_issue_credits_free_issue_qty_not_contractor(
    client: TestClient,
    admin_headers: dict[str, str],
) -> None:
    store_id = make_store(client, admin_headers)
    device_headers, _ = enrol(client, admin_headers, store_id)

    code = f"FREE-{uuid4().hex[:8]}"
    lines = [{
        "line_no": 1, "description_raw": "Owner-supplied cable", "code": code,
        "qty_received": 15.0, "uom_raw": "M",
    }]
    sync_res = sync_grn(client, device_headers, lines=lines, source_kind="free_issue")
    assert sync_res.status_code == 200
    grn_id = sync_res.json()["grn_id"]

    detail = client.get(f"/api/store/grns/{grn_id}", headers=admin_headers)
    assert detail.status_code == 200
    for line in detail.json()["lines"]:
        assert line["match_status"] == "no_po"

    confirm = client.post(
        f"/api/store/grns/{grn_id}/confirm",
        headers=admin_headers,
        json={"lines": [{"line_no": 1, "no_po": True, "qty_received": 15.0}]},
    )
    assert confirm.status_code == 200

    stock = client.get("/api/store/stock", headers=admin_headers, params={"store_id": store_id})
    assert stock.status_code == 200
    row = next(r for r in stock.json() if r["code"] == code)
    assert row["free_issue_qty"] == 15.0
    assert row["contractor_qty"] == 0.0


# --- 11. Damaged quantity never enters stock ------------------------------------


def test_damaged_qty_excluded_from_ledger_and_stock(
    client: TestClient,
    admin_headers: dict[str, str],
) -> None:
    store_id = make_store(client, admin_headers)
    device_headers, _ = enrol(client, admin_headers, store_id)

    code = f"DMG-{uuid4().hex[:8]}"
    lines = [{
        "line_no": 1, "description_raw": "Damaged crate", "code": code,
        "qty_received": 10.0, "qty_damaged": 2.0, "uom_raw": "EA",
    }]
    sync_res = sync_grn(client, device_headers, lines=lines)
    assert sync_res.status_code == 200
    grn_id = sync_res.json()["grn_id"]

    confirm = client.post(
        f"/api/store/grns/{grn_id}/confirm",
        headers=admin_headers,
        json={"lines": [{"line_no": 1, "no_po": True, "qty_received": 10.0, "qty_damaged": 2.0}]},
    )
    assert confirm.status_code == 200

    ledger = client.get(
        f"/api/store/stock/{code}/ledger", headers=admin_headers, params={"store_id": store_id}
    )
    assert ledger.status_code == 200
    rows = ledger.json()
    assert len(rows) == 1
    assert rows[0]["qty_signed"] == 10.0

    stock = client.get("/api/store/stock", headers=admin_headers, params={"store_id": store_id})
    assert stock.status_code == 200
    row = next(r for r in stock.json() if r["code"] == code)
    assert row["total_qty"] == 10.0


# --- 12. Omitted confirm lines keep their captured quantities -------------------


def test_omitted_confirm_line_keeps_qty_and_still_enters_ledger(
    client: TestClient,
    admin_headers: dict[str, str],
) -> None:
    """A partial confirm must not zero the lines it leaves out: captured
    quantities are claims evidence, and unmatched stock is still stock."""
    store_id = make_store(client, admin_headers)
    device_headers, _ = enrol(client, admin_headers, store_id)

    kept_code = f"KEEP-{uuid4().hex[:8]}"
    omitted_code = f"OMIT-{uuid4().hex[:8]}"
    sync_res = sync_grn(client, device_headers, lines=[
        {"line_no": 1, "description_raw": "Submitted widget", "code": kept_code,
         "qty_received": 4.0, "uom_raw": "EA"},
        {"line_no": 2, "description_raw": "Omitted widget", "code": omitted_code,
         "qty_received": 6.0, "qty_damaged": 1.0, "uom_raw": "EA"},
    ])
    assert sync_res.status_code == 200
    grn_id = sync_res.json()["grn_id"]

    subset = {"lines": [{"line_no": 1, "no_po": True, "qty_received": 4.0}]}
    confirm = client.post(f"/api/store/grns/{grn_id}/confirm", headers=admin_headers, json=subset)
    assert confirm.status_code == 200
    assert confirm.json()["ledger_entries"] == 2

    detail = client.get(f"/api/store/grns/{grn_id}", headers=admin_headers)
    assert detail.status_code == 200
    omitted = next(l for l in detail.json()["lines"] if l["line_no"] == 2)
    assert omitted["qty_received"] == 6.0
    assert omitted["qty_damaged"] == 1.0
    assert omitted["match_status"] == "no_po"
    assert omitted["po_no"] is None

    ledger = client.get(
        f"/api/store/stock/{omitted_code}/ledger", headers=admin_headers,
        params={"store_id": store_id},
    )
    assert ledger.status_code == 200
    rows = [r for r in ledger.json() if r["ref_id"] == grn_id]
    assert len(rows) == 1
    assert rows[0]["qty_signed"] == 6.0

    # Replaying the same subset matches the stored state (omitted lines
    # normalise identically on both sides); changing it conflicts.
    replay = client.post(f"/api/store/grns/{grn_id}/confirm", headers=admin_headers, json=subset)
    assert replay.status_code == 200
    assert replay.json()["status"] == "confirmed"

    conflict = client.post(
        f"/api/store/grns/{grn_id}/confirm",
        headers=admin_headers,
        json={"lines": [{"line_no": 1, "no_po": True, "qty_received": 4.0},
                        {"line_no": 2, "no_po": True, "qty_received": 3.0}]},
    )
    assert conflict.status_code == 409


# --- 13. Confirm rejects a line_no that is not on the GRN -----------------------


def test_confirm_unknown_line_no_rejected(
    client: TestClient,
    admin_headers: dict[str, str],
) -> None:
    store_id = make_store(client, admin_headers)
    device_headers, _ = enrol(client, admin_headers, store_id)

    sync_res = sync_grn(client, device_headers)
    assert sync_res.status_code == 200
    grn_id = sync_res.json()["grn_id"]

    confirm = client.post(
        f"/api/store/grns/{grn_id}/confirm",
        headers=admin_headers,
        json={"lines": [{"line_no": 99, "no_po": True, "qty_received": 1.0}]},
    )
    assert confirm.status_code == 422

    detail = client.get(f"/api/store/grns/{grn_id}", headers=admin_headers)
    assert detail.json()["status"] != "confirmed"


# --- 14. Re-enrolment of a reinstalled device ----------------------------------


def test_reenrol_same_device_rotates_token_and_keeps_sequence_watermark(
    client: TestClient,
    admin_headers: dict[str, str],
) -> None:
    store_id = make_store(client, admin_headers)
    device_headers, device_id = enrol(client, admin_headers, store_id)

    sequence_no = next(_seq_counter)
    assert sync_grn(client, device_headers, sequence_no=sequence_no).status_code == 200

    revoke = client.post(f"/api/field-admin/devices/{device_id}/revoke", headers=admin_headers)
    assert revoke.status_code == 200
    assert client.get("/api/v1/field/context", headers=device_headers).status_code == 403

    invite = client.post(
        "/api/field-admin/enrolments",
        headers=admin_headers,
        json={"store_id": store_id, "person_name": "Reinstall Tester", "person_role": "storekeeper"},
    )
    assert invite.status_code == 200
    again = client.post(
        "/api/v1/field/enrol",
        json={"code": invite.json()["code"], "device_id": device_id, "app_version": "1.0.1"},
    )
    assert again.status_code == 200
    body = again.json()
    assert body["last_sequence_no"] == sequence_no

    new_headers = {"Authorization": f"Bearer {body['token']}"}
    assert new_headers["Authorization"] != device_headers["Authorization"]
    assert client.get("/api/v1/field/context", headers=new_headers).status_code == 200
    # The rotated-away token is dead.
    assert client.get("/api/v1/field/context", headers=device_headers).status_code == 401


# --- 15. Negative quantities are rejected at sync -------------------------------


def test_negative_qty_in_sync_record_rejected(
    client: TestClient,
    admin_headers: dict[str, str],
) -> None:
    store_id = make_store(client, admin_headers)
    device_headers, _ = enrol(client, admin_headers, store_id)

    grn_id = uuid4().hex
    res = sync_grn(
        client, device_headers, grn_id=grn_id,
        lines=[{"line_no": 1, "description_raw": "Negative widget",
                "qty_received": -5.0, "uom_raw": "EA"}],
    )
    assert res.status_code == 422

    office = client.get(f"/api/store/grns/{grn_id}", headers=admin_headers)
    assert office.status_code == 404


# --- 16. over_receipt flag --------------------------------------------------------


def test_over_receipt_set_only_when_qty_exceeds_po_headroom(
    client: TestClient,
    admin_headers: dict[str, str],
    head_headers: dict[str, str],
) -> None:
    store_id = make_store(client, admin_headers)
    device_headers, _ = enrol(client, admin_headers, store_id)

    projects = client.get("/api/projects", headers=admin_headers)
    assert projects.status_code == 200
    project_id = projects.json()[0]["project_id"]

    # remaining_qty = quantity * 1.05 headroom, so 12 > 10.5 is an over-receipt.
    over_po = make_po(
        client, head_headers, project_id, quantity=10.0,
        code=f"SM-OVER-{uuid4().hex[:6]}", description="Storemark over-receipt test material",
    )
    over_sync = sync_grn(
        client, device_headers,
        lines=[{"line_no": 1, "description_raw": over_po["description"], "code": over_po["code"],
                "uom_raw": over_po["uom"], "qty_received": 12.0}],
        vendor_name_raw=over_po["vendor"],
    )
    assert over_sync.status_code == 200
    over_grn_id = over_sync.json()["grn_id"]
    over_confirm = client.post(
        f"/api/store/grns/{over_grn_id}/confirm",
        headers=admin_headers,
        json={"lines": [{"line_no": 1, "po_no": over_po["po_no"], "qty_received": 12.0}]},
    )
    assert over_confirm.status_code == 200
    over_detail = client.get(f"/api/store/grns/{over_grn_id}", headers=admin_headers)
    assert over_detail.json()["lines"][0]["over_receipt"] is True

    # Receiving exactly the ordered quantity is inside the headroom.
    exact_po = make_po(
        client, head_headers, project_id, quantity=10.0,
        code=f"SM-EXACT-{uuid4().hex[:6]}", description="Storemark exact-receipt test material",
    )
    exact_sync = sync_grn(
        client, device_headers,
        lines=[{"line_no": 1, "description_raw": exact_po["description"], "code": exact_po["code"],
                "uom_raw": exact_po["uom"], "qty_received": 10.0}],
        vendor_name_raw=exact_po["vendor"],
    )
    assert exact_sync.status_code == 200
    exact_grn_id = exact_sync.json()["grn_id"]
    exact_confirm = client.post(
        f"/api/store/grns/{exact_grn_id}/confirm",
        headers=admin_headers,
        json={"lines": [{"line_no": 1, "po_no": exact_po["po_no"], "qty_received": 10.0}]},
    )
    assert exact_confirm.status_code == 200
    exact_detail = client.get(f"/api/store/grns/{exact_grn_id}", headers=admin_headers)
    assert exact_detail.json()["lines"][0]["over_receipt"] is False


# --- 17. Extraction never overwrites a GRN confirmed mid-flight ----------------


def test_extraction_result_discarded_when_confirm_lands_first(
    client: TestClient,
    admin_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The vision call takes seconds; a confirm inside that window wins."""
    import asyncio

    from app import llm
    from app.store import extraction

    store_id = make_store(client, admin_headers)
    device_headers, _ = enrol(client, admin_headers, store_id)

    # This one GRN takes the extraction-on path (the module default is off).
    monkeypatch.setenv("XAI_API_KEY", "test-key")
    sync_res = sync_grn(client, device_headers, lines=[
        {"line_no": 1, "description_raw": "Race widget", "code": f"RACE-{uuid4().hex[:8]}",
         "qty_received": 3.0, "uom_raw": "EA"},
    ])
    assert sync_res.status_code == 200
    grn_id = sync_res.json()["grn_id"]

    def _confirm_then_extract(_system: str, _user: str, _photo_path: str) -> dict:
        confirm = client.post(
            f"/api/store/grns/{grn_id}/confirm",
            headers=admin_headers,
            json={"lines": [{"line_no": 1, "no_po": True, "qty_received": 3.0}]},
        )
        assert confirm.status_code == 200
        return {
            "challan_no": "CH-FROM-MODEL", "vendor_name": "Model Vendor",
            "lines": [{"description": "model line", "qty": 999, "uom": "EA"}],
        }

    monkeypatch.setattr(llm, "grok_vision_json", _confirm_then_extract)
    asyncio.run(extraction.run_extraction(grn_id))

    detail = client.get(f"/api/store/grns/{grn_id}", headers=admin_headers)
    assert detail.status_code == 200
    body = detail.json()
    assert body["status"] == "confirmed"
    assert body["vendor_name_raw"] != "Model Vendor"
    assert [l["qty_received"] for l in body["lines"]] == [3.0]
    # The confirm closed out the in-flight extraction rather than stranding
    # the header at extraction_status='running' forever.
    assert body["extraction_status"] == "skipped"


# --- 18. Two lines on one PO are one delivery ----------------------------------


def test_two_lines_against_one_po_report_it_once(
    client: TestClient,
    admin_headers: dict[str, str],
    head_headers: dict[str, str],
) -> None:
    store_id = make_store(client, admin_headers)
    device_headers, _ = enrol(client, admin_headers, store_id)

    projects = client.get("/api/projects", headers=admin_headers)
    assert projects.status_code == 200
    project_id = projects.json()[0]["project_id"]

    po = make_po(
        client, head_headers, project_id, quantity=20.0,
        code=f"SM-SPLIT-{uuid4().hex[:6]}", description="Storemark split-across-lines material",
    )
    sync_res = sync_grn(
        client, device_headers,
        lines=[
            {"line_no": 1, "description_raw": po["description"], "code": po["code"],
             "uom_raw": po["uom"], "qty_received": 10.0},
            {"line_no": 2, "description_raw": po["description"], "code": po["code"],
             "uom_raw": po["uom"], "qty_received": 10.0},
        ],
        vendor_name_raw=po["vendor"],
    )
    assert sync_res.status_code == 200
    grn_id = sync_res.json()["grn_id"]

    confirm = client.post(
        f"/api/store/grns/{grn_id}/confirm",
        headers=admin_headers,
        json={"lines": [
            {"line_no": 1, "po_no": po["po_no"], "qty_received": 10.0},
            {"line_no": 2, "po_no": po["po_no"], "qty_received": 10.0},
        ]},
    )
    assert confirm.status_code == 200
    body = confirm.json()
    assert body["pos_updated"] == [po["po_no"]]
    assert body["pos_delivered"] == [po["po_no"]]

    po_after = client.get(f"/api/sourcing-pos/{po['po_no']}", headers=head_headers).json()
    assert po_after["ct_gr_qty"] == 20.0
    assert po_after["status"] == "delivered"


# --- 19. Startup sweep is gated on effects_applied_at, not on an audit event ----


def test_startup_sweep_skips_stamped_grns_and_resumes_unstamped_ones(
    client: TestClient,
    admin_headers: dict[str, str],
    head_headers: dict[str, str],
) -> None:
    from app.store import db as store_db, grn as grn_mod

    store_id = make_store(client, admin_headers)
    device_headers, _ = enrol(client, admin_headers, store_id)

    projects = client.get("/api/projects", headers=admin_headers)
    assert projects.status_code == 200
    project_id = projects.json()[0]["project_id"]

    po = make_po(
        client, head_headers, project_id, quantity=50.0,
        code=f"SM-SWEEP-{uuid4().hex[:6]}", description="Storemark sweep test material",
    )
    sync_res = sync_grn(
        client, device_headers,
        lines=[{"line_no": 1, "description_raw": po["description"], "code": po["code"],
                "uom_raw": po["uom"], "qty_received": 12.0}],
        vendor_name_raw=po["vendor"],
    )
    assert sync_res.status_code == 200
    grn_id = sync_res.json()["grn_id"]
    assert client.post(
        f"/api/store/grns/{grn_id}/confirm",
        headers=admin_headers,
        json={"lines": [{"line_no": 1, "po_no": po["po_no"], "qty_received": 12.0}]},
    ).status_code == 200

    def ct_gr_qty() -> float:
        return client.get(f"/api/sourcing-pos/{po['po_no']}", headers=head_headers).json()["ct_gr_qty"]

    def effects_stamp() -> Optional[str]:
        conn = store_db.connect()
        try:
            return conn.execute(
                "SELECT effects_applied_at FROM grn WHERE grn_id = ?", (grn_id,)
            ).fetchone()["effects_applied_at"]
        finally:
            conn.close()

    assert ct_gr_qty() == 12.0
    assert effects_stamp() is not None

    # A stamped GRN is never re-applied, however empty the audit ring buffer is.
    grn_mod.startup_sweep()
    assert ct_gr_qty() == 12.0

    # Simulate a crash between the SQLite commit and the dict-store phase: the
    # stamp is missing, so the sweep must land the effects (and stamp them).
    conn = store_db.connect()
    try:
        conn.execute("UPDATE grn SET effects_applied_at = NULL WHERE grn_id = ?", (grn_id,))
        conn.commit()
    finally:
        conn.close()

    grn_mod.startup_sweep()
    assert ct_gr_qty() == 24.0
    assert effects_stamp() is not None
