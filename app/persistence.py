"""JSON snapshot persistence for in-memory state.

The app keeps its state in module-level dicts (sourcing._prs, planning._projects,
audit._events, etc). For production deployments without a database, this module
periodically dumps every store to disk as JSON and restores them on boot. Not
transactional — but good enough for pilots that need restart durability.

Trigger points:
  * On startup (FastAPI startup hook) → restore_all()
  * Every SNAPSHOT_INTERVAL_SECONDS (default 120) → snapshot_all()
  * On graceful shutdown (FastAPI shutdown hook) → snapshot_all()
  * On demand via POST /api/admin/snapshot (when exposed)
  * Write-through on every mutation → flush_critical() for approvals, audit,
    vendors, and sourcing (≤120s data-loss risk for those stores)

Storage layout (STATE_DIR, default ./.data):
  state/
    projects.json
    bom_items.json
    sourcing.json        ← PRs, RFQs, quotes, awards, POs, counter
    tbe.json             ← criteria, evaluations, weights
    logistics.json       ← shipments
    expediting.json      ← follow-up sent stamps (tenant → PO)
    audit.json           ← last 10k events
    sap_cpi.json         ← submission counters + last error
    .version             ← schema version sentinel
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger("ct.persistence")


SNAPSHOT_VERSION = 1
SNAPSHOT_INTERVAL = int(os.getenv("SNAPSHOT_INTERVAL_SECONDS", "120"))
STATE_DIR = Path(os.getenv("STATE_DIR", ".data"))
STATE_DIR.mkdir(parents=True, exist_ok=True)

_lock = threading.Lock()
_last_snapshot_at: Optional[datetime] = None
_last_snapshot_size: int = 0
_last_error: Optional[str] = None
_background_task: Optional[asyncio.Task] = None


def _path(name: str) -> Path:
    return STATE_DIR / name


def _dump_model_dict(d: dict) -> dict:
    """Serialise a dict whose values are Pydantic models (or anything with
    .model_dump()) into a plain JSON-friendly dict."""

    out = {}
    for k, v in d.items():
        if hasattr(v, "model_dump"):
            out[k] = v.model_dump(mode="json")
        elif isinstance(v, dict):
            # Nested map (e.g. _bom_items[project_id][bom_item_id])
            out[k] = _dump_model_dict(v)
        elif isinstance(v, list):
            out[k] = [item.model_dump(mode="json") if hasattr(item, "model_dump") else item for item in v]
        else:
            out[k] = v
    return out


def _load_model_dict(raw: dict, cls) -> dict:
    out = {}
    for k, v in raw.items():
        if isinstance(v, dict):
            try:
                out[k] = cls.model_validate(v)
            except Exception:  # noqa: BLE001
                # Nested map — recurse
                out[k] = _load_model_dict(v, cls)
        elif isinstance(v, list):
            out[k] = [cls.model_validate(item) for item in v]
        else:
            out[k] = v
    return out


# ----------------------------------------------------------------------------
# Per-module snapshot + restore
# ----------------------------------------------------------------------------


def _snap_projects() -> None:
    from . import planning
    from .schemas import BOMItem, Document, Project  # noqa: F401
    payload = {
        "projects":  {k: v.model_dump(mode="json") for k, v in planning._projects.items()},  # type: ignore[attr-defined]
        "bom_items": {p: {b: i.model_dump(mode="json") for b, i in items.items()}
                      for p, items in planning._bom_items.items()},  # type: ignore[attr-defined]
        "documents": {k: v.model_dump(mode="json") for k, v in planning._documents.items()},  # type: ignore[attr-defined]
    }
    _path("projects.json").write_text(json.dumps(payload, default=str, indent=0))


def _restore_projects() -> None:
    p = _path("projects.json")
    if not p.exists():
        return
    from . import planning
    from .schemas import BOMItem, Document, Project
    data = json.loads(p.read_text())
    planning._projects.clear()  # type: ignore[attr-defined]
    planning._projects.update({k: Project.model_validate(v) for k, v in data.get("projects", {}).items()})  # type: ignore[attr-defined]
    planning._bom_items.clear()  # type: ignore[attr-defined]
    for proj, items in data.get("bom_items", {}).items():
        planning._bom_items[proj] = {b: BOMItem.model_validate(i) for b, i in items.items()}  # type: ignore[attr-defined]
    planning._documents.clear()  # type: ignore[attr-defined]
    planning._documents.update({k: Document.model_validate(v) for k, v in data.get("documents", {}).items()})  # type: ignore[attr-defined]


def _snap_sourcing() -> None:
    from . import sourcing
    payload = {
        "prs":            {k: v.model_dump(mode="json") for k, v in sourcing._prs.items()},  # type: ignore[attr-defined]
        "rfqs":           {k: v.model_dump(mode="json") for k, v in sourcing._rfqs.items()},  # type: ignore[attr-defined]
        "quotes_by_rfq":  {r: [q.model_dump(mode="json") for q in qs]
                           for r, qs in sourcing._quotes_by_rfq.items()},  # type: ignore[attr-defined]
        "awards":         {k: v.model_dump(mode="json") for k, v in sourcing._awards.items()},  # type: ignore[attr-defined]
        "pos":            {k: v.model_dump(mode="json") for k, v in sourcing._pos.items()},  # type: ignore[attr-defined]
        "counter":        sourcing._counter,  # type: ignore[attr-defined]
        "seeded":         sourcing._seeded,  # type: ignore[attr-defined]
    }
    _path("sourcing.json").write_text(json.dumps(payload, default=str, indent=0))


def _restore_sourcing() -> None:
    p = _path("sourcing.json")
    if not p.exists():
        return
    from . import sourcing
    from .schemas import Award, PurchaseRequisition, Quote, RFQ, SourcingPO
    data = json.loads(p.read_text())
    sourcing._prs.clear()  # type: ignore[attr-defined]
    sourcing._prs.update({k: PurchaseRequisition.model_validate(v) for k, v in data.get("prs", {}).items()})  # type: ignore[attr-defined]
    sourcing._rfqs.clear()  # type: ignore[attr-defined]
    sourcing._rfqs.update({k: RFQ.model_validate(v) for k, v in data.get("rfqs", {}).items()})  # type: ignore[attr-defined]
    sourcing._quotes_by_rfq.clear()  # type: ignore[attr-defined]
    for r, qs in data.get("quotes_by_rfq", {}).items():
        sourcing._quotes_by_rfq[r] = [Quote.model_validate(q) for q in qs]  # type: ignore[attr-defined]
    sourcing._awards.clear()  # type: ignore[attr-defined]
    sourcing._awards.update({k: Award.model_validate(v) for k, v in data.get("awards", {}).items()})  # type: ignore[attr-defined]
    sourcing._pos.clear()  # type: ignore[attr-defined]
    sourcing._pos.update({k: SourcingPO.model_validate(v) for k, v in data.get("pos", {}).items()})  # type: ignore[attr-defined]
    if "counter" in data:
        sourcing._counter.update(data["counter"])  # type: ignore[attr-defined]
    sourcing._seeded = bool(data.get("seeded", False))  # type: ignore[attr-defined]


def _snap_tbe() -> None:
    from . import tbe
    payload = {
        "criteria_by_rfq": {r: [c.model_dump(mode="json") for c in cs]
                            for r, cs in tbe._criteria_by_rfq.items()},  # type: ignore[attr-defined]
        "evaluations":     {r: {q: e.model_dump(mode="json") for q, e in m.items()}
                            for r, m in tbe._evaluations.items()},  # type: ignore[attr-defined]
        "weights":         {r: list(t) for r, t in tbe._weights.items()},  # type: ignore[attr-defined]
    }
    _path("tbe.json").write_text(json.dumps(payload, default=str, indent=0))


def _restore_tbe() -> None:
    p = _path("tbe.json")
    if not p.exists():
        return
    from . import tbe
    from .schemas import TechnicalCriterion, TechnicalEvaluation
    data = json.loads(p.read_text())
    tbe._criteria_by_rfq.clear()  # type: ignore[attr-defined]
    for r, cs in data.get("criteria_by_rfq", {}).items():
        tbe._criteria_by_rfq[r] = [TechnicalCriterion.model_validate(c) for c in cs]  # type: ignore[attr-defined]
    tbe._evaluations.clear()  # type: ignore[attr-defined]
    for r, m in data.get("evaluations", {}).items():
        tbe._evaluations[r] = {q: TechnicalEvaluation.model_validate(e) for q, e in m.items()}  # type: ignore[attr-defined]
    tbe._weights.clear()  # type: ignore[attr-defined]
    for r, pair in data.get("weights", {}).items():
        tbe._weights[r] = (float(pair[0]), float(pair[1]))  # type: ignore[attr-defined]


def _snap_logistics() -> None:
    from . import logistics
    # Internal store name may differ; guard with getattr
    shipments = getattr(logistics, "_shipments", None)
    if shipments is None:
        return
    payload = {k: v.model_dump(mode="json") for k, v in shipments.items()}
    _path("logistics.json").write_text(json.dumps(payload, default=str, indent=0))


def _restore_logistics() -> None:
    p = _path("logistics.json")
    if not p.exists():
        return
    from . import logistics
    from .schemas import Shipment
    shipments = getattr(logistics, "_shipments", None)
    if shipments is None:
        return
    data = json.loads(p.read_text())
    shipments.clear()
    shipments.update({k: Shipment.model_validate(v) for k, v in data.items()})


def _snap_expediting() -> None:
    from . import expediting
    _path("expediting.json").write_text(
        json.dumps(expediting.dump_followups(), default=str, indent=0)
    )


def _restore_expediting() -> None:
    p = _path("expediting.json")
    if not p.exists():
        return
    from . import expediting
    try:
        expediting.load_followups(json.loads(p.read_text()))
    except Exception as e:  # noqa: BLE001
        log.warning("expediting restore skipped: %s", e)


def _snap_audit() -> None:
    from . import audit
    payload = [e.model_dump(mode="json") for e in list(audit._events)]  # type: ignore[attr-defined]
    _path("audit.json").write_text(json.dumps(payload, default=str, indent=0))


def _restore_audit() -> None:
    p = _path("audit.json")
    if not p.exists():
        return
    from . import audit
    from .schemas import AuditEvent
    data = json.loads(p.read_text())
    audit._events.clear()  # type: ignore[attr-defined]
    for evt in data:
        try:
            audit._events.append(AuditEvent.model_validate(evt))  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            continue


def _snap_sap() -> None:
    try:
        from .integrations import sap_cpi
        t = sap_cpi._T  # type: ignore[attr-defined]
        payload = {
            "last_success_at": t.last_success_at.isoformat() if t.last_success_at else None,
            "last_error_at":   t.last_error_at.isoformat()   if t.last_error_at else None,
            "last_error":      t.last_error,
            "submissions_total":  t.submissions_total,
            "submissions_failed": t.submissions_failed,
            "events_received":    t.events_received,
        }
        _path("sap_cpi.json").write_text(json.dumps(payload, default=str, indent=0))
    except Exception as e:  # noqa: BLE001
        log.warning("sap_cpi snapshot skipped: %s", e)


def _restore_sap() -> None:
    p = _path("sap_cpi.json")
    if not p.exists():
        return
    try:
        from .integrations import sap_cpi
        data = json.loads(p.read_text())
        t = sap_cpi._T  # type: ignore[attr-defined]
        if data.get("last_success_at"):
            t.last_success_at = datetime.fromisoformat(data["last_success_at"])
        if data.get("last_error_at"):
            t.last_error_at = datetime.fromisoformat(data["last_error_at"])
        t.last_error = data.get("last_error")
        t.submissions_total = int(data.get("submissions_total", 0))
        t.submissions_failed = int(data.get("submissions_failed", 0))
        t.events_received = int(data.get("events_received", 0))
    except Exception as e:  # noqa: BLE001
        log.warning("sap_cpi restore skipped: %s", e)


# ----------------------------------------------------------------------------
# Public API
# ----------------------------------------------------------------------------


def _snap_vendors() -> None:
    from . import vendor_store
    _path("vendors.json").write_text(
        json.dumps(vendor_store.dump(), default=str, indent=0)
    )


def _restore_vendors() -> None:
    p = _path("vendors.json")
    if not p.exists():
        return
    from . import vendor_store
    try:
        vendor_store.load(json.loads(p.read_text()))
    except Exception as e:  # noqa: BLE001
        log.warning("vendor_store restore skipped: %s", e)


def _snap_approvals() -> None:
    from . import approvals
    _path("approvals.json").write_text(
        json.dumps(approvals.dump(), default=str, indent=0)
    )


def _restore_approvals() -> None:
    p = _path("approvals.json")
    if not p.exists():
        return
    from . import approvals
    try:
        approvals.load(json.loads(p.read_text()))
    except Exception as e:  # noqa: BLE001
        log.warning("approvals restore skipped: %s", e)


_CRITICAL_FILES = ("approvals.json", "audit.json", "vendors.json", "sourcing.json", ".version")


def flush_critical() -> dict:
    """Write-through snapshot for critical stores.

    Flushes approvals, audit, vendors, and sourcing so gated procurement writes
    and vendor onboarding survive crashes without waiting for the 120s timer.
    Does not replace the periodic snapshot_all() loop.
    """
    global _last_snapshot_at, _last_snapshot_size, _last_error

    with _lock:
        try:
            _snap_approvals()
            _snap_audit()
            _snap_vendors()
            _snap_sourcing()
            _path(".version").write_text(str(SNAPSHOT_VERSION))
            total_size = sum(
                _path(name).stat().st_size
                for name in _CRITICAL_FILES
                if _path(name).exists()
            )
            _last_snapshot_at = datetime.now(timezone.utc)
            _last_snapshot_size = total_size
            _last_error = None
            log.info("critical flush ok: %d bytes across %s", total_size, _CRITICAL_FILES)
            return {
                "ok": True,
                "bytes": total_size,
                "at": _last_snapshot_at.isoformat(),
                "stores": ["approvals", "audit", "vendors", "sourcing"],
            }
        except Exception as e:  # noqa: BLE001
            _last_error = f"{type(e).__name__}: {e}"
            log.exception("critical flush failed")
            return {"ok": False, "error": _last_error}


def snapshot_all() -> dict:
    """Write every module's state to disk. Safe to call any time."""
    global _last_snapshot_at, _last_snapshot_size, _last_error

    with _lock:
        try:
            _snap_projects()
            _snap_sourcing()
            _snap_tbe()
            _snap_logistics()
            _snap_expediting()
            _snap_audit()
            _snap_sap()
            _snap_vendors()
            _snap_approvals()
            _path(".version").write_text(str(SNAPSHOT_VERSION))
            total_size = sum(p.stat().st_size for p in STATE_DIR.iterdir() if p.is_file())
            _last_snapshot_at = datetime.now(timezone.utc)
            _last_snapshot_size = total_size
            _last_error = None
            log.info("snapshot ok: %d bytes across %s", total_size, STATE_DIR)
            return {"ok": True, "bytes": total_size, "at": _last_snapshot_at.isoformat()}
        except Exception as e:  # noqa: BLE001
            _last_error = f"{type(e).__name__}: {e}"
            log.exception("snapshot failed")
            return {"ok": False, "error": _last_error}


