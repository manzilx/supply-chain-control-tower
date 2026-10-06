"""Re-uploads update the lines they name; nothing is overwritten by position.
Also: spreadsheet suppliers go through vendor approval, and vendors without
real performance data are flagged, capped and never recommended."""

from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient

from app import approvals, planning, vendor_intel, vendor_store
from tests.conftest import TENANT


def _project(client: TestClient, headers: dict[str, str]) -> str:
    return next(
        p["project_id"] for p in client.get("/api/projects", headers=headers).json()
        if p["project_id"].startswith("PRJ-AF")
    )


def _upload(client: TestClient, headers: dict[str, str], pid: str, csv_text: str) -> dict:
    res = client.post(
        f"/api/projects/{pid}/bom/upload", headers=headers,
        files={"file": ("bom.csv", csv_text.encode(), "text/csv")},
    )
    assert res.status_code == 200, res.text
    return res.json()


def _lines(pid: str, code: str) -> list:
    return [i for i in planning._bom_items[pid].values() if i.code == code]


def test_second_file_adds_lines_instead_of_overwriting(client: TestClient, head_headers: dict[str, str]) -> None:
    pid = _project(client, head_headers)
    tag = uuid4().hex[:5].upper()
    before = len(planning._bom_items[pid])
    _upload(client, head_headers, pid, f"code,description,quantity\nA1-{tag},a1,1\nA2-{tag},a2,2\nA3-{tag},a3,3\n")
    _upload(client, head_headers, pid, f"code,description,quantity\nB1-{tag},b1,1\nB2-{tag},b2,2\n")

    assert len(planning._bom_items[pid]) == before + 5
    assert _lines(pid, f"A1-{tag}")[0].description == "a1"


def test_reupload_updates_in_place_and_keeps_unsupplied_fields(
    client: TestClient, head_headers: dict[str, str]
) -> None:
    pid = _project(client, head_headers)
    tag = uuid4().hex[:5].upper()
    _upload(client, head_headers, pid,
            f"code,description,quantity,supplier_name,spec_doc_id\nV-{tag},Valve,4,Acme Forge,SPEC-1\n")
    count = len(planning._bom_items[pid])
    (line,) = _lines(pid, f"V-{tag}")
    assert line.status == "planned"

    body = _upload(client, head_headers, pid, f"code,description,quantity\nV-{tag},Valve,6\n")
    assert len(planning._bom_items[pid]) == count
    (updated,) = _lines(pid, f"V-{tag}")
    assert updated.bom_item_id == line.bom_item_id
    assert updated.quantity == 6
    assert updated.supplier_name == "Acme Forge"   # not blanked by the sparser file
    assert updated.spec_doc_id == "SPEC-1"
    assert body["rows_accepted"] == 1


def test_file_status_never_moves_an_ordered_line_backwards(
    client: TestClient, head_headers: dict[str, str]
) -> None:
    pid = _project(client, head_headers)
    tag = uuid4().hex[:5].upper()
    _upload(client, head_headers, pid, f"code,description,quantity,status\nO-{tag},Pump,1,ordered\n")
    _upload(client, head_headers, pid, f"code,description,quantity,status\nO-{tag},Pump,1,planned\n")
    assert _lines(pid, f"O-{tag}")[0].status == "ordered"


def test_ambiguous_duplicate_codes_are_rejected_not_guessed(
    client: TestClient, head_headers: dict[str, str]
) -> None:
    pid = _project(client, head_headers)
    tag = uuid4().hex[:5].upper()
    _upload(client, head_headers, pid, f"code,description,quantity\nD-{tag},one,1\nD-{tag},two,2\n")
    assert len(_lines(pid, f"D-{tag}")) == 2

    # Same two rows again → pairs up in order, no growth.
    _upload(client, head_headers, pid, f"code,description,quantity\nD-{tag},one,10\nD-{tag},two,20\n")
    assert sorted(i.quantity for i in _lines(pid, f"D-{tag}")) == [10, 20]

    # One row dropped → can't tell which line it means.
    body = _upload(client, head_headers, pid, f"code,description,quantity\nD-{tag},two,30\n")
    assert body["rows_accepted"] == 0
    assert "bom_item_id" in body["errors"][0]
    assert sorted(i.quantity for i in _lines(pid, f"D-{tag}")) == [10, 20]


