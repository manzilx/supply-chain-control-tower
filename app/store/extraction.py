"""Async vision-LLM challan extraction worker.

Runs after a GRN lands via field sync. Grok vision -> deterministic
normalize -> matcher (no LLM, see matching.py) -> banded header status.
LLM-off is a first-class working path, not an error: extraction_status
becomes 'skipped' and the matcher still runs synchronously against any
manually-keyed lines.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
from datetime import datetime
from typing import Optional

from . import matching
from .db import connect
from .. import llm


SYSTEM_PROMPT = (
    "You are extracting structured data from a photo of a delivery challan / "
    "goods-receipt note at a construction site store. Read the photo carefully "
    "and return a JSON object with EXACTLY these keys:\n"
    '{"challan_no": string or null, "challan_date": "YYYY-MM-DD" string or null, '
    '"vendor_name": string or null, "vehicle_no": string or null, '
    '"lines": [{"description": string, "code": string or null, "qty": number or null, '
    '"uom": string or null, "batch_no": string or null}]}\n'
    "Do not invent values you cannot read — use null where illegible or absent."
)
USER_PROMPT = "Extract the challan header fields and line items from this photo."


_DATE_SLASH_RE = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})$")
_DATE_DASH_RE = re.compile(r"^(\d{1,2})-(\d{1,2})-(\d{4})$")

# Extraction may only touch a GRN that is still pre-confirm. The vision call
# takes seconds, and a storekeeper can confirm (or the office reject) inside
# that window — every extraction-side write is therefore conditional on the
# header still being in one of these states, so the confirm always wins.
ACTIVE_STATUSES = ("captured", "extracting")


def _normalize_date(raw: Optional[str]) -> Optional[str]:
    """dd/mm/yyyy or dd-mm-yyyy -> ISO date; already-ISO values pass through;
    anything else (unparseable) -> None."""

    if not raw:
        return None
    raw = raw.strip()
    for rx in (_DATE_SLASH_RE, _DATE_DASH_RE):
        m = rx.match(raw)
        if m:
            d, mo, y = (int(g) for g in m.groups())
            try:
                return datetime(y, mo, d).date().isoformat()
            except ValueError:
                return None
    try:
        return datetime.fromisoformat(raw).date().isoformat()
    except ValueError:
        return None


def _normalize_qty(raw) -> Optional[float]:
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _extraction_model() -> str:
    return os.getenv("XAI_VISION_MODEL", "").strip() or os.getenv("XAI_MODEL", "grok-4-1-fast-reasoning")


async def run_extraction(grn_id: str) -> None:
    conn = connect()
    try:
        header = conn.execute("SELECT * FROM grn WHERE grn_id = ?", (grn_id,)).fetchone()
        if header is None or header["status"] not in ACTIVE_STATUSES:
            return

        if not llm.is_enabled():
            cur = conn.execute(
                "UPDATE grn SET extraction_status = 'skipped' "
                "WHERE grn_id = ? AND status IN ('captured', 'extracting')",
                (grn_id,),
            )
            if cur.rowcount == 0:
                conn.commit()
                return
            matching.apply_bands(conn, grn_id)
            conn.commit()
            return

        cur = conn.execute(
            "UPDATE grn SET extraction_status = 'running' "
            "WHERE grn_id = ? AND status IN ('captured', 'extracting')",
            (grn_id,),
        )
        conn.commit()
        if cur.rowcount == 0:
            return
        photo_path = header["photo_path"]
    finally:
        conn.close()

    result = await asyncio.to_thread(llm.grok_vision_json, SYSTEM_PROMPT, USER_PROMPT, photo_path)

    conn = connect()
    try:
        header = conn.execute("SELECT * FROM grn WHERE grn_id = ?", (grn_id,)).fetchone()
        if header is None or header["status"] not in ACTIVE_STATUSES:
            return  # confirmed/rejected while the vision call was in flight

        if result is None:
            conn.execute(
                "UPDATE grn SET extraction_status = 'failed', status = 'triage' "
                "WHERE grn_id = ? AND status IN ('captured', 'extracting')",
                (grn_id,),
            )
            conn.commit()
            return

        # This guarded UPDATE is both the re-check and the write lock for the
        # rest of the transaction: rowcount 0 means the GRN moved on between
        # the SELECT above and here, so extraction must not touch it again.
        cur = conn.execute(
            "UPDATE grn SET extraction_json = ?, extraction_model = ?, extraction_status = 'done' "
            "WHERE grn_id = ? AND status IN ('captured', 'extracting')",
            (json.dumps(result), _extraction_model(), grn_id),
        )
        if cur.rowcount == 0:
            conn.commit()
            return

        # Header fields fill only where currently NULL — manual keying wins.
        updates: dict = {}
        if header["challan_no"] is None and result.get("challan_no"):
            updates["challan_no"] = str(result["challan_no"])
        if header["challan_date"] is None:
            normalized_date = _normalize_date(result.get("challan_date"))
            if normalized_date:
                updates["challan_date"] = normalized_date
        if header["vendor_name_raw"] is None and result.get("vendor_name"):
            updates["vendor_name_raw"] = str(result["vendor_name"])
        if header["vehicle_no"] is None and result.get("vehicle_no"):
            updates["vehicle_no"] = str(result["vehicle_no"])
        if updates:
            set_clause = ", ".join(f"{k} = ?" for k in updates)
            conn.execute(
                f"UPDATE grn SET {set_clause} "
                "WHERE grn_id = ? AND status IN ('captured', 'extracting')",
                (*updates.values(), grn_id),
            )

        # Lines insert ONLY if the GRN currently has none — manual lines always win.
        existing = conn.execute(
            "SELECT COUNT(*) AS n FROM grn_lines WHERE grn_id = ?", (grn_id,)
        ).fetchone()["n"]
        if existing == 0:
            from .db import new_id
            for i, raw_line in enumerate(result.get("lines") or [], start=1):
                qty = _normalize_qty(raw_line.get("qty"))
                uom_raw = raw_line.get("uom")
                description = str(raw_line.get("description") or "").strip() or "(unreadable)"
                conn.execute(
                    """INSERT INTO grn_lines
                       (grn_line_id, grn_id, line_no, description_raw, code, uom_raw, uom,
                        qty_challan, qty_received, qty_damaged, qty_rejected, batch_no,
                        po_no, match_status, match_confidence, match_candidates, matched_by,
                        over_receipt)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, ?, NULL, 'unmatched', NULL, NULL, NULL, 0)""",
                    (
                        new_id(), grn_id, i, description, raw_line.get("code"), uom_raw,
                        matching.canonical_uom(uom_raw), qty, qty if qty is not None else 0.0,
                        raw_line.get("batch_no"),
                    ),
                )

        # One transaction end to end — committing before apply_bands would drop
        # the write lock the guard above acquired.
        matching.apply_bands(conn, grn_id)
        conn.commit()
    finally:
        conn.close()


def resume_pending() -> None:
    """Reschedule pending|running GRNs after a restart. Called from the
    startup hook, where a running event loop already exists."""

    conn = connect()
    try:
        rows = conn.execute(
            "SELECT grn_id FROM grn WHERE extraction_status IN ('pending', 'running') "
            "AND status IN ('captured', 'extracting')"
        ).fetchall()
    finally:
        conn.close()
    if not rows:
        return

    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        return

    for row in rows:
        if loop.is_running():
            loop.create_task(run_extraction(row["grn_id"]))
        else:
            asyncio.ensure_future(run_extraction(row["grn_id"]))
