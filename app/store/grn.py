"""GRN create-from-sync + confirm_grn() — the sole state-mutating path.

confirm_grn() is callable identically from the field device confirm screen
or the office triage queue. Per-request rule: SQLite transaction commits
first, dict-store effects (sourcing PO, audit, logistics) run second and are
individually best-effort, and invalidate_all() runs last. Damaged/rejected
qty never touches the ledger or a PO — only qty_received does.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from datetime import datetime, timezone
from functools import lru_cache
from typing import Dict, List, Optional, Set, Tuple

from fastapi import HTTPException

from . import matching
from .db import MEDIA_DIR, connect, new_id
from ..schemas import (
    AddShipmentEventRequest,
    ConfirmGrnReply,
    ConfirmGrnRequest,
    DeviceContext,
    FieldGrnRecord,
    GrnDetail,
    GrnLineOut,
    GrnSummary,
    GrnSyncReply,
    MatchCandidate,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _fallback_code(description_raw: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "-", description_raw or "").strip("-").upper()[:24]
    return f"UNCODED-{slug}" if slug else "UNCODED"


@lru_cache(maxsize=256)
def _store_name(tenant_id: str, store_id: str) -> Optional[str]:
    """Store names are create-only in v1 (no rename route), so this is cached
    rather than opening a connection on every delivered-shipment event."""

    conn = connect()
    try:
        row = conn.execute(
            "SELECT name FROM site_stores WHERE store_id = ? AND tenant_id = ?",
            (store_id, tenant_id),
        ).fetchone()
        return row["name"] if row else None
    finally:
        conn.close()


# --- Create from field sync --------------------------------------------------


def create_from_sync(device: DeviceContext, record: FieldGrnRecord, photo_bytes: bytes) -> GrnSyncReply:
    digest = hashlib.sha256(photo_bytes).hexdigest()
    if digest != record.photo_sha256:
        raise HTTPException(status_code=422, detail="Photo checksum mismatch")

    photo_dir = MEDIA_DIR / device.tenant_id
    photo_path = photo_dir / f"{record.grn_id}.jpg"

    from .. import llm

    if record.source_kind == "free_issue" or not llm.is_enabled():
        extraction_status = "skipped"
    else:
        extraction_status = "pending"

    now_iso = _iso(_now())

    conn = connect()
    try:
        try:
            cur = conn.execute(
                """INSERT INTO grn
                   (grn_id, grn_no, tenant_id, store_id, project_id, device_id,
                    sequence_no, status, source_kind, challan_no, challan_date,
                    vendor_name_raw, vendor_name, vehicle_no, remarks,
                    photo_path, photo_sha256, extraction_status,
                    extraction_json, extraction_model, observed_at,
                    device_clock_offset_ms, clock_trust, received_at,
                    confirmed_at, confirmed_by, confirmed_via, superseded_by, created_at)
                   VALUES (?, NULL, ?, ?, ?, ?, ?, 'captured', ?, ?, ?, ?, NULL, ?, ?,
                           ?, ?, ?, NULL, NULL, ?, ?, 'device', ?, NULL, NULL, NULL, NULL, ?)
                   ON CONFLICT(grn_id) DO NOTHING""",
                (
                    record.grn_id, device.tenant_id, device.store_id, device.project_id,
                    device.device_id, record.sequence_no, record.source_kind,
                    record.challan_no, record.challan_date, record.vendor_name_raw,
                    record.vehicle_no, record.remarks,
                    str(photo_path), digest, extraction_status,
                    record.observed_at, record.device_clock_offset_ms,
                    now_iso, now_iso,
                ),
            )
        except sqlite3.IntegrityError:
            # UNIQUE(device_id, sequence_no): this device already synced a
            # different GRN under that number. Hand back the watermark so the
            # client can resume above it instead of retrying forever.
            watermark = conn.execute(
                "SELECT last_sequence_no FROM capture_devices WHERE device_id = ?",
                (device.device_id,),
            ).fetchone()
            raise HTTPException(
                status_code=409,
                detail=(
                    f"sequence_no {record.sequence_no} already used by this device "
                    f"(last_sequence_no {watermark['last_sequence_no'] if watermark else 0})"
                ),
            )

        if cur.rowcount == 0:
            existing = conn.execute(
                "SELECT status FROM grn WHERE grn_id = ?", (record.grn_id,)
            ).fetchone()
            conn.commit()
            return GrnSyncReply(
                grn_id=record.grn_id,
                status=existing["status"] if existing else "captured",
                duplicate=True,
            )

        # Newly inserted — only now is it safe to write the photo. A duplicate
        # sync must never overwrite the stored challan image.
        photo_dir.mkdir(parents=True, exist_ok=True)
        photo_path.write_bytes(photo_bytes)

        for line in record.lines:
            conn.execute(
                """INSERT INTO grn_lines
                   (grn_line_id, grn_id, line_no, description_raw, code, uom_raw, uom,
                    qty_challan, qty_received, qty_damaged, qty_rejected, batch_no,
                    po_no, match_status, match_confidence, match_candidates, matched_by,
                    over_receipt)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, 'unmatched', NULL, NULL, NULL, 0)""",
                (
                    new_id(), record.grn_id, line.line_no, line.description_raw,
                    line.code, line.uom_raw, matching.canonical_uom(line.uom_raw),
                    line.qty_challan, line.qty_received, line.qty_damaged,
                    line.qty_rejected, line.batch_no,
                ),
            )

        if record.source_kind == "free_issue":
            if record.lines:
                conn.execute(
                    "UPDATE grn_lines SET match_status = 'no_po' WHERE grn_id = ?",
                    (record.grn_id,),
                )
                header_status = "suggested"
            else:
                header_status = "triage"
            conn.execute("UPDATE grn SET status = ? WHERE grn_id = ?", (header_status, record.grn_id))
        elif extraction_status == "skipped":
            # LLM disabled — band synchronously (deterministic for tests).
            matching.apply_bands(conn, record.grn_id)
        # else: extraction_status == 'pending' — leave 'captured' for the async worker.

        conn.execute(
            "UPDATE capture_devices SET last_sequence_no = MAX(last_sequence_no, ?) WHERE device_id = ?",
            (record.sequence_no, device.device_id),
        )
        conn.commit()

        final = conn.execute("SELECT status FROM grn WHERE grn_id = ?", (record.grn_id,)).fetchone()
        return GrnSyncReply(grn_id=record.grn_id, status=final["status"], duplicate=False)
    finally:
        conn.close()


# --- Confirm ------------------------------------------------------------------


def _reply_from_stored(conn, grn_id: str) -> ConfirmGrnReply:
    header = conn.execute("SELECT * FROM grn WHERE grn_id = ?", (grn_id,)).fetchone()
    lines = conn.execute("SELECT * FROM grn_lines WHERE grn_id = ?", (grn_id,)).fetchall()
    ledger_count = conn.execute(
        "SELECT COUNT(*) AS n FROM stock_ledger WHERE ref_kind = 'grn' AND ref_id = ?", (grn_id,)
    ).fetchone()["n"]
    pos_updated = sorted({l["po_no"] for l in lines if l["po_no"]})

    from .. import sourcing
    pos_delivered = [
        po_no for po_no in pos_updated
        if (po := sourcing.get_po(po_no, tenant_id=header["tenant_id"])) and po.status == "delivered"
    ]
    return ConfirmGrnReply(
        grn_id=grn_id, grn_no=header["grn_no"], status=header["status"],
        ledger_entries=ledger_count, pos_updated=pos_updated, pos_delivered=pos_delivered,
    )


def _confirm_line_values(line, submitted) -> Tuple[Optional[str], str, float, float, float]:
    """(po_no, match_status, qty_received, qty_damaged, qty_rejected) for one
    stored line under one (possibly absent) ConfirmLine.

    A line omitted from the request KEEPS its captured quantities and is banded
    no_po: the storekeeper's counts are claims evidence, never destroyed by a
    partial confirm, and unmatched stock still belongs in the ledger.
    """

    if submitted is None:
        return None, "no_po", line["qty_received"], line["qty_damaged"], line["qty_rejected"]
    po_no = submitted.po_no if not submitted.no_po else None
    return (
        po_no,
        "confirmed" if po_no else "no_po",
        submitted.qty_received,
        submitted.qty_damaged,
        submitted.qty_rejected,
    )


def _submitted_keys(all_lines, req: ConfirmGrnRequest) -> Set[tuple]:
    """Per-line replay key for the incoming request, normalised exactly the way
    confirm writes it — so a replay that omits the same lines still matches."""

    submitted_by_no = {ln.line_no: ln for ln in req.lines}
    keys: Set[tuple] = set()
    for line in all_lines:
        po_no, _status, qty_received, qty_damaged, qty_rejected = _confirm_line_values(
            line, submitted_by_no.get(line["line_no"])
        )
        keys.add((line["line_no"], po_no, qty_received, qty_damaged, qty_rejected))
    return keys


def _stored_keys(stored_lines) -> Set[tuple]:
    """The same key shape read back off a confirmed GRN."""

    return {
        (l["line_no"], l["po_no"], l["qty_received"], l["qty_damaged"], l["qty_rejected"])
        for l in stored_lines
    }


def _next_grn_no(conn, tenant_id: str) -> str:
    """Next GRN number, global across tenants: grn_no carries a table-wide
    UNIQUE constraint, so numbering must draw from the global MAX or two
    tenants would both derive the same first number and the retry could
    never resolve it."""

    row = conn.execute(
        "SELECT MAX(CAST(SUBSTR(grn_no, 5) AS INTEGER)) AS n FROM grn "
        "WHERE grn_no IS NOT NULL"
    ).fetchone()
    return f"GRN-{(row['n'] or 0) + 1:05d}"


def _apply_confirm_effects(
    *,
    grn_id: str,
    grn_no: str,
    tenant_id: str,
    project_id: str,
    store_id: str,
    matched_pos: List[tuple],
    ledger_count: int,
    actor: str,
    via: str,
    resumed: bool = False,
) -> Tuple[List[str], List[str]]:
    """Phase 2 of a confirm: dict-store PO receipts, audit events, logistics
    delivered events, cache invalidation. Individually best-effort — the SQLite
    transaction has already committed by the time this runs.

    Shared by confirm_grn() and startup_sweep() so a resumed GRN produces
    exactly the same effects as a live one. Returns (pos_updated, pos_delivered),
    both deduped by po_no: two GRN lines against one PO are one delivery.
    """

    from .. import audit, logistics, sourcing

    pos_updated: List[str] = []
    pos_delivered: List[str] = []
    for po_no, qty in matched_pos:
        po = sourcing.apply_ct_receipt(po_no, qty, tenant_id, grn_no)
        if po is None:
            continue
        if po_no not in pos_updated:
            pos_updated.append(po_no)
        if po.status == "delivered" and po_no not in pos_delivered:
            pos_delivered.append(po_no)

    source = "field_device" if via == "device" else "ui"
    metadata = {"grn_id": grn_id, "pos_updated": pos_updated, "pos_delivered": pos_delivered}
    if resumed:
        metadata["resumed"] = True
    audit.emit(
        action="grn_confirmed",
        entity_kind="grn",
        entity_id=grn_no,
        subject=grn_no,
        summary=f"GRN {grn_no} confirmed at store {store_id} · {ledger_count} line(s)",
        actor=actor,
        source=source,
        tenant_id=tenant_id,
        project_id=project_id,
        metadata=metadata,
    )

    for po_no, qty in matched_pos:
        po = sourcing.get_po(po_no, tenant_id=tenant_id)
        if po is None:
            continue
        line_metadata = {"grn_no": grn_no, "qty": qty}
        if resumed:
            line_metadata["resumed"] = True
        audit.emit(
            action="gr_posted",
            entity_kind="po",
            entity_id=po_no,
            subject=po_no,
            summary=f"Site GRN {grn_no} posted {qty} to {po_no}",
            actor=actor,
            source=source,
            tenant_id=tenant_id,
            project_id=po.project_id,
            bom_code=po.code,
            po_no=po_no,
            vendor=po.vendor,
            metadata=line_metadata,
        )

    for po_no in pos_delivered:
        try:
            logistics.add_event(
                po_no,
                AddShipmentEventRequest(
                    stage="delivered",
                    location=_store_name(tenant_id, store_id),
                    note=f"GRN {grn_no}",
                ),
                tenant_id,
            )
        except Exception:  # noqa: BLE001 — no shipment exists is a normal outcome
            pass

    from .._cache import invalidate_all
    invalidate_all()

    return pos_updated, pos_delivered


def _stamp_effects_applied(grn_id: str) -> None:
    """Mark the dict-store effects as landed. Absence of this stamp — not
    absence of an audit event — is what startup_sweep() reads: the audit log is
    a capped ring buffer and can legitimately forget a GRN."""

    conn = connect()
    try:
        conn.execute(
            "UPDATE grn SET effects_applied_at = ? WHERE grn_id = ?", (_iso(_now()), grn_id)
        )
        conn.commit()
    finally:
        conn.close()


def confirm_grn(
    grn_id: str,
    req: ConfirmGrnRequest,
    *,
    actor: str,
    via: str,
    tenant_id: str,
    store_id: Optional[str] = None,
) -> ConfirmGrnReply:
    conn = connect()
    try:
        header = conn.execute("SELECT * FROM grn WHERE grn_id = ?", (grn_id,)).fetchone()
        if header is None or header["tenant_id"] != tenant_id:
            raise HTTPException(status_code=404, detail="GRN not found")
        # Device confirm is store-scoped, not just tenant-scoped.
        if store_id is not None and header["store_id"] != store_id:
            raise HTTPException(status_code=404, detail="GRN not found")

        if header["status"] == "cancelled":
            raise HTTPException(status_code=409, detail="GRN already rejected")

        all_lines = conn.execute(
            "SELECT * FROM grn_lines WHERE grn_id = ? ORDER BY line_no", (grn_id,)
        ).fetchall()
        known_line_nos = {l["line_no"] for l in all_lines}
        for ln in req.lines:
            if ln.line_no not in known_line_nos:
                raise HTTPException(
                    status_code=422, detail=f"Line {ln.line_no} is not on this GRN"
                )

        if header["status"] == "confirmed":
            if _stored_keys(all_lines) != _submitted_keys(all_lines, req):
                raise HTTPException(status_code=409, detail="GRN already confirmed with different lines")
            return _reply_from_stored(conn, grn_id)

        for ln in req.lines:
            if bool(ln.po_no) == bool(ln.no_po):
                raise HTTPException(
                    status_code=422,
                    detail=f"Line {ln.line_no}: exactly one of po_no or no_po must be set",
                )

        submitted_by_no = {ln.line_no: ln for ln in req.lines}

        grn_no = _next_grn_no(conn, tenant_id)
        now_iso = _iso(_now())

        from .. import sourcing

        matched_pos: List[tuple] = []
        ledger_count = 0

        for line in all_lines:
            submitted = submitted_by_no.get(line["line_no"])
            po_no, match_status, qty_received, qty_damaged, qty_rejected = _confirm_line_values(
                line, submitted
            )
            if submitted is None:
                uom, batch_no = line["uom"], line["batch_no"]
            else:
                uom = submitted.uom or line["uom"]
                batch_no = submitted.batch_no or line["batch_no"]

            # remaining_qty() is read before apply_ct_receipt() runs, so this is
            # the headroom the PO had when the material arrived.
            matched_po = sourcing.get_po(po_no, tenant_id=tenant_id) if po_no else None
            over_receipt = bool(
                matched_po is not None and qty_received > matching.remaining_qty(matched_po)
            )

            conn.execute(
                """UPDATE grn_lines SET po_no = ?, match_status = ?, qty_received = ?,
                   qty_damaged = ?, qty_rejected = ?, uom = ?, batch_no = ?, over_receipt = ?
                   WHERE grn_line_id = ?""",
                (po_no, match_status, qty_received, qty_damaged, qty_rejected, uom, batch_no,
                 1 if over_receipt else 0, line["grn_line_id"]),
            )

            # Only qty_received enters stock/PO. Damaged/rejected qty goes nowhere
            # else. no_po/unmatched lines still enter the ledger (unmatched stock).
            if qty_received and qty_received > 0:
                vendor = None
                code = line["code"]
                if matched_po is not None:
                    vendor = matched_po.vendor
                    code = code or matched_po.code
                if not code:
                    code = _fallback_code(line["description_raw"])
                entry_uom = uom or line["uom_raw"] or "EA"

                conn.execute(
                    """INSERT INTO stock_ledger
                       (entry_id, tenant_id, store_id, project_id, code, description, uom,
                        movement, qty_signed, source_kind, batch_id, ref_kind, ref_id,
                        po_no, vendor, effective_at, entered_at, entered_by)
                       VALUES (?, ?, ?, ?, ?, ?, ?, 'receipt', ?, ?, NULL, 'grn', ?, ?, ?, ?, ?, ?)""",
                    (
                        new_id(), header["tenant_id"], header["store_id"], header["project_id"],
                        code, line["description_raw"], entry_uom, qty_received,
                        header["source_kind"], grn_id, po_no, vendor,
                        header["observed_at"], now_iso, actor,
                    ),
                )
                ledger_count += 1
                if po_no:
                    matched_pos.append((po_no, qty_received))

        # vendor_deliveries upsert per matched PO, inside this same transaction.
        # The delivered flip below predicts what apply_ct_receipt() (dict-store,
        # phase 2) will do a moment later — safe because confirm_grn runs
        # single-threaded end to end for this GRN.
        po_qty_totals: Dict[str, float] = {}
        for po_no, qty in matched_pos:
            po_qty_totals[po_no] = po_qty_totals.get(po_no, 0.0) + qty

        for po_no, added_qty in po_qty_totals.items():
            po = sourcing.get_po(po_no, tenant_id=tenant_id)
            if po is None:
                continue
            existing_vd = conn.execute(
                "SELECT * FROM vendor_deliveries WHERE po_no = ?", (po_no,)
            ).fetchone()
            prior_total = max(po.ct_gr_qty or 0, po.sap_gr_qty or 0)
            predicted_total = max(prior_total, (po.ct_gr_qty or 0) + added_qty)
            will_be_delivered = predicted_total >= po.quantity
            need_by_str = po.need_by.isoformat() if po.need_by else None

            if existing_vd is None:
                full_at = header["observed_at"] if will_be_delivered else None
                on_time = None
                if full_at and need_by_str:
                    on_time = 1 if full_at[:10] <= need_by_str else 0
                conn.execute(
                    """INSERT INTO vendor_deliveries
                       (po_no, tenant_id, vendor, need_by, first_receipt_at, full_receipt_at, on_time)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (po_no, tenant_id, po.vendor, need_by_str, header["observed_at"], full_at, on_time),
                )
            elif existing_vd["full_receipt_at"] is None and will_be_delivered:
                full_at = header["observed_at"]
                on_time = (1 if full_at[:10] <= need_by_str else 0) if need_by_str else None
                conn.execute(
                    "UPDATE vendor_deliveries SET full_receipt_at = ?, on_time = ? WHERE po_no = ?",
                    (full_at, on_time, po_no),
                )

        # A confirm racing the extraction worker wins (the worker's writes are
        # guarded on pre-confirm status), but would strand extraction_status at
        # 'pending'/'running' forever — close it out as 'skipped' here.
        _CONFIRM_SQL = """UPDATE grn SET grn_no = ?, status = 'confirmed', confirmed_at = ?,
               confirmed_by = ?, confirmed_via = ?,
               extraction_status = CASE WHEN extraction_status IN ('pending', 'running')
                                        THEN 'skipped' ELSE extraction_status END
               WHERE grn_id = ?"""
        try:
            conn.execute(_CONFIRM_SQL, (grn_no, now_iso, actor, via, grn_id))
        except sqlite3.IntegrityError:
            # UNIQUE(grn_no) — someone else took the number between the MAX
            # read and here. Recompute and retry once; cheap insurance for a
            # future multi-worker deployment.
            grn_no = _next_grn_no(conn, tenant_id)
            conn.execute(_CONFIRM_SQL, (grn_no, now_iso, actor, via, grn_id))
        conn.commit()
        project_id = header["project_id"]
        header_store_id = header["store_id"]
    finally:
        conn.close()

    # --- Dict-store effects (best-effort; SQLite already committed above) ---
    pos_updated, pos_delivered = _apply_confirm_effects(
        grn_id=grn_id,
        grn_no=grn_no,
        tenant_id=tenant_id,
        project_id=project_id,
        store_id=header_store_id,
        matched_pos=matched_pos,
        ledger_count=ledger_count,
        actor=actor,
        via=via,
    )
    _stamp_effects_applied(grn_id)

    return ConfirmGrnReply(
        grn_id=grn_id, grn_no=grn_no, status="confirmed",
        ledger_entries=ledger_count, pos_updated=pos_updated, pos_delivered=pos_delivered,
    )


