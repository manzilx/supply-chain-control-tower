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
