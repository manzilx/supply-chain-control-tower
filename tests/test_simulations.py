"""What-if simulator: default scenario returns impact; tenant-scoped lookups."""

from __future__ import annotations

from collections.abc import Callable
from unittest.mock import patch

from fastapi.testclient import TestClient


def _simulate(
    client: TestClient,
    headers: dict[str, str],
    body: dict,
):
    return client.post("/api/risk/simulate", json=body, headers=headers)


def test_vendor_slip_default_returns_impact(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    """Arcforge default vendor-slip is a real result, not the empty-error path."""
    res = _simulate(
        client,
        auth_headers,
        {"scenario": "vendor_slip_2w", "target": "Helios Cast & Forge"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["scenario"] == "vendor_slip_2w"
    assert body["affected_items"], body["headline"]
    assert body["cost_delta_usd"] > 0
    assert body["schedule_delta_days"] == 14
    assert "no impact" not in body["headline"].lower()
    refs = {item["ref_id"] for item in body["affected_items"]}
    assert "PO-AF-24017" in refs


def test_vendor_slip_uses_tenant_demo_pos(
    client: TestClient,
    login: Callable[[str], dict[str, str]],
) -> None:
    """Helios slip hits Helios POs, not the Arcforge demo slice."""
    headers = login("helios-buyer-01")
    res = _simulate(
        client,
        headers,
        {"scenario": "vendor_slip_2w", "target": "NorthCable Subsea"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["affected_items"], body["headline"]
    refs = {item["ref_id"] for item in body["affected_items"]}
    assert "PO-HE-31022" in refs
    assert not any(ref.startswith("PO-AF-") for ref in refs)


def test_vendor_slip_does_not_leak_cross_tenant_pos(
    client: TestClient,
    login: Callable[[str], dict[str, str]],
) -> None:
    headers = login("helios-buyer-01")
    res = _simulate(
        client,
        headers,
        {"scenario": "vendor_slip_2w", "target": "Helios Cast & Forge"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["affected_items"] == []
    assert body["cost_delta_usd"] == 0
    assert "no open orders" in body["headline"].lower()


def test_customs_hold_tenant_po(
    client: TestClient,
    login: Callable[[str], dict[str, str]],
) -> None:
    headers = login("helios-buyer-01")
    res = _simulate(
        client,
        headers,
        {"scenario": "customs_hold", "target": "PO-HE-31022"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["affected_items"], body["headline"]
    assert body["schedule_delta_days"] == 21
    assert body["cost_delta_usd"] > 0
    assert body["affected_items"][0]["ref_id"] == "PO-HE-31022"


def test_top_expedite_vendor_slip_has_impact_every_tenant(
    client: TestClient,
    login: Callable[[str], dict[str, str]],
) -> None:
    """The vendor the UI now defaults to (top expedite exposure) must not be empty-impact."""
    for user_id in ("arcforge-buyer-01", "helios-buyer-01", "northwind-buyer-01"):
        headers = login(user_id)
        queue = client.get("/api/expediting/queue", headers=headers)
        assert queue.status_code == 200, user_id
        items = queue.json()["items"]
        assert items, f"{user_id} expedite queue empty"
        vendor = items[0]["supplier_name"]
        res = _simulate(
            client,
            headers,
            {"scenario": "vendor_slip_2w", "target": vendor},
        )
        assert res.status_code == 200, user_id
        body = res.json()
        assert body["affected_items"], f"{user_id} {vendor}: {body['headline']}"
        assert "no impact" not in body["headline"].lower()


def test_need_by_move_milestone_has_impact(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    res = _simulate(
        client,
        auth_headers,
        {"scenario": "need_by_move", "target": "PRJ-RB-660:M1", "custom_slip_days": 10},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["scenario"] == "need_by_move"
    assert body["schedule_delta_days"] == 10
    assert body["milestone_impacts"], body["headline"]
    assert body["milestone_impacts"][0]["milestone_code"] == "M1"
    assert body["affected_items"]
    assert "not found" not in body["headline"].lower()


def test_need_by_move_unknown_target(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    res = _simulate(
        client,
        auth_headers,
        {"scenario": "need_by_move", "target": "NO-SUCH-TARGET"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["affected_items"] == []
    assert body["milestone_impacts"] == []
    assert "not found" in body["headline"].lower()


def test_need_by_move_pr(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    bom = client.get("/api/projects/PRJ-RB-660/bom", headers=auth_headers)
    assert bom.status_code == 200
    item = next(b for b in bom.json() if b["status"] == "planned")
    pr = client.post(
        "/api/prs",
        headers=auth_headers,
        json={
            "project_id": "PRJ-RB-660",
            "bom_item_id": item["bom_item_id"],
            "need_by": "2026-12-01",
        },
    )
    assert pr.status_code == 200
    pr_no = pr.json()["pr_no"]
    res = _simulate(
        client,
        auth_headers,
        {"scenario": "need_by_move", "target": pr_no, "custom_slip_days": 7},
    )
    assert res.status_code == 200
    body = res.json()
    assert any(a["ref_id"] == pr_no for a in body["affected_items"]), body
    assert body["schedule_delta_days"] == 7


def test_simulate_does_not_block_on_narrative(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    res = _simulate(
        client,
        auth_headers,
        {"scenario": "vendor_slip_2w", "target": "Helios Cast & Forge"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["affected_items"]
    assert body.get("narrative") in (None, "")


def test_brief_is_deterministic_without_key(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    sim = _simulate(
        client,
        auth_headers,
        {"scenario": "vendor_slip_2w", "target": "Helios Cast & Forge"},
    )
    with patch("app.llm.is_enabled", return_value=False):
        brief = client.post("/api/risk/simulate/brief", json=sim.json(), headers=auth_headers)
    assert brief.status_code == 200
    body = brief.json()
    assert body["source"] == "deterministic"
    assert body["why"]
    assert body["primary_action"] in {
        "followup", "expedite", "open_po", "open_vendor", "open_project",
    }


def test_parse_vendor_slip_days(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    with patch("app.llm.is_enabled", return_value=False):
        res = client.post(
            "/api/risk/simulate/parse",
            json={"ask": "Helios slips 21 days"},
            headers=auth_headers,
        )
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    assert body["scenario"] == "vendor_slip_2w"
    assert body["target"] == "Helios Cast & Forge"
    assert body["custom_slip_days"] == 21


def test_parse_customs_hold_po(
    client: TestClient,
    login: Callable[[str], dict[str, str]],
) -> None:
    headers = login("helios-buyer-01")
    with patch("app.llm.is_enabled", return_value=False):
        res = client.post(
            "/api/risk/simulate/parse",
            json={"ask": "hold PO-HE-31022"},
            headers=headers,
        )
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    assert body["scenario"] == "customs_hold"
    assert body["target"] == "PO-HE-31022"


def test_parse_garbage_does_not_invent(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    with patch("app.llm.is_enabled", return_value=False):
        res = client.post(
            "/api/risk/simulate/parse",
            json={"ask": "asdf qwerty purple helicopter"},
            headers=auth_headers,
        )
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is False
    assert not body.get("target")


def test_alt_vendor_same_category(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    res = _simulate(
        client,
        auth_headers,
        {
            "scenario": "alt_vendor",
            "target": "Helios Cast & Forge",
            "alternate_vendor": "Kerala Forge Works",
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert "not found" not in body["headline"].lower()
    assert body["affected_items"]
    assert any(item["ref_id"] == "PO-AF-24017" for item in body["affected_items"])