def reject_grn(grn_id: str, reason: str, *, actor: str, tenant_id: str) -> GrnDetail:
    conn = connect()
    try:
        header = conn.execute("SELECT * FROM grn WHERE grn_id = ?", (grn_id,)).fetchone()
        if header is None or header["tenant_id"] != tenant_id:
            raise HTTPException(status_code=404, detail="GRN not found")
        if header["status"] in ("confirmed", "cancelled"):
            raise HTTPException(status_code=409, detail=f"GRN already {header['status']}")
        remarks = header["remarks"] or ""
        new_remarks = f"{remarks}\n{reason}" if remarks else reason
        conn.execute(
            """UPDATE grn SET status = 'cancelled', remarks = ?,
               extraction_status = CASE WHEN extraction_status IN ('pending', 'running')
                                        THEN 'skipped' ELSE extraction_status END
               WHERE grn_id = ?""",
            (new_remarks, grn_id),
        )
        conn.commit()
    finally:
        conn.close()
    return get_grn_detail(grn_id, tenant_id)


# --- Startup sweep -------------------------------------------------------------


def startup_sweep() -> None:
    """Re-apply dict-store effects for confirmed GRNs that crashed between the
    SQLite commit and the dict-store phase — those whose effects_applied_at was
    never stamped. Idempotent."""

    conn = connect()
    try:
        headers = conn.execute(
            "SELECT * FROM grn WHERE status = 'confirmed' AND grn_no IS NOT NULL "
            "AND effects_applied_at IS NULL"
        ).fetchall()
        lines_by_grn = {
            h["grn_id"]: conn.execute(
                "SELECT * FROM grn_lines WHERE grn_id = ?", (h["grn_id"],)
            ).fetchall()
            for h in headers
        }
    finally:
        conn.close()

    if not headers:
        return

    for header in headers:
        lines = lines_by_grn.get(header["grn_id"], [])
        matched_pos = [
            (l["po_no"], l["qty_received"])
            for l in lines
            if l["po_no"] and l["qty_received"] and l["qty_received"] > 0
        ]
        ledger_count = sum(1 for l in lines if l["qty_received"] and l["qty_received"] > 0)

        _apply_confirm_effects(
            grn_id=header["grn_id"],
            grn_no=header["grn_no"],
            tenant_id=header["tenant_id"],
            project_id=header["project_id"],
            store_id=header["store_id"],
            matched_pos=matched_pos,
            ledger_count=ledger_count,
            actor=header["confirmed_by"] or "system",
            via=header["confirmed_via"] or "office",
            resumed=True,
        )
        _stamp_effects_applied(header["grn_id"])


