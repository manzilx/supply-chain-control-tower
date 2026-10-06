"""Password login, tenant-switch scope, chat RBAC, and device enrol scope."""

from __future__ import annotations

import os
import stat
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app import credentials, persistence
from tests.conftest import headers_for_user
from tests.test_store_grn import make_store

PASSWORD = "correct horse battery staple"


@pytest.fixture()
def password_mode(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setenv("DEMO_LOGIN", "0")
    monkeypatch.delenv("PLATFORM_ADMINS", raising=False)
    monkeypatch.setattr(persistence, "STATE_DIR", tmp_path)
    credentials.reset_lockouts()
    yield tmp_path
    credentials.reset_lockouts()


def test_password_mode_hides_personas_and_requires_password(
    client: TestClient, password_mode: Path
) -> None:
    assert client.get("/api/auth/mode").json() == {"demo_login": False}
    assert client.get("/api/auth/personas").status_code == 404
    # The old passwordless request no longer works.
    res = client.post("/api/auth/login", json={"user_id": "arcforge-head-01"})
    assert res.status_code == 401


def test_password_login_by_email(client: TestClient, password_mode: Path) -> None:
    credentials.set_password("arcforge-head-01", PASSWORD)
    mode = stat.S_IMODE(os.stat(password_mode / "credentials.json").st_mode)
    assert mode == 0o600
    assert PASSWORD not in (password_mode / "credentials.json").read_text()

    res = client.post("/api/auth/login", json={"user_id": "HEAD@arcforge.com", "password": PASSWORD})
    assert res.status_code == 200
    body = res.json()
    assert body["user"]["user_id"] == "arcforge-head-01"
    assert body["can_switch_tenant"] is False

    wrong = client.post("/api/auth/login", json={"user_id": "head@arcforge.com", "password": "nope-nope-nope"})
    assert wrong.status_code == 401


def test_short_password_rejected(password_mode: Path) -> None:
    with pytest.raises(ValueError):
        credentials.set_password("arcforge-head-01", "short")


def test_repeated_failures_lock_out(client: TestClient, password_mode: Path) -> None:
    credentials.set_password("arcforge-buyer-01", PASSWORD)
    for _ in range(credentials.MAX_FAILURES):
        res = client.post("/api/auth/login", json={"user_id": "arcforge-buyer-01", "password": "wrong-password!"})
        assert res.status_code == 401
    # Even the right password is refused while locked out.
    res = client.post("/api/auth/login", json={"user_id": "arcforge-buyer-01", "password": PASSWORD})
    assert res.status_code == 429


def test_tenant_admin_cannot_act_in_another_tenant(
    client: TestClient, password_mode: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    northwind_admin = {**headers_for_user("northwind-admin-01"), "X-Tenant-Override": "arcforge"}
    assert client.get("/api/approvals", headers=northwind_admin).status_code == 403
    assert client.get("/api/tenants", headers=headers_for_user("northwind-admin-01")).status_code == 403

    monkeypatch.setenv("PLATFORM_ADMINS", "northwind-admin-01")
    res = client.get("/api/auth/me", headers=northwind_admin)
    assert res.status_code == 200
    assert res.json()["tenant"]["tenant_id"] == "arcforge"
    assert res.json()["can_switch_tenant"] is True


def test_demo_mode_keeps_admin_switching(client: TestClient) -> None:
    headers = {**headers_for_user("northwind-admin-01"), "X-Tenant-Override": "arcforge"}
    res = client.get("/api/auth/me", headers=headers)
    assert res.status_code == 200
    assert res.json()["tenant"]["tenant_id"] == "arcforge"


def test_chat_cannot_create_vendor_for_role_without_permission(client: TestClient) -> None:
    from app import approvals, vendor_store

    store = headers_for_user("arcforge-store-01")
    assert client.post("/api/vendors", headers=store, json={}).status_code in (403, 422)

    res = client.post(
        "/api/chat", headers=store, json={"message": "Please onboard supplier named Side Door Valves"}
    )
    assert res.status_code == 200
    assert not any(
        "Side Door Valves" in a.title for a in approvals._approvals.get("arcforge", {}).values()
    ), "no approval should be created"
    assert not any(s.name == "Side Door Valves" for s in vendor_store._runtime.get("arcforge", []))
    calls = res.json().get("tool_calls") or []
    assert any("Permission denied" in c["output_summary"] for c in calls if c["tool"] == "propose_vendor_onboarding")


def test_chat_tool_list_is_filtered_by_role() -> None:
    from app.agent_tools import tools_for
    from app.tenants import get_user

    store_tools = {t.name for t in tools_for(get_user("arcforge-store-01"))}
    assert "propose_vendor_onboarding" not in store_tools
    assert "get_commercial_summary" not in store_tools
    assert "get_grn_queue" in store_tools
    assert "propose_vendor_onboarding" in {t.name for t in tools_for(get_user("arcforge-buyer-01"))}
    assert tools_for(None) == []


def test_device_id_cannot_be_taken_over_by_another_tenant(client: TestClient) -> None:
    def invite(admin: dict[str, str]) -> str:
        store_id = make_store(client, admin)
        res = client.post(
            "/api/field-admin/enrolments",
            headers=admin,
            json={"store_id": store_id, "person_name": "Field Tester", "person_role": "storekeeper"},
        )
        assert res.status_code == 200
        return res.json()["code"]

    device_id = uuid4().hex
    first = client.post(
        "/api/v1/field/enrol",
        json={"code": invite(headers_for_user("arcforge-admin-01")), "device_id": device_id},
    )
    assert first.status_code == 200

    hijack = client.post(
        "/api/v1/field/enrol",
        json={"code": invite(headers_for_user("northwind-admin-01")), "device_id": device_id},
    )
    assert hijack.status_code == 409
