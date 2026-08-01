"""Stock ledger reads: balances, per-code history, vendor OTD.

The ledger itself is append-only and only ever written by grn.confirm_grn();
this module is read-only.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from .db import connect
from ..schemas import LedgerEntryOut, StockBalance, VendorOtdRow


def stock_balances(tenant_id: str, store_id: Optional[str] = None) -> List[StockBalance]:
    conn = connect()
    try:
        sql = "SELECT * FROM stock_ledger WHERE tenant_id = ?"
        params: List = [tenant_id]
        if store_id:
            sql += " AND store_id = ?"
            params.append(store_id)
        sql += " ORDER BY effective_at ASC"
        rows = conn.execute(sql, params).fetchall()
    finally:
        conn.close()

    groups: Dict[tuple, dict] = {}
    for r in rows:
        key = (r["store_id"], r["code"], r["uom"])
        g = groups.setdefault(key, {
            "contractor_qty": 0.0, "free_issue_qty": 0.0,
            "description": r["description"], "last_movement_at": r["effective_at"],
        })
        if r["source_kind"] == "free_issue":
            g["free_issue_qty"] += r["qty_signed"]
        else:
            g["contractor_qty"] += r["qty_signed"]
        g["description"] = r["description"]  # rows are ascending -> last write wins
        if r["effective_at"] > g["last_movement_at"]:
            g["last_movement_at"] = r["effective_at"]

    return [
        StockBalance(
            code=code, description=g["description"], uom=uom, store_id=sid,
            contractor_qty=round(g["contractor_qty"], 3),
            free_issue_qty=round(g["free_issue_qty"], 3),
            total_qty=round(g["contractor_qty"] + g["free_issue_qty"], 3),
            last_movement_at=g["last_movement_at"],
        )
        for (sid, code, uom), g in groups.items()
    ]


def code_ledger(tenant_id: str, code: str, store_id: Optional[str] = None) -> List[LedgerEntryOut]:
    conn = connect()
    try:
        sql = "SELECT * FROM stock_ledger WHERE tenant_id = ? AND code = ?"
        params: List = [tenant_id, code]
        if store_id:
            sql += " AND store_id = ?"
            params.append(store_id)
        sql += " ORDER BY effective_at DESC"
        rows = conn.execute(sql, params).fetchall()
        return [
            LedgerEntryOut(
                entry_id=r["entry_id"], store_id=r["store_id"], code=r["code"],
                description=r["description"], uom=r["uom"], movement=r["movement"],
                qty_signed=r["qty_signed"], source_kind=r["source_kind"], ref_kind=r["ref_kind"],
                ref_id=r["ref_id"], po_no=r["po_no"], vendor=r["vendor"],
                effective_at=r["effective_at"], entered_at=r["entered_at"], entered_by=r["entered_by"],
            )
            for r in rows
        ]
    finally:
        conn.close()


def vendor_otd(tenant_id: str) -> List[VendorOtdRow]:
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT * FROM vendor_deliveries WHERE tenant_id = ? ORDER BY po_no", (tenant_id,)
        ).fetchall()
        return [
            VendorOtdRow(
                vendor=r["vendor"], po_no=r["po_no"], need_by=r["need_by"],
                first_receipt_at=r["first_receipt_at"], full_receipt_at=r["full_receipt_at"],
                on_time=bool(r["on_time"]) if r["on_time"] is not None else None,
            )
            for r in rows
        ]
    finally:
        conn.close()