def test_bom_item_id_from_another_project_is_refused(client: TestClient, head_headers: dict[str, str]) -> None:
    projects = [p["project_id"] for p in client.get("/api/projects", headers=head_headers).json()
                if p["project_id"].startswith("PRJ-AF")]
    other_pid, pid = projects[0], projects[1]
    foreign_id = next(iter(planning._bom_items[other_pid]))
    body = _upload(client, head_headers, pid, f"bom_item_id,code,description,quantity\n{foreign_id},X,x,1\n")
    assert body["rows_accepted"] == 0
    assert "belongs to project" in body["errors"][0]


def _ingest(client: TestClient, headers: dict[str, str], name: str, csv_text: str) -> dict:
    preview = client.post(
        "/api/ingest/preview", headers=headers,
        files={"file": (name, csv_text.encode(), "text/csv")},
    )
    assert preview.status_code == 200, preview.text
    commit = client.post("/api/ingest/commit", headers=headers, json={"staging_id": preview.json()["staging_id"]})
    assert commit.status_code == 200, commit.text
    return commit.json()


def test_projects_sheet_updates_without_wiping_milestones(
    client: TestClient, head_headers: dict[str, str]
) -> None:
    pid = _project(client, head_headers)
    before = planning._projects[pid]
    assert len(before.milestones) > 1

    _ingest(client, head_headers, "projects.csv", f"project id,project name\n{pid},Renamed Project\n")
    after = planning._projects[pid]
    assert after.name == "Renamed Project"
    assert [m.code for m in after.milestones] == [m.code for m in before.milestones]
    assert after.client == before.client


def test_spreadsheet_suppliers_need_approval_for_buyers(
    client: TestClient, buyer_headers: dict[str, str]
) -> None:
    name = f"Sheet Vendor {uuid4().hex[:5]}"
    csv_text = f"name,category,country,on_time_delivery_pct,quality_ppm,lead_time_days\n{name},Valves,India,95,100,30\n"
    reply = _ingest(client, buyer_headers, "suppliers.csv", csv_text)
    assert reply["created"]["suppliers"] == 0
    assert reply["created"]["suppliers_pending_approval"] == 1
    assert not any(s.name == name for s in vendor_store._runtime.get(TENANT, []))

    _ingest(client, buyer_headers, "suppliers.csv", csv_text)  # re-upload
    pending = [a for a in approvals._approvals.get(TENANT, {}).values()
               if a.status == "pending" and name in a.title]
    assert len(pending) == 1, "re-uploading must not stack duplicate approvals"


def test_vendor_without_metrics_is_unverified_capped_and_not_recommended(
    client: TestClient, head_headers: dict[str, str]
) -> None:
    category = f"Cat {uuid4().hex[:5]}"
    proven = {"name": f"Proven {category}", "category": category, "country": "India", "lead_time_days": 30,
              "on_time_delivery_pct": 80, "quality_ppm": 900, "annual_spend_usd": 1000}
    assert client.post("/api/vendors", headers=head_headers, json=proven).status_code == 200

    res = client.post("/api/chat", headers=head_headers,
                      json={"message": f"Please onboard supplier named Shiny New Co from India"})
    assert res.status_code == 200
    new = next(s for s in vendor_store._runtime[TENANT] if s.name == "Shiny New Co")
    assert new.performance_verified is False
    assert new.country == "India"
    assert any("unverified" in f for f in new.risk_flags)

    card = vendor_intel.get_vendor_scorecard("Shiny New Co", tenant_id=TENANT)
    assert card is not None and card.composite_score <= vendor_intel.UNVERIFIED_SCORE_CAP

    # Same category as the proven vendor → must not be offered as its alternate.
    vendor_store._runtime[TENANT] = [
        s.model_copy(update={"category": category}) if s.name == "Shiny New Co" else s
        for s in vendor_store._runtime[TENANT]
    ]
    proven_card = vendor_intel.get_vendor_scorecard(proven["name"], tenant_id=TENANT)
    assert "Shiny New Co" not in {a.name for a in proven_card.alternates}