def restore_all() -> dict:
    """Read snapshots from disk back into the in-memory stores. No-op if no
    snapshot exists (fresh boot)."""

    version_file = _path(".version")
    if not version_file.exists():
        log.info("no snapshot at %s, starting fresh", STATE_DIR)
        return {"restored": False, "reason": "no snapshot"}

    with _lock:
        try:
            _restore_projects()
            _restore_sourcing()
            _restore_tbe()
            _restore_logistics()
            _restore_expediting()
            _restore_audit()
            _restore_sap()
            _restore_vendors()
            _restore_approvals()
            log.info("snapshot restored from %s", STATE_DIR)
            return {"restored": True, "from": str(STATE_DIR)}
        except Exception as e:  # noqa: BLE001
            log.exception("snapshot restore failed")
            return {"restored": False, "error": f"{type(e).__name__}: {e}"}


def snapshot_status() -> dict:
    return {
        "state_dir": str(STATE_DIR),
        "interval_seconds": SNAPSHOT_INTERVAL,
        "last_snapshot_at": _last_snapshot_at.isoformat() if _last_snapshot_at else None,
        "last_snapshot_bytes": _last_snapshot_size,
        "last_error": _last_error,
        "version": SNAPSHOT_VERSION,
    }


# ----------------------------------------------------------------------------
# Background scheduler
# ----------------------------------------------------------------------------


async def _snapshot_loop() -> None:
    log.info("snapshot loop running every %ds → %s", SNAPSHOT_INTERVAL, STATE_DIR)
    while True:
        try:
            await asyncio.sleep(SNAPSHOT_INTERVAL)
            await asyncio.to_thread(snapshot_all)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            log.exception("snapshot loop iteration failed")


def start_background_snapshot() -> None:
    """Kick off the periodic snapshot task on the running event loop."""

    global _background_task
    if _background_task and not _background_task.done():
        return
    try:
        loop = asyncio.get_event_loop()
        _background_task = loop.create_task(_snapshot_loop())
        log.info("background snapshot scheduler started")
    except RuntimeError:
        # No running loop (e.g. in a test) — caller can invoke snapshot_all() manually
        log.warning("no event loop; snapshot scheduler not started")
