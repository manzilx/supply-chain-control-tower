"""SAP CPI (Cloud Integration) adapter — Phase 0 scaffold.

Two modes, selected via SAP_CPI_MODE env var:

  - "mock"   (default): no network. Returns plausible SAP doc numbers, lets the
             whole submit → status → webhook loop be exercised locally without a
             real CPI tenant.
  - "live"  : calls real CPI iflows over REST with OAuth2 client_credentials.
  - "disabled": every operation returns failed; "Submit to SAP" buttons stay
             disabled in the UI.

The contract is intentionally narrow:

  submit_pr(pr)               -> {sap_pr_no, sap_status, error}
  submit_po(po)               -> {sap_po_no, sap_status, error}
  get_pr_status(sap_pr_no)    -> {status, gr_qty?, ir_value?}
  get_po_status(sap_po_no)    -> {status, gr_qty?, ir_value?}
  pull_vendor_delta(since)    -> list of vendor records
  pull_material_delta(since)  -> list of material records

CPI iflow signature must match these (the basis team builds 6 iflows; we
call them like plain REST). When the live mode is enabled, the same code
talks to the real thing — no caller change needed.
"""

from __future__ import annotations

import json
import os
import random
import string
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from threading import Lock
from typing import Any, Optional
from urllib import error as _urlerror
from urllib import request as _urlrequest

from ..schemas import (
    PurchaseRequisition,
    SapHealth,
    SapMode,
    SourcingPO,
)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


def _mode() -> SapMode:
    raw = os.getenv("SAP_CPI_MODE", "mock").strip().lower()
    if raw in ("mock", "live", "disabled"):
        return raw  # type: ignore[return-value]
    return "mock"


def _base_url() -> str:
    return os.getenv("SAP_CPI_BASE_URL", "https://example-cpi.eu1.hana.ondemand.com").rstrip("/")


def _client_id() -> str:
    return os.getenv("SAP_CPI_CLIENT_ID", "").strip()


def _client_secret() -> str:
    return os.getenv("SAP_CPI_CLIENT_SECRET", "").strip()


def _token_url() -> str:
    return os.getenv("SAP_CPI_TOKEN_URL", f"{_base_url()}/oauth/token")


# ---------------------------------------------------------------------------
# Health telemetry (thread-safe singleton)
# ---------------------------------------------------------------------------


@dataclass
class _Telemetry:
    last_success_at: Optional[datetime] = None
    last_error_at: Optional[datetime] = None
    last_error: Optional[str] = None
    token_cached: Optional[str] = None
    token_valid_until: Optional[datetime] = None
    submissions_total: int = 0
    submissions_failed: int = 0
    events_received: int = 0
    lock: Lock = field(default_factory=Lock)

    def record_success(self):
        with self.lock:
            self.last_success_at = datetime.now(timezone.utc)
            self.submissions_total += 1

    def record_failure(self, msg: str):
        with self.lock:
            self.last_error_at = datetime.now(timezone.utc)
            self.last_error = msg
            self.submissions_total += 1
            self.submissions_failed += 1

    def record_event(self):
        with self.lock:
            self.events_received += 1


_T = _Telemetry()


def health() -> SapHealth:
    return SapHealth(
        mode=_mode(),
        base_url=_base_url() if _mode() != "disabled" else None,
        last_success_at=_T.last_success_at,
        last_error_at=_T.last_error_at,
        last_error=_T.last_error,
        token_valid_until=_T.token_valid_until,
        submissions_total=_T.submissions_total,
        submissions_failed=_T.submissions_failed,
        events_received=_T.events_received,
    )


def record_event_received() -> None:
    _T.record_event()


# ---------------------------------------------------------------------------
# OAuth2 token cache (live mode only)
# ---------------------------------------------------------------------------


