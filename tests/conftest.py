"""Shared pytest fixtures for the control-tower API."""

from __future__ import annotations

import os
import tempfile
from collections.abc import Callable, Generator

import pytest
from fastapi.testclient import TestClient

# Isolate persistence before the app module loads snapshot paths.
_tmp_state = tempfile.mkdtemp(prefix="ct-test-state-")
os.environ.setdefault("STATE_DIR", _tmp_state)
os.environ.setdefault("APP_ENV", "dev")

from app.auth import issue_token  # noqa: E402
from app.main import app  # noqa: E402
from app.tenants import get_user  # noqa: E402


TENANT = "arcforge"
BUYER_ID = f"{TENANT}-buyer-01"
HEAD_ID = f"{TENANT}-head-01"
ADMIN_ID = f"{TENANT}-admin-01"


def headers_for_user(user_id: str) -> dict[str, str]:
    user = get_user(user_id)
    assert user is not None, f"unknown test user {user_id}"
    return {"Authorization": f"Bearer {issue_token(user)}"}


@pytest.fixture()
def client() -> Generator[TestClient, None, None]:
    from app import approvals, vendor_store

    vendor_store._runtime.clear()
    approvals._approvals.clear()
    approvals._counter["approval"] = 0

    with TestClient(app) as c:
        yield c

    vendor_store._runtime.clear()
    approvals._approvals.clear()
    approvals._counter["approval"] = 0


@pytest.fixture()
def buyer_headers() -> dict[str, str]:
    return headers_for_user(BUYER_ID)


@pytest.fixture()
def head_headers() -> dict[str, str]:
    return headers_for_user(HEAD_ID)


@pytest.fixture()
def admin_headers() -> dict[str, str]:
    return headers_for_user(ADMIN_ID)


@pytest.fixture()
def auth_headers(buyer_headers: dict[str, str]) -> dict[str, str]:
    """Default authenticated buyer session for smoke tests."""
    return buyer_headers


@pytest.fixture()
def login() -> Callable[[str], dict[str, str]]:
    def _login(user_id: str) -> dict[str, str]:
        return headers_for_user(user_id)

    return _login

