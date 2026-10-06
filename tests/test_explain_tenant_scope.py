"""/api/explain and BOM autofill only see the caller's tenant.

Explain once looked entities up across every tenant (and cached by id alone),
so any user could read another tenant's PO or project — and with DeepSeek on,
that data went into the prompt.
"""

from __future__ import annotations

from collections.abc import Callable
from unittest.mock import patch

from fastapi.testclient import TestClient


def _explain(client: TestClient, headers: dict[str, str], kind: str, eid: str) -> dict:
    with patch("app.llm.is_enabled", return_value=False):
        res = client.post("/api/explain", json={"kind": kind, "id": eid}, headers=headers)
    assert res.status_code == 200
    return res.json()


def test_explain_other_tenants_project_is_not_found(
    client: TestClient,
    auth_headers: dict[str, str],
    login: Callable[[str], dict[str, str]],
) -> None:
    # Arcforge owns PRJ-RB-660. Read it as arcforge first so a cache keyed on
    # id alone would hand the same brief to helios.
    own = _explain(client, auth_headers, "project", "PRJ-RB-660")
    assert "not found" not in own["headline"]

    other = _explain(client, login("helios-viewer-01"), "project", "PRJ-RB-660")
    assert other["headline"] == "project PRJ-RB-660 not found"
    assert other["bullets"] == []


def test_explain_other_tenants_po_is_not_found(
    client: TestClient,
    auth_headers: dict[str, str],
    login: Callable[[str], dict[str, str]],
) -> None:
    own = _explain(client, auth_headers, "po", "PO-AF-24017")
    assert "not found" not in own["headline"]

    other = _explain(client, login("northwind-viewer-01"), "po", "PO-AF-24017")
    assert other["headline"] == "po PO-AF-24017 not found"


def test_bom_autofill_offers_only_tenant_suppliers(
    client: TestClient,
    login: Callable[[str], dict[str, str]],
) -> None:
    from app.sample_data import build_demo_request

    helios_suppliers = {s.name for s in build_demo_request("helios").suppliers}
    seen: dict = {}

    def capture(system: str, user: str, **_: object) -> dict:
        seen["user"] = user
        return {"suggestions": []}

    # ai_actions binds these at import time, so patch them where they're used.
    with patch("app.ai_actions.is_enabled", return_value=True), patch(
        "app.ai_actions.llm_json", side_effect=capture
    ):
        res = client.post("/api/projects/PRJ-NS-OSS/bom/autofill", headers=login("helios-head-01"))
    assert res.status_code == 200
    import json

    ctx = json.loads(seen["user"][seen["user"].index("{"):])
    offered = {s["name"] for s in ctx["approved_suppliers"]}
    assert offered and offered <= helios_suppliers
