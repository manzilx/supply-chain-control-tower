"""Deterministic fuzzy matcher: GRN lines -> open sourcing POs.

No LLM here — extraction (app/store/extraction.py) is the only module that
talks to the vision model; this module only scores candidates and bands the
result. Both extraction.py (LLM-off path) and grn.py (manual-line path) call
apply_bands() so line banding is identical regardless of how a GRN got its
lines.
"""

from __future__ import annotations

import json
import re
import sqlite3
from difflib import SequenceMatcher
from functools import lru_cache
from typing import Dict, List, Optional, Set

from .db import connect
from ..schemas import MatchCandidate, SourcingPO


_TOKEN_RE = re.compile(r"[a-z0-9]+")

AUTO_THRESHOLD = 0.85
SUGGESTED_THRESHOLD = 0.6
UNIQUE_WINNER_MARGIN = 0.1
OVER_RECEIPT_HEADROOM = 1.05


@lru_cache(maxsize=1)
def _alias_map() -> Dict[str, str]:
    """uom_alias is static seed data (db.init_db seeds it once), so it is read
    exactly once per process instead of once per canonical_uom() call — the
    matcher calls this several times per line per candidate PO."""

    conn = connect()
    try:
        rows = conn.execute("SELECT alias, canonical FROM uom_alias").fetchall()
    finally:
        conn.close()
    return {r["alias"]: r["canonical"] for r in rows}


def canonical_uom(raw: Optional[str]) -> Optional[str]:
    """Canonicalise a raw uom string via the uom_alias table (lowercase,
    stripped). Unknown values fall back to the uppercased raw string."""

    if not raw:
        return None
    key = raw.strip().lower()
    if not key:
        return None
    canonical = _alias_map().get(key)
    if canonical is not None:
        return canonical
    return raw.strip().upper() or None


def remaining_qty(po: SourcingPO) -> float:
    """5% over-receipt headroom above quantity, less whichever GR channel
    (site or SAP) has received more so far."""

    received = max(po.ct_gr_qty or 0, po.sap_gr_qty or 0)
    return po.quantity * OVER_RECEIPT_HEADROOM - received


def _tokens(text: str) -> Set[str]:
    return {t for t in _TOKEN_RE.findall(text.lower()) if len(t) > 2}


def _jaccard(a: Set[str], b: Set[str]) -> float:
    if not a or not b:
        return 0.0
    union = len(a | b)
    return len(a & b) / union if union else 0.0


def _resolve_vendor(vendor_name_raw: Optional[str], pool: List[SourcingPO]) -> Optional[str]:
    if not vendor_name_raw:
        return None
    raw = vendor_name_raw.strip().lower()
    if not raw:
        return None
    best_vendor: Optional[str] = None
    best_ratio = 0.0
    for po in pool:
        v = po.vendor.strip().lower()
        if not v:
            continue
        if raw in v or v in raw:
            return po.vendor
        ratio = SequenceMatcher(None, raw, v).ratio()
        if ratio > best_ratio:
            best_ratio = ratio
            best_vendor = po.vendor
    return best_vendor if best_ratio >= 0.85 else None


def _line_qty(line: dict) -> float:
    qty = line.get("qty_received") or 0
    if not qty:
        qty = line.get("qty_challan") or 0
    return qty or 0.0


def _score_line(line: dict, po: SourcingPO, resolved_vendor: Optional[str]) -> float:
    score = 0.0

    if resolved_vendor and po.vendor == resolved_vendor:
        score += 0.35

    code = (line.get("code") or "").strip().lower()
    po_code = (po.code or "").strip().lower()
    desc_raw = (line.get("description_raw") or "").lower()
    if po_code and (code == po_code or po_code in desc_raw):
        score += 0.25

    score += 0.20 * _jaccard(_tokens(line.get("description_raw") or ""), _tokens(po.description or ""))

    qty = _line_qty(line)
    if qty and qty <= remaining_qty(po):
        score += 0.15

    line_uom = canonical_uom(line.get("uom_raw"))
    if line_uom and line_uom == canonical_uom(po.uom):
        score += 0.05

    return round(score, 4)


