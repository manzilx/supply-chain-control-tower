"""Per-project SCM process map and risk register."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.process_map import STAGE_ORDER
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


def test_process_summary_tenant_isolation(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    res = client.get("/api/projects/process-summary", headers=auth_headers)
    assert res.status_code == 200
    body = res.json()
    assert body, "Arcforge should have at least one project"
    ids = {row["project_id"] for row in body}
    assert PROJECT in ids
    assert "PRJ-HE-WIND" not in ids
    river = next(row for row in body if row["project_id"] == PROJECT)
    assert river["bom_total"] > 0
    assert "spec" in river["current_by_stage"]
    assert river["open_risks"] >= 1
    assert sum(river["current_by_stage"].values()) == river["bom_total"]

    helios = client.get(
        "/api/projects/process-summary",
        headers=headers_for_user("helios-buyer-01"),
    )
    assert helios.status_code == 200
    helios_ids = {row["project_id"] for row in helios.json()}
    assert "PRJ-HE-WIND" in helios_ids
    assert PROJECT not in helios_ids


def test_tenant_risk_register_seeds_without_leak(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    bom = client.get(f"/api/projects/{PROJECT}/bom", headers=auth_headers)
    assert bom.status_code == 200
    missing = [b for b in bom.json() if b["status"] == "spec_missing"]
    assert missing, "Riverbank fixture should have spec_missing lines"

    res = client.get("/api/risks/register", headers=auth_headers)
    assert res.status_code == 200
    body = res.json()
    assert body
    projects = {r["project_id"] for r in body}
    assert PROJECT in projects
    assert "PRJ-HE-WIND" not in projects
    keys = {r["signal_key"] for r in body if r.get("signal_key")}
    for item in missing:
        assert f"spec:{item['bom_item_id']}" in keys

    helios = client.get("/api/risks/register", headers=headers_for_user("helios-buyer-01"))
    assert helios.status_code == 200
    helios_projects = {r["project_id"] for r in helios.json()}
    assert PROJECT not in helios_projects


def test_process_map_review_actions_for_blocked_spec(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    res = client.get(f"/api/projects/{PROJECT}/process-map", headers=auth_headers)
    assert res.status_code == 200
    actions = res.json()["review_actions"]
    assert actions
    spec = next((a for a in actions if a["process_stage"] == "spec"), None)
    assert spec is not None
    assert spec["priority"] == "P1"
    assert spec["owner"] == "Engineering"
    assert "Unblock" in spec["title"]


def test_process_line_next_actions(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    res = client.get(f"/api/projects/{PROJECT}/process-map", headers=auth_headers)
    assert res.status_code == 200
    stages = {s["stage"]: s for s in res.json()["stages"]}
    spec_items = stages["spec"]["items"]
    assert spec_items
    assert all(i["next_action"] == "request_spec" for i in spec_items)

    for item in stages["pr"]["items"]:
        if item.get("entity_id"):
            assert item["next_action"] == "issue_rfq"
        else:
            assert item["next_action"] == "create_pr"

    for item in stages["delivery"]["items"]:
        assert item["next_action"] is None


def test_create_pr_sets_issue_rfq_action(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    first = client.get(f"/api/projects/{PROJECT}/process-map", headers=auth_headers)
    assert first.status_code == 200
    waiting = [
        i for s in first.json()["stages"] if s["stage"] == "pr"
        for i in s["items"] if i["next_action"] == "create_pr"
    ]
    assert waiting, "Riverbank should have planned lines ready for a PR"
    item = waiting[0]
    created = client.post(
        "/api/prs",
        headers=auth_headers,
        json={"project_id": PROJECT, "bom_item_id": item["bom_item_id"]},
    )
    assert created.status_code == 200
    pr_no = created.json()["pr_no"]

    second = client.get(f"/api/projects/{PROJECT}/process-map", headers=auth_headers)
    assert second.status_code == 200
    line = next(
        i
        for s in second.json()["stages"]
        for i in s["items"]
        if i["bom_item_id"] == item["bom_item_id"]
    )
    assert line["next_action"] == "issue_rfq"
    assert line["entity_id"] == pr_no

    rfq = client.post(
        "/api/rfqs",
        headers=auth_headers,
        json={"pr_no": pr_no, "vendors": ["Process Map Vendor"], "due_in_days": 10},
    )
    assert rfq.status_code == 200
    third = client.get(f"/api/projects/{PROJECT}/process-map", headers=auth_headers)
    assert third.status_code == 200
    moved = next(
        (s["stage"], i)
        for s in third.json()["stages"]
        for i in s["items"]
        if i["bom_item_id"] == item["bom_item_id"]
    )
    assert moved[0] == "rfq"
    assert moved[1]["next_action"] == "add_quote"
    assert moved[1]["entity_id"] == rfq.json()["rfq_no"]

    quoted = client.post(
        f"/api/rfqs/{rfq.json()['rfq_no']}/quotes",
        headers=auth_headers,
        json={
            "vendor": "Process Map Vendor",
            "unit_price_usd": 1250,
            "lead_time_days": 28,
        },
    )
    assert quoted.status_code == 200
    fourth = client.get(f"/api/projects/{PROJECT}/process-map", headers=auth_headers)
    assert fourth.status_code == 200
    after_quote = next(
        (s["stage"], i)
        for s in fourth.json()["stages"]
        for i in s["items"]
        if i["bom_item_id"] == item["bom_item_id"]
    )
    assert after_quote[0] == "quotes"
    assert after_quote[1]["next_action"] == "add_quote"


def test_weekly_plan_includes_process_review(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    res = client.get("/api/weekly-plan", headers=auth_headers)
    assert res.status_code == 200
    body = res.json()
    labels = {k["label"] for k in body["kpi_snapshot"]}
    assert "Process Blocked" in labels
    process_items = [i for i in body["items"] if i["category"] == "process"]
    assert process_items
    assert any("/process" in (i.get("href") or "") for i in process_items)
    assert any(PROJECT in ref for i in process_items for ref in i["supporting_refs"])

    helios = client.get("/api/weekly-plan", headers=headers_for_user("helios-buyer-01"))
    assert helios.status_code == 200
    helios_refs = [ref for i in helios.json()["items"] for ref in i["supporting_refs"]]
    assert f"project:{PROJECT}" not in helios_refs


def test_search_index_includes_process_and_risks(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    res = client.get("/api/search/index", headers=auth_headers)
    assert res.status_code == 200
    items = res.json()["items"]
    process = [i for i in items if i["kind"] == "process"]
    assert any(i["project_id"] == PROJECT and i["href"].endswith("/process") for i in process)
    assert all(i["project_id"] != "PRJ-HE-WIND" for i in process)
    risks = [i for i in items if i["kind"] == "risk"]
    assert any(i["project_id"] == PROJECT for i in risks)
    assert any("spec" in (i["title"] + " ".join(i.get("tags") or [])).lower() for i in risks)

    helios = client.get("/api/search/index", headers=headers_for_user("helios-buyer-01"))
    assert helios.status_code == 200
    helios_items = helios.json()["items"]
    assert all(i.get("project_id") != PROJECT for i in helios_items)


def test_alerts_include_process_rollup(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    res = client.get("/api/alerts", headers=auth_headers)
    assert res.status_code == 200
    process = [a for a in res.json()["alerts"] if a["category"] == "process"]
    assert process
    assert any(PROJECT in a["href"] for a in process)


def test_risk_patch_emits_audit(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    first = client.get(f"/api/projects/{PROJECT}/process-map", headers=auth_headers)
    assert first.status_code == 200
    risk = next(r for r in first.json()["risks"] if r["signal_key"] and r["signal_key"].startswith("spec:"))
    patched = client.patch(
        f"/api/projects/{PROJECT}/risks/{risk['risk_id']}",
        headers=auth_headers,
        json={"status": "accepted", "owner": "Buyer One"},
    )
    assert patched.status_code == 200

    audit = client.get(f"/api/audit/entity/risk/{risk['risk_id']}", headers=auth_headers)
    assert audit.status_code == 200
    events = audit.json()
    assert events
    assert any(e["action"] == "updated" and e["entity_kind"] == "risk" for e in events)
    assert all(e.get("project_id") != "PRJ-HE-WIND" for e in events)


