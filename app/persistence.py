"""JSON snapshot persistence for in-memory state.

The app keeps its state in module-level dicts (sourcing._prs, planning._projects,
audit._events, etc). For production deployments without a database, this module
periodically dumps every store to disk as JSON and restores them on boot. Not
transactional across stores, but each file is written atomically (temp file +
fsync + rename), and restore is per store and per record: a bad file or row is
logged, copied aside as `<name>.corrupt-<UTC stamp>`, and never takes the other
stores down with it.

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
import shutil
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
_restore_report: dict = {}


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


def _write_text(name: str, text: str) -> None:
    """Atomic write: temp file in the same dir, fsync, then rename over the
    target. A crash mid-write leaves the previous file intact, never a
    truncated one."""

    target = _path(name)
    tmp = target.with_name(f".{target.name}.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, target)


def _write_json(name: str, payload: Any) -> None:
    _write_text(name, json.dumps(payload, default=str, indent=0))


def _read_json(name: str) -> Any:
    """Parsed snapshot file, or None when it doesn't exist."""

    p = _path(name)
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


# Records dropped during the current store's restore. Reset per store by
# restore_all(); a non-empty list means the file gets a quarantine copy.
_skipped: list[str] = []


def _valid(cls, raw: Any, where: str):
    """Validate one record; on failure log it, remember it, return None so a
    single bad row (e.g. an enum value from a newer build) can't take the
    whole store down with it."""

    try:
        return cls.model_validate(raw)
    except Exception as e:  # noqa: BLE001
        _skipped.append(where)
        log.warning("restore: skipped %s (%s: %s)", where, type(e).__name__, e)
        return None


def _valid_map(cls, raw: Optional[dict], where: str) -> dict:
    out = {}
    for k, v in (raw or {}).items():
        m = _valid(cls, v, f"{where}[{k}]")
        if m is not None:
            out[k] = m
    return out


def _valid_list(cls, raw: Optional[list], where: str) -> list:
    out = []
    for i, v in enumerate(raw or []):
        m = _valid(cls, v, f"{where}[{i}]")
        if m is not None:
            out.append(m)
    return out


def _quarantine(name: str) -> Optional[str]:
    """Copy a snapshot file aside before the next flush can overwrite it."""

    p = _path(name)
    if not p.exists():
        return None
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dest = p.with_name(f"{p.name}.corrupt-{stamp}")
    shutil.copy2(p, dest)
    return dest.name


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
    _write_json("projects.json", payload)


def _restore_projects() -> None:
    data = _read_json("projects.json")
    if data is None:
        return
    from . import planning
    from .schemas import BOMItem, Document, Project
    projects = _valid_map(Project, data.get("projects"), "projects")
    bom = {proj: _valid_map(BOMItem, items, f"bom_items[{proj}]")
           for proj, items in (data.get("bom_items") or {}).items()}
    documents = _valid_map(Document, data.get("documents"), "documents")
    planning._projects.clear()  # type: ignore[attr-defined]
    planning._projects.update(projects)  # type: ignore[attr-defined]
    planning._bom_items.clear()  # type: ignore[attr-defined]
    planning._bom_items.update(bom)  # type: ignore[attr-defined]
    planning._documents.clear()  # type: ignore[attr-defined]
    planning._documents.update(documents)  # type: ignore[attr-defined]


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
        "sap_seen":       sourcing._sap_seen,  # type: ignore[attr-defined]
    }
    _write_json("sourcing.json", payload)


def _restore_sourcing() -> None:
    data = _read_json("sourcing.json")
    if data is None:
        return
    from . import sourcing
    from .schemas import Award, PurchaseRequisition, Quote, RFQ, SourcingPO
    prs = _valid_map(PurchaseRequisition, data.get("prs"), "prs")
    rfqs = _valid_map(RFQ, data.get("rfqs"), "rfqs")
    quotes = {r: _valid_list(Quote, qs, f"quotes_by_rfq[{r}]")
              for r, qs in (data.get("quotes_by_rfq") or {}).items()}
    awards = _valid_map(Award, data.get("awards"), "awards")
    pos = _valid_map(SourcingPO, data.get("pos"), "pos")
    counter = {k: int(v) for k, v in (data.get("counter") or {}).items()}
    sap_seen = {str(k): str(v) for k, v in (data.get("sap_seen") or {}).items()}
    sourcing._prs.clear()  # type: ignore[attr-defined]
    sourcing._prs.update(prs)  # type: ignore[attr-defined]
    sourcing._rfqs.clear()  # type: ignore[attr-defined]
    sourcing._rfqs.update(rfqs)  # type: ignore[attr-defined]
    sourcing._quotes_by_rfq.clear()  # type: ignore[attr-defined]
    sourcing._quotes_by_rfq.update(quotes)  # type: ignore[attr-defined]
    sourcing._awards.clear()  # type: ignore[attr-defined]
    sourcing._awards.update(awards)  # type: ignore[attr-defined]
    sourcing._pos.clear()  # type: ignore[attr-defined]
    sourcing._pos.update(pos)  # type: ignore[attr-defined]
    sourcing._counter.update(counter)  # type: ignore[attr-defined]
    sourcing._sap_seen.clear()  # type: ignore[attr-defined]
    sourcing._sap_seen.update(sap_seen)  # type: ignore[attr-defined]
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
    _write_json("tbe.json", payload)


