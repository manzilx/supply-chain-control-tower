"""Malformed model output falls back to deterministic answers instead of 500s.

DeepSeek replies are untrusted: a JSON-mode reply can still carry an off-list
enum or the wrong type for a field. Each surface here once crashed or rendered
garbage on such a reply.
"""

from __future__ import annotations

from contextlib import ExitStack, contextmanager
from unittest.mock import patch

from fastapi.testclient import TestClient


@contextmanager
def model_replies(reply: dict):
    """Pretend DeepSeek is configured and answers every JSON call with `reply`.

    ai_actions binds grok_json / is_enabled at import time, so patch it
    directly as well as app.llm (which simulations import from per call).
    """
    with ExitStack() as stack:
        for target in ("app.llm", "app.ai_actions"):
            stack.enter_context(patch(f"{target}.is_enabled", return_value=True))
            stack.enter_context(patch(f"{target}.grok_json", return_value=reply))
        yield


def test_parse_off_list_scenario_falls_back_to_rules(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    with model_replies(
        {"ok": True, "scenario": "vendor_slip", "target": "Helios Cast & Forge"}
    ):
        res = client.post(
            "/api/risk/simulate/parse",
            json={"ask": "Helios slips 21 days"},
            headers=auth_headers,
        )
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    assert body["scenario"] == "vendor_slip_2w"
    assert body["custom_slip_days"] == 21


def test_brief_with_list_typed_fields_falls_back(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    sim = client.post(
        "/api/risk/simulate",
        json={"scenario": "vendor_slip_2w", "target": "Helios Cast & Forge"},
        headers=auth_headers,
    ).json()
    with model_replies(
        {"why": ["not a string"], "primary_action": ["followup"], "action_ref": ["PO-1"]}
    ):
        res = client.post("/api/risk/simulate/brief", json=sim, headers=auth_headers)
    assert res.status_code == 200
    body = res.json()
    assert body["why"] and not body["why"].startswith("[")
    assert body["primary_action"] in {
        "followup", "expedite", "open_po", "open_vendor", "open_project",
    }


def test_brief_keeps_valid_why_but_drops_bad_action(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    sim = client.post(
        "/api/risk/simulate",
        json={"scenario": "vendor_slip_2w", "target": "Helios Cast & Forge"},
        headers=auth_headers,
    ).json()
    with model_replies(
        {"why": "Four orders slide a month.", "primary_action": ["followup"], "action_ref": {"x": 1}}
    ):
        res = client.post("/api/risk/simulate/brief", json=sim, headers=auth_headers)
    assert res.status_code == 200
    body = res.json()
    assert body["why"] == "Four orders slide a month."
    assert body["source"] == "deepseek"
    assert isinstance(body["primary_action"], str)


def test_explain_rejects_non_string_fields(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    with model_replies({"headline": ["a list"], "body": ["also a list"]}):
        res = client.post(
            "/api/explain", json={"kind": "vendor", "id": "Helios Cast & Forge"}, headers=auth_headers
        )
    assert res.status_code == 200
    body = res.json()
    assert body["source"] == "deterministic"
    assert not body["headline"].startswith("[")


def test_explain_string_bullets_are_not_split_into_characters(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    # A different vendor from the test above: explain replies are cached per entity.
    with model_replies(
        {"headline": "BluePeak is reliable.", "body": "Scores well.", "bullets": "one bullet"}
    ):
        res = client.post(
            "/api/explain", json={"kind": "vendor", "id": "BluePeak Controls"}, headers=auth_headers
        )
    assert res.status_code == 200
    body = res.json()
    assert body["source"] == "deepseek"
    assert body["headline"] == "BluePeak is reliable."
    assert body["bullets"] == []