def _fetch_token() -> Optional[str]:
    """Client-credentials flow against CPI's OAuth token URL. Caches until expiry."""

    if _T.token_cached and _T.token_valid_until and _T.token_valid_until > datetime.now(timezone.utc) + timedelta(seconds=60):
        return _T.token_cached
    if not _client_id() or not _client_secret():
        return None
    body = (
        f"grant_type=client_credentials&client_id={_client_id()}&client_secret={_client_secret()}"
    ).encode()
    req = _urlrequest.Request(
        _token_url(),
        data=body,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with _urlrequest.urlopen(req, timeout=15) as resp:
            payload = json.loads(resp.read().decode())
        access = payload.get("access_token")
        expires_in = int(payload.get("expires_in", 1800))
        if access:
            with _T.lock:
                _T.token_cached = access
                _T.token_valid_until = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
            return access
    except (_urlerror.URLError, _urlerror.HTTPError, TimeoutError, json.JSONDecodeError, KeyError, ValueError):
        pass
    return None


def _post(path: str, body: dict, timeout: int = 30) -> dict:
    """POST helper used by live mode. Raises on non-2xx; caller catches."""

    token = _fetch_token()
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = _urlrequest.Request(
        f"{_base_url()}{path}",
        data=json.dumps(body).encode(),
        method="POST",
        headers=headers,
    )
    with _urlrequest.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode() or "{}")


def _get(path: str, timeout: int = 30) -> dict:
    token = _fetch_token()
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = _urlrequest.Request(f"{_base_url()}{path}", method="GET", headers=headers)
    with _urlrequest.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode() or "{}")


# ---------------------------------------------------------------------------
# Mock-mode generators (so the workflow is testable without a CPI tenant)
# ---------------------------------------------------------------------------


_MOCK_PR_SEQ = 9000000
_MOCK_PO_SEQ = 4500000000
_MOCK_LOCK = Lock()


def _next_mock_pr() -> str:
    global _MOCK_PR_SEQ
    with _MOCK_LOCK:
        _MOCK_PR_SEQ += 1
        return str(_MOCK_PR_SEQ)


def _next_mock_po() -> str:
    global _MOCK_PO_SEQ
    with _MOCK_LOCK:
        _MOCK_PO_SEQ += 1
        return str(_MOCK_PO_SEQ)


def _maybe_mock_failure() -> Optional[str]:
    """Mock mode injects a small failure rate so the failed-state UI is testable."""

    if random.random() < 0.08:
        return random.choice([
            "BAPI_PR_CREATE: account assignment category 'X' is not defined for plant 1000",
            "Vendor 0000123456 is blocked for purchasing on 2026-05-13",
            "GL account 4100100 is locked for posting",
            "Material XYZ-001 not extended to plant 1000",
        ])
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def submit_pr(pr: PurchaseRequisition) -> dict[str, Any]:
    """Submit a Control Tower PR into SAP via CPI. Returns:

      { "sap_pr_no": str | None,
        "sap_status": "synced" | "failed",
        "error": str | None }
    """

    mode = _mode()
    if mode == "disabled":
        _T.record_failure("SAP CPI is disabled")
        return {"sap_pr_no": None, "sap_status": "failed", "error": "SAP CPI is disabled"}

    if mode == "mock":
        err = _maybe_mock_failure()
        if err:
            _T.record_failure(err)
            return {"sap_pr_no": None, "sap_status": "failed", "error": err}
        sap_pr = _next_mock_pr()
        _T.record_success()
        return {"sap_pr_no": sap_pr, "sap_status": "synced", "error": None}

    # live mode
    payload = {
        "ct_ref": pr.pr_no,
        "code": pr.code,
        "description": pr.description,
        "quantity": pr.quantity,
        "uom": pr.uom,
        "need_by": pr.need_by.isoformat() if pr.need_by else None,
        "buyer": pr.buyer,
        "project_id": pr.project_id,
        "budget_value_usd": pr.budget_value_usd,
    }
    try:
        reply = _post("/control-tower/pr", payload)
        sap_pr = reply.get("sap_pr_no")
        if sap_pr:
            _T.record_success()
            return {"sap_pr_no": sap_pr, "sap_status": "synced", "error": None}
        err = reply.get("error") or "CPI returned no sap_pr_no"
        _T.record_failure(err)
        return {"sap_pr_no": None, "sap_status": "failed", "error": err}
    except (_urlerror.URLError, _urlerror.HTTPError, TimeoutError, json.JSONDecodeError, KeyError, ValueError) as e:
        msg = f"{type(e).__name__}: {e}"
        _T.record_failure(msg)
        return {"sap_pr_no": None, "sap_status": "failed", "error": msg}


