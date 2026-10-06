"""One award (and one PO) per RFQ, server-side actor, honest approval status."""

from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient

from app import sourcing
from tests.conftest import TENANT


def _rfq_with_two_quotes(client: TestClient, headers: dict[str, str]) -> tuple[str, str, str]:
    """PR with a budget the quotes beat, two vendors quoting, so the cheaper
    quote is the comparison winner. Returns (rfq_no, cheap_quote, dear_quote)."""

    project = next(
        p for p in client.get("/api/projects", headers=headers).json()
        if p["project_id"].startswith("PRJ-AF")
    )
    code = f"AW-{uuid4().hex[:6].upper()}"
    pr = client.post(
        "/api/prs",
        headers=headers,
        json={
            "project_id": project["project_id"], "code": code, "description": "Award-once valve",
            "quantity": 10, "uom": "ea", "budget_value_usd": 900_000.0,
        },
    )
    assert pr.status_code == 200, pr.text
    vendors = [f"Vendor A {code}", f"Vendor B {code}"]
    rfq = client.post("/api/rfqs", headers=headers, json={"pr_no": pr.json()["pr_no"], "vendors": vendors})
    assert rfq.status_code == 200, rfq.text
    rfq_no = rfq.json()["rfq_no"]
    ids = []
    for vendor, price in zip(vendors, (6_000.0, 6_500.0)):
        q = client.post(
            f"/api/rfqs/{rfq_no}/quotes", headers=headers,
            json={"vendor": vendor, "unit_price_usd": price, "lead_time_days": 30, "quantity": 10},
        )
        assert q.status_code == 200, q.text
        assert q.json()["status"] == "applied", q.json()
        ids.append(q.json()["quote"]["quote_id"])
    return rfq_no, ids[0], ids[1]


def _awards_for(rfq_no: str) -> list:
    return [a for a in sourcing._awards.values() if a.rfq_no == rfq_no]


def test_second_award_on_same_rfq_is_refused(client: TestClient, head_headers: dict[str, str]) -> None:
    rfq_no, cheap, dear = _rfq_with_two_quotes(client, head_headers)

    first = client.post(f"/api/rfqs/{rfq_no}/award", headers=head_headers, json={"quote_id": cheap})
    assert first.status_code == 200
    assert first.json()["status"] == "applied"

    again = client.post(f"/api/rfqs/{rfq_no}/award", headers=head_headers, json={"quote_id": dear})
    assert again.status_code == 409
    assert len(_awards_for(rfq_no)) == 1


def test_awarded_by_comes_from_login_not_body(client: TestClient, head_headers: dict[str, str]) -> None:
    rfq_no, cheap, _ = _rfq_with_two_quotes(client, head_headers)
    res = client.post(
        f"/api/rfqs/{rfq_no}/award", headers=head_headers,
        json={"quote_id": cheap, "awarded_by": "CFO Jane Doe"},
    )
    assert res.status_code == 200
    award = res.json()["award"]
    assert award["awarded_by"] != "CFO Jane Doe"
    assert award["awarded_by"] == "Arcforge Procurement Head"


def test_duplicate_pending_award_request_is_refused(
    client: TestClient, head_headers: dict[str, str], buyer_headers: dict[str, str]
) -> None:
    rfq_no, _, dear = _rfq_with_two_quotes(client, head_headers)
    # Buyer picks the non-winner → needs approval.
    first = client.post(f"/api/rfqs/{rfq_no}/award", headers=buyer_headers, json={"quote_id": dear})
    assert first.status_code == 200
    assert first.json()["status"] == "pending_approval"

    second = client.post(f"/api/rfqs/{rfq_no}/award", headers=buyer_headers, json={"quote_id": dear})
    assert second.status_code == 409


def test_stale_approval_fails_instead_of_creating_second_po(
    client: TestClient, head_headers: dict[str, str], buyer_headers: dict[str, str]
) -> None:
    rfq_no, cheap, dear = _rfq_with_two_quotes(client, head_headers)
    pending = client.post(f"/api/rfqs/{rfq_no}/award", headers=buyer_headers, json={"quote_id": dear})
    approval_id = pending.json()["approval"]["approval_id"]

    # Meanwhile the head awards the RFQ directly.
    direct = client.post(f"/api/rfqs/{rfq_no}/award", headers=head_headers, json={"quote_id": cheap})
    # The head's own award is blocked while a request is pending...
    assert direct.status_code == 409
    # ...so simulate the race the guard exists for: award lands via sourcing.
    from app.schemas import AwardRFQRequest
    sourcing.award_rfq(rfq_no, AwardRFQRequest(quote_id=cheap), tenant_id=TENANT)

    decided = client.post(f"/api/approvals/{approval_id}/approve", headers=head_headers)
    assert decided.status_code == 200
    body = decided.json()
    assert body["status"] == "failed"
    assert "already awarded" in body["decision_note"]
    assert len(_awards_for(rfq_no)) == 1

    from app import audit
    assert any(
        e.action == "commit_failed" and e.entity_id == approval_id for e in audit._events
    ), "the failed decision must be in the audit trail"