# --- Reads ---------------------------------------------------------------------


def _line_out(row) -> GrnLineOut:
    candidates = None
    if row["match_candidates"]:
        candidates = [MatchCandidate.model_validate(c) for c in json.loads(row["match_candidates"])]
    return GrnLineOut(
        grn_line_id=row["grn_line_id"], line_no=row["line_no"],
        description_raw=row["description_raw"], code=row["code"],
        uom_raw=row["uom_raw"], uom=row["uom"], qty_challan=row["qty_challan"],
        qty_received=row["qty_received"], qty_damaged=row["qty_damaged"],
        qty_rejected=row["qty_rejected"], batch_no=row["batch_no"], po_no=row["po_no"],
        match_status=row["match_status"], match_confidence=row["match_confidence"],
        match_candidates=candidates, over_receipt=bool(row["over_receipt"]),
    )


def get_grn_detail(grn_id: str, tenant_id: str, store_id: Optional[str] = None) -> GrnDetail:
    conn = connect()
    try:
        header = conn.execute("SELECT * FROM grn WHERE grn_id = ?", (grn_id,)).fetchone()
        if header is None or header["tenant_id"] != tenant_id:
            raise HTTPException(status_code=404, detail="GRN not found")
        if store_id is not None and header["store_id"] != store_id:
            raise HTTPException(status_code=404, detail="GRN not found")
        lines = conn.execute(
            "SELECT * FROM grn_lines WHERE grn_id = ? ORDER BY line_no", (grn_id,)
        ).fetchall()
        return GrnDetail(
            grn_id=header["grn_id"], grn_no=header["grn_no"], tenant_id=header["tenant_id"],
            store_id=header["store_id"], project_id=header["project_id"], device_id=header["device_id"],
            status=header["status"], source_kind=header["source_kind"], challan_no=header["challan_no"],
            challan_date=header["challan_date"], vendor_name_raw=header["vendor_name_raw"],
            vendor_name=header["vendor_name"], vehicle_no=header["vehicle_no"], remarks=header["remarks"],
            photo_sha256=header["photo_sha256"], extraction_status=header["extraction_status"],
            extraction_model=header["extraction_model"], observed_at=header["observed_at"],
            received_at=header["received_at"], confirmed_at=header["confirmed_at"],
            confirmed_by=header["confirmed_by"], confirmed_via=header["confirmed_via"],
            created_at=header["created_at"], lines=[_line_out(l) for l in lines],
        )
    finally:
        conn.close()


