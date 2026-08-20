"""Admins can paste a DeepSeek key in the app. The key is never echoed."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.llm import is_enabled, key_hint
from tests.conftest import ADMIN_ID, BUYER_ID, headers_for_user


SECRET = "sk-test-deepseek-key-do-not-echo"


def test_buyer_cannot_set_deepseek_key(client: TestClient) -> None:
    res = client.post(
        "/api/ai/key",
        json={"api_key": SECRET},
        headers=headers_for_user(BUYER_ID),
    )
    assert res.status_code == 403
    assert SECRET not in res.text
    assert is_enabled() is False


def test_admin_can_key_in_deepseek_key_and_status_hides_it(
    client: TestClient,
    monkeypatch,
) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

    saved = client.post(
        "/api/ai/key",
        json={"api_key": SECRET},
        headers=headers_for_user(ADMIN_ID),
    )
    assert saved.status_code == 200, saved.text
    body = saved.json()
    assert body["enabled"] is True
    assert body["key_hint"] == key_hint()
    assert SECRET not in saved.text
    assert "sk-test-deepseek" not in saved.text

    status = client.get("/api/ai/status", headers=headers_for_user(ADMIN_ID))
    assert status.status_code == 200
    payload = status.json()
    assert payload["enabled"] is True
    assert payload["provider"] == "deepseek"
    assert payload["configured_via"] == "runtime"
    assert payload["key_hint"] == "••••echo"
    dumped = status.text
    assert SECRET not in dumped
    assert "sk-test-deepseek" not in dumped

    cleared = client.delete("/api/ai/key", headers=headers_for_user(ADMIN_ID))
    assert cleared.status_code == 200
    assert cleared.json()["enabled"] is False
    assert SECRET not in cleared.text
