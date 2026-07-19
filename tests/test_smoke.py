"""Smoke tests for core API health, auth, tenancy, and approvals."""

from __future__ import annotations

from collections.abc import Callable

from fastapi.testclient import TestClient


def test_health(client: TestClient) -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ready(client: TestClient) -> None:
    response = client.get("/readyz")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert "snapshot" in body


def test_login_and_me(
    client: TestClient,
    login: Callable[[str], dict[str, str]],
) -> None:
    user_id = "arcforge-admin-01"
    login_response = client.post("/api/auth/login", json={"user_id": user_id})
    assert login_response.status_code == 200
    body = login_response.json()
    assert body["token"]
    assert body["user"]["user_id"] == user_id
    assert body["user"]["tenant_id"] == "arcforge"

    headers = {"Authorization": f"Bearer {body['token']}"}
    me_response = client.get("/api/auth/me", headers=headers)
    assert me_response.status_code == 200
    me_body = me_response.json()
    assert me_body["user"]["user_id"] == user_id
    assert me_body["tenant"]["tenant_id"] == "arcforge"


def test_tenant_isolation_returns_404(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    """Arcforge users must not see Helios-only projects."""
    own = client.get("/api/projects", headers=auth_headers)
    assert own.status_code == 200
    own_ids = {project["project_id"] for project in own.json()}
    assert "PRJ-AF-CCGT" in own_ids
    assert "PRJ-HE-WIND" not in own_ids

    cross_tenant = client.get("/api/projects/PRJ-HE-WIND", headers=auth_headers)
    assert cross_tenant.status_code == 404


def test_quote_above_budget_pending_approval(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    """Buyer over-budget quotes are gated; sourcing state stays uncommitted."""
    projects = client.get("/api/projects", headers=auth_headers)
    assert projects.status_code == 200
    project = next(p for p in projects.json() if p["project_id"].startswith("PRJ-AF"))

    bom = client.get(f"/api/projects/{project['project_id']}/bom", headers=auth_headers)
    assert bom.status_code == 200
    bom_item = bom.json()[0]

    pr_response = client.post(
        "/api/prs",
        headers=auth_headers,
        json={
            "project_id": project["project_id"],
            "bom_item_id": bom_item["bom_item_id"],
            "budget_value_usd": 1000.0,
            "buyer": "Smoke Test Buyer",
        },
    )
    assert pr_response.status_code == 200
    pr_no = pr_response.json()["pr_no"]

    rfq_response = client.post(
        "/api/rfqs",
        headers=auth_headers,
        json={
            "pr_no": pr_no,
            "vendors": ["Helios Cast & Forge"],
            "due_in_days": 7,
        },
    )
    assert rfq_response.status_code == 200
    rfq_no = rfq_response.json()["rfq_no"]

    quote_response = client.post(
        f"/api/rfqs/{rfq_no}/quotes",
        headers=auth_headers,
        json={
            "vendor": "Helios Cast & Forge",
            "unit_price_usd": 5000.0,
            "lead_time_days": 30,
            "incoterm": "CIP",
            "validity_days": 30,
        },
    )
    assert quote_response.status_code == 200
    body = quote_response.json()
    assert body["status"] == "pending_approval"
    assert body["quote"] is None
    assert body["approval"]["status"] == "pending"
    assert body["approval"]["kind"] == "quote_above_budget"

    quotes = client.get(f"/api/rfqs/{rfq_no}/quotes", headers=auth_headers)
    assert quotes.status_code == 200
    assert quotes.json() == []