def list_grns(
    tenant_id: str,
    status: Optional[str] = None,
    store_id: Optional[str] = None,
    triage: bool = False,
) -> List[GrnSummary]:
    conn = connect()
    try:
        # One query, not one per row: the line count comes off a LEFT JOIN so a
        # 500-GRN triage queue is still a single round trip.
        sql = (
            "SELECT g.*, COUNT(l.grn_line_id) AS line_count FROM grn g "
            "LEFT JOIN grn_lines l ON l.grn_id = g.grn_id WHERE g.tenant_id = ?"
        )
        params: List = [tenant_id]
        if store_id:
            sql += " AND g.store_id = ?"
            params.append(store_id)
        if status:
            sql += " AND g.status = ?"
            params.append(status)
        elif triage:
            sql += " AND g.status IN ('triage', 'suggested', 'matched')"
        sql += " GROUP BY g.grn_id ORDER BY g.received_at DESC"

        rows = conn.execute(sql, params).fetchall()
        return [
            GrnSummary(
                grn_id=r["grn_id"], grn_no=r["grn_no"], status=r["status"],
                source_kind=r["source_kind"], vendor_name=r["vendor_name"] or r["vendor_name_raw"],
                challan_no=r["challan_no"], store_id=r["store_id"], line_count=r["line_count"],
                observed_at=r["observed_at"], confirmed_at=r["confirmed_at"],
            )
            for r in rows
        ]
    finally:
        conn.close()