def match_lines(
    tenant_id: str,
    project_id: str,
    vendor_name_raw: Optional[str],
    lines: List[dict],
    pool: Optional[List[SourcingPO]] = None,
) -> List[dict]:
    """Score each line against the candidate PO pool and band it.

    `pool` overrides the live pool for unit tests. Returns one dict per line
    (same order as `lines`): match_status, po_no (set only for 'auto'),
    match_confidence, match_candidates (top-3 MatchCandidate list).
    """

    if pool is None:
        from .. import sourcing
        pool = [
            po for po in sourcing.list_pos(tenant_id=tenant_id)
            if po.project_id == project_id
            and po.status in ("released", "in_transit")
            and remaining_qty(po) > 0
        ]

    resolved_vendor = _resolve_vendor(vendor_name_raw, pool)

    results: List[dict] = []
    for line in lines:
        scored = sorted(
            ((_score_line(line, po, resolved_vendor), po) for po in pool),
            key=lambda x: x[0],
            reverse=True,
        )

        candidates = [
            MatchCandidate(
                po_no=po.po_no, vendor=po.vendor, code=po.code, description=po.description,
                score=s, remaining_qty=round(remaining_qty(po), 3), uom=po.uom,
            )
            for s, po in scored[:3]
        ]

        if not scored:
            results.append({
                "match_status": "unmatched", "po_no": None,
                "match_confidence": None, "match_candidates": candidates,
            })
            continue

        best_score, best_po = scored[0]
        if len(scored) == 1:
            unique_winner = best_score >= SUGGESTED_THRESHOLD
        else:
            unique_winner = (best_score - scored[1][0]) >= UNIQUE_WINNER_MARGIN

        qty_ok = bool(_line_qty(line)) and _line_qty(line) <= remaining_qty(best_po)
        line_uom = canonical_uom(line.get("uom_raw"))
        uom_equal = bool(line_uom) and line_uom == canonical_uom(best_po.uom)

        if best_score >= AUTO_THRESHOLD and unique_winner and uom_equal and qty_ok:
            results.append({
                "match_status": "auto", "po_no": best_po.po_no,
                "match_confidence": best_score, "match_candidates": candidates,
            })
        elif best_score >= SUGGESTED_THRESHOLD:
            results.append({
                "match_status": "suggested", "po_no": None,
                "match_confidence": best_score, "match_candidates": candidates,
            })
        else:
            results.append({
                "match_status": "unmatched", "po_no": None,
                "match_confidence": best_score, "match_candidates": candidates,
            })

    return results


def apply_bands(conn: sqlite3.Connection, grn_id: str) -> str:
    """Run match_lines() against a GRN's current lines, persist the results,
    and set the header's banded status. Returns the new header status.

    Shared by extraction.py's LLM-disabled path and grn.py's manual-line
    path so both bands identically. Caller commits.
    """

    header = conn.execute("SELECT * FROM grn WHERE grn_id = ?", (grn_id,)).fetchone()
    if header is None:
        return "triage"

    lines = conn.execute(
        "SELECT * FROM grn_lines WHERE grn_id = ? ORDER BY line_no", (grn_id,)
    ).fetchall()
    if not lines:
        conn.execute("UPDATE grn SET status = 'triage' WHERE grn_id = ?", (grn_id,))
        return "triage"

    results = match_lines(
        header["tenant_id"], header["project_id"], header["vendor_name_raw"],
        [dict(l) for l in lines],
    )

    for line, result in zip(lines, results):
        candidates_json = json.dumps(
            [c.model_dump(mode="json") for c in result["match_candidates"]]
        )
        conn.execute(
            """UPDATE grn_lines SET po_no = ?, match_status = ?, match_confidence = ?,
               match_candidates = ? WHERE grn_line_id = ?""",
            (
                result["po_no"], result["match_status"], result["match_confidence"],
                candidates_json, line["grn_line_id"],
            ),
        )

    statuses = {r["match_status"] for r in results}
    if statuses == {"auto"}:
        status = "matched"
    elif statuses & {"auto", "suggested"}:
        status = "suggested"
    else:
        status = "triage"
    conn.execute("UPDATE grn SET status = ? WHERE grn_id = ?", (status, grn_id))
    return status