def _restore_tbe() -> None:
    data = _read_json("tbe.json")
    if data is None:
        return
    from . import tbe
    from .schemas import TechnicalCriterion, TechnicalEvaluation
    criteria = {r: _valid_list(TechnicalCriterion, cs, f"criteria_by_rfq[{r}]")
                for r, cs in (data.get("criteria_by_rfq") or {}).items()}
    evaluations = {r: _valid_map(TechnicalEvaluation, m, f"evaluations[{r}]")
                   for r, m in (data.get("evaluations") or {}).items()}
    weights = {r: (float(pair[0]), float(pair[1]))
               for r, pair in (data.get("weights") or {}).items()}
    tbe._criteria_by_rfq.clear()  # type: ignore[attr-defined]
    tbe._criteria_by_rfq.update(criteria)  # type: ignore[attr-defined]
    tbe._evaluations.clear()  # type: ignore[attr-defined]
    tbe._evaluations.update(evaluations)  # type: ignore[attr-defined]
    tbe._weights.clear()  # type: ignore[attr-defined]
    tbe._weights.update(weights)  # type: ignore[attr-defined]


def _snap_logistics() -> None:
    from . import logistics
    # Internal store name may differ; guard with getattr
    shipments = getattr(logistics, "_shipments", None)
    if shipments is None:
        return
    payload = {k: v.model_dump(mode="json") for k, v in shipments.items()}
    _write_json("logistics.json", payload)


def _restore_logistics() -> None:
    from . import logistics
    from .schemas import Shipment
    shipments = getattr(logistics, "_shipments", None)
    if shipments is None:
        return
    data = _read_json("logistics.json")
    if data is None:
        return
    restored = _valid_map(Shipment, data, "shipments")
    shipments.clear()
    shipments.update(restored)


def _snap_expediting() -> None:
    from . import expediting
    _write_json("expediting.json", expediting.dump_followups())


def _restore_expediting() -> None:
    data = _read_json("expediting.json")
    if data is None:
        return
    from . import expediting
    expediting.load_followups(data)


def _snap_audit() -> None:
    from . import audit
    payload = [e.model_dump(mode="json") for e in list(audit._events)]  # type: ignore[attr-defined]
    _write_json("audit.json", payload)


def _restore_audit() -> None:
    data = _read_json("audit.json")
    if data is None:
        return
    from . import audit
    from .schemas import AuditEvent
    events = _valid_list(AuditEvent, data, "audit")
    audit._events.clear()  # type: ignore[attr-defined]
    audit._events.extend(events)  # type: ignore[attr-defined]


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
        _write_json("sap_cpi.json", payload)
    except Exception as e:  # noqa: BLE001
        log.warning("sap_cpi snapshot skipped: %s", e)


def _restore_sap() -> None:
    data = _read_json("sap_cpi.json")
    if data is None:
        return
    from .integrations import sap_cpi
    t = sap_cpi._T  # type: ignore[attr-defined]
    if data.get("last_success_at"):
        t.last_success_at = datetime.fromisoformat(data["last_success_at"])
    if data.get("last_error_at"):
        t.last_error_at = datetime.fromisoformat(data["last_error_at"])
    t.last_error = data.get("last_error")
    t.submissions_total = int(data.get("submissions_total", 0))
    t.submissions_failed = int(data.get("submissions_failed", 0))
    t.events_received = int(data.get("events_received", 0))


# ----------------------------------------------------------------------------
# Public API
# ----------------------------------------------------------------------------


def _snap_vendors() -> None:
    from . import vendor_store
    _write_json("vendors.json", vendor_store.dump())


def _restore_vendors() -> None:
    data = _read_json("vendors.json")
    if data is None:
        return
    from . import vendor_store
    from .schemas import SupplierRecord
    # Filter to rows that validate, then hand the module raw dicts as before.
    kept = {
        tid: [r for i, r in enumerate(rows or [])
              if _valid(SupplierRecord, r, f"vendors[{tid}][{i}]") is not None]
        for tid, rows in data.items()
    }
    vendor_store.load(kept)


def _snap_approvals() -> None:
    from . import approvals
    _write_json("approvals.json", approvals.dump())


