"""Prod JWT secret guard — isolated from the session-scoped app fixture."""

from __future__ import annotations

import pytest

from app.auth import validate_jwt_secret_for_production


def test_prod_rejects_missing_jwt_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "prod")
    monkeypatch.delenv("JWT_SECRET", raising=False)

    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        validate_jwt_secret_for_production()


def test_prod_rejects_default_jwt_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("JWT_SECRET", "dev-secret-change-me")

    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        validate_jwt_secret_for_production()


def test_prod_accepts_custom_jwt_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "prod")
    monkeypatch.setenv("JWT_SECRET", "a" * 64)

    validate_jwt_secret_for_production()


def test_dev_allows_default_jwt_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "dev")
    monkeypatch.delenv("JWT_SECRET", raising=False)

    validate_jwt_secret_for_production()
