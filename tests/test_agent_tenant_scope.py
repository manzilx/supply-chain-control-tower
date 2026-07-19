"""Agent tools must not leak cross-tenant data when a user is set."""

from __future__ import annotations

from app.agent_tools import invoke, reset_tool_user, set_tool_user
from app.tenants import get_user


def test_list_projects_tool_scoped_to_arcforge() -> None:
    user = get_user("arcforge-buyer-01")
    assert user is not None
    token = set_tool_user(user)
    try:
        record = invoke("list_projects", {})
        projects = record.output_preview
        assert isinstance(projects, list)
        assert projects, "expected arcforge projects"
        ids = {p["project_id"] for p in projects}
        assert "PRJ-AF-CCGT" in ids
        assert "PRJ-HE-WIND" not in ids
        assert "PRJ-HE-FPSO" not in ids
        for p in projects:
            assert p["tenant_id"] == "arcforge"
    finally:
        reset_tool_user(token)


def test_open_prs_tool_scoped_to_arcforge() -> None:
    user = get_user("arcforge-buyer-01")
    assert user is not None
    token = set_tool_user(user)
    try:
        record = invoke("get_open_prs", {})
        prs = record.output_preview
        assert isinstance(prs, list)
        for pr in prs:
            assert pr["tenant_id"] == "arcforge"
    finally:
        reset_tool_user(token)