def submit_po(po: SourcingPO) -> dict[str, Any]:
    """Submit a sourcing PO into SAP via CPI."""

    mode = _mode()
    if mode == "disabled":
        _T.record_failure("SAP CPI is disabled")
        return {"sap_po_no": None, "sap_status": "failed", "error": "SAP CPI is disabled"}

    if mode == "mock":
        err = _maybe_mock_failure()
        if err:
            _T.record_failure(err)
            return {"sap_po_no": None, "sap_status": "failed", "error": err}
        sap_po = _next_mock_po()
        _T.record_success()
        return {"sap_po_no": sap_po, "sap_status": "synced", "error": None}

    payload = {
        "ct_ref": po.po_no,
        "vendor": po.vendor,
        "code": po.code,
        "description": po.description,
        "quantity": po.quantity,
        "uom": po.uom,
        "unit_price_usd": po.unit_price_usd,
        "value_usd": po.value_usd,
        "incoterm": po.incoterm,
        "need_by": po.need_by.isoformat() if po.need_by else None,
        "project_id": po.project_id,
        "rfq_no": po.rfq_no,
        "award_id": po.award_id,
    }
    try:
        reply = _post("/control-tower/po", payload)
        sap_po = reply.get("sap_po_no")
        if sap_po:
            _T.record_success()
            return {"sap_po_no": sap_po, "sap_status": "synced", "error": None}
        err = reply.get("error") or "CPI returned no sap_po_no"
        _T.record_failure(err)
        return {"sap_po_no": None, "sap_status": "failed", "error": err}
    except (_urlerror.URLError, _urlerror.HTTPError, TimeoutError, json.JSONDecodeError, KeyError, ValueError) as e:
        msg = f"{type(e).__name__}: {e}"
        _T.record_failure(msg)
        return {"sap_po_no": None, "sap_status": "failed", "error": msg}


def get_pr_status(sap_pr_no: str) -> dict[str, Any]:
    if _mode() == "mock":
        return {"status": random.choice(["released", "pending_release", "rejected"])}
    if _mode() == "disabled":
        return {"status": "unknown", "error": "SAP CPI is disabled"}
    try:
        return _get(f"/control-tower/pr/{sap_pr_no}")
    except Exception as e:  # noqa: BLE001
        return {"status": "unknown", "error": str(e)}


def get_po_status(sap_po_no: str) -> dict[str, Any]:
    if _mode() == "mock":
        return {
            "status": random.choice(["released", "in_transit", "gr_partial", "closed"]),
            "gr_qty": random.choice([0, 0, 0.5, 1.0]),
            "ir_value_usd": random.choice([0, 0, 0, 1000.0]),
        }
    if _mode() == "disabled":
        return {"status": "unknown", "error": "SAP CPI is disabled"}
    try:
        return _get(f"/control-tower/po/{sap_po_no}")
    except Exception as e:  # noqa: BLE001
        return {"status": "unknown", "error": str(e)}


# Master-data pulls — stubs for Phase 1; here so the interface is complete.


def pull_vendor_delta(since: Optional[datetime] = None) -> list[dict]:
    if _mode() != "live":
        return []
    try:
        ts = (since or (datetime.now(timezone.utc) - timedelta(days=1))).isoformat()
        return _get(f"/control-tower/master/vendors?since={ts}").get("vendors", [])
    except Exception:  # noqa: BLE001
        return []


def pull_material_delta(since: Optional[datetime] = None) -> list[dict]:
    if _mode() != "live":
        return []
    try:
        ts = (since or (datetime.now(timezone.utc) - timedelta(days=1))).isoformat()
        return _get(f"/control-tower/master/materials?since={ts}").get("materials", [])
    except Exception:  # noqa: BLE001
        return []