def _restore_approvals() -> None:
    data = _read_json("approvals.json")
    if data is None:
        return
    from . import approvals
    from .schemas import Approval
    kept = {
        tid: {aid: a for aid, a in (bucket or {}).items()
              if _valid(Approval, a, f"approvals[{tid}][{aid}]") is not None}
        for tid, bucket in (data.get("approvals") or {}).items()
    }
    approvals.load({"counter": data.get("counter") or {}, "approvals": kept})


def _snap_risks() -> None:
    from . import risk_register
    _write_json("risks.json", risk_register.dump())


def _restore_risks() -> None:
    data = _read_json("risks.json")
    if data is None:
        return
    from . import risk_register
    from .schemas import ManagedRisk
    kept = {
        tid: {rid: r for rid, r in (bucket or {}).items()
              if _valid(ManagedRisk, r, f"risks[{tid}][{rid}]") is not None}
        for tid, bucket in (data.get("risks") or {}).items()
    }
    risk_register.load({"counter": data.get("counter") or {}, "risks": kept})


_CRITICAL_FILES = (
    "approvals.json", "audit.json", "vendors.json", "sourcing.json", "risks.json", ".version",
)


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
            _snap_risks()
            _write_text(".version", str(SNAPSHOT_VERSION))
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
                "stores": ["approvals", "audit", "vendors", "sourcing", "risks"],
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
            _snap_risks()
            _write_text(".version", str(SNAPSHOT_VERSION))
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

    global _restore_report

    version_file = _path(".version")
    if not version_file.exists():
        log.info("no snapshot at %s, starting fresh", STATE_DIR)
        return {"restored": False, "reason": "no snapshot"}

    raw_version = version_file.read_text().strip()
    try:
        on_disk = int(raw_version)
    except ValueError:
        on_disk = SNAPSHOT_VERSION
        log.warning("unreadable snapshot version %r; assuming %d", raw_version, on_disk)
    if on_disk > SNAPSHOT_VERSION:
        # Written by a newer build. Restoring would drop fields and the next
        # flush would overwrite them — refuse to boot instead.
        raise RuntimeError(
            f"Snapshot in {STATE_DIR} is version {on_disk}, this build reads "
            f"up to {SNAPSHOT_VERSION}. Deploy the newer build or restore a backup."
        )

    stores = (
        ("projects.json", _restore_projects),
        ("sourcing.json", _restore_sourcing),
        ("tbe.json", _restore_tbe),
        ("logistics.json", _restore_logistics),
        ("expediting.json", _restore_expediting),
        ("audit.json", _restore_audit),
        ("sap_cpi.json", _restore_sap),
        ("vendors.json", _restore_vendors),
        ("approvals.json", _restore_approvals),
        ("risks.json", _restore_risks),
    )
    errors: dict[str, str] = {}
    skipped: dict[str, int] = {}
    quarantined: list[str] = []
    with _lock:
        # Each store restores on its own: one bad file must not leave the
        # others empty (and then get them overwritten by the next flush).
        for name, restore in stores:
            _skipped.clear()
            try:
                restore()
            except Exception as e:  # noqa: BLE001
                errors[name] = f"{type(e).__name__}: {e}"
                log.error("restore of %s failed — keeping a copy: %s", name, errors[name])
                _mark_seeded_after_failed_restore(name)
            if _skipped:
                skipped[name] = len(_skipped)
            if name in errors or name in skipped:
                copy = _quarantine(name)
                if copy:
                    quarantined.append(copy)
        _skipped.clear()

    _restore_report = {"errors": errors, "skipped_records": skipped, "quarantined": quarantined}
    if errors or skipped:
        log.error("snapshot restored with problems from %s: %s", STATE_DIR, _restore_report)
    else:
        log.info("snapshot restored from %s", STATE_DIR)
    return {"restored": True, "from": str(STATE_DIR), **_restore_report}


def _mark_seeded_after_failed_restore(name: str) -> None:
    """A store whose snapshot failed to load must not lazily seed demo data
    into the gap — that would then be flushed over the real file."""

    if name == "projects.json":
        from . import planning
        planning._restore_failed = True  # type: ignore[attr-defined]
    elif name == "sourcing.json":
        from . import sourcing
        sourcing._seeded = True  # type: ignore[attr-defined]
    elif name == "logistics.json":
        from . import logistics
        logistics._seeded = True  # type: ignore[attr-defined]


def snapshot_status() -> dict:
    return {
        "state_dir": str(STATE_DIR),
        "interval_seconds": SNAPSHOT_INTERVAL,
        "last_snapshot_at": _last_snapshot_at.isoformat() if _last_snapshot_at else None,
        "last_snapshot_bytes": _last_snapshot_size,
        "last_error": _last_error,
        "version": SNAPSHOT_VERSION,
        "last_restore": _restore_report,
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
