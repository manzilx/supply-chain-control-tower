"""Pure-function tests for app.store.matching: scoring, banding, and the
qty/UOM/vendor-resolution rules that decide auto vs suggested vs unmatched.

No FastAPI app is needed here, but canonical_uom() still reads the uom_alias
table, so we init the (isolated, tempdir) store schema once for this module.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import pytest

from app.schemas import SourcingPO
from app.store import db, matching


@pytest.fixture(autouse=True, scope="module")
def _store_schema() -> None:
    db.init_db()


def _po(
    po_no: str,
    *,
    code: str,
    vendor: str,
    quantity: float,
    uom: str = "EA",
    description: Optional[str] = None,
    status: str = "released",
    ct_gr_qty: float = 0.0,
    sap_gr_qty: float = 0.0,
) -> SourcingPO:
    return SourcingPO(
        po_no=po_no, pr_no=f"PR-{po_no}", rfq_no=f"RFQ-{po_no}", award_id=f"AWD-{po_no}",
        project_id="PRJ-TEST", vendor=vendor, code=code,
        description=description or f"{code} material",
        quantity=quantity, uom=uom, unit_price_usd=10.0, value_usd=10.0 * quantity,
        incoterm="CIP", lead_time_days=30, created_at=datetime.now(timezone.utc),
        status=status, ct_gr_qty=ct_gr_qty, sap_gr_qty=sap_gr_qty,
    )


def test_auto_band_unique_winner_above_threshold() -> None:
    pool = [_po("SPO-001", code="WIDGET-A", vendor="Acme Vendor", quantity=100, description="Widget A")]
    line = {
        "description_raw": "Widget A delivered", "code": "WIDGET-A",
        "uom_raw": "EA", "qty_received": 50, "qty_challan": 50,
    }
    [result] = matching.match_lines("t1", "PRJ-TEST", "Acme Vendor", [line], pool=pool)
    assert result["match_status"] == "auto"
    assert result["po_no"] == "SPO-001"
    assert result["match_confidence"] >= matching.AUTO_THRESHOLD


def test_near_tie_demotes_to_suggested() -> None:
    # Two POs that score identically against the line: best - second == 0,
    # so there is no unique winner even though both clear SUGGESTED_THRESHOLD.
    pool = [
        _po("SPO-101", code="PIPE-100", vendor="Vendor One", quantity=200, description="Pipe 100mm"),
        _po("SPO-102", code="PIPE-100", vendor="Vendor One", quantity=200, description="Pipe 100mm"),
    ]
    line = {
        "description_raw": "Pipe 100mm", "code": "PIPE-100",
        "uom_raw": "EA", "qty_received": 50, "qty_challan": 50,
    }
    [result] = matching.match_lines("t1", "PRJ-TEST", "Vendor One", [line], pool=pool)
    assert result["match_confidence"] >= matching.SUGGESTED_THRESHOLD
    assert result["match_status"] == "suggested"
    assert result["po_no"] is None


def test_uom_mismatch_caps_at_suggested_even_with_perfect_score() -> None:
    pool = [_po("SPO-201", code="CEM-53", vendor="UltraTech", quantity=100, uom="BAG", description="OPC 53 cement")]
    line = {
        "description_raw": "OPC 53 cement", "code": "CEM-53",
        "uom_raw": "kg", "qty_received": 50,
    }
    [result] = matching.match_lines("t1", "PRJ-TEST", "UltraTech", [line], pool=pool)
    assert result["match_status"] == "suggested"
    assert result["po_no"] is None


def test_qty_beyond_105pct_headroom_excluded_from_auto() -> None:
    pool = [_po("SPO-301", code="REBAR-8", vendor="Tata Steel", quantity=100, uom="EA", description="TMT rebar 8mm")]
    remaining = matching.remaining_qty(pool[0])
    line = {
        "description_raw": "TMT rebar 8mm", "code": "REBAR-8",
        "uom_raw": "EA", "qty_received": remaining + 5,
    }
    [result] = matching.match_lines("t1", "PRJ-TEST", "Tata Steel", [line], pool=pool)
    assert result["match_status"] != "auto"
    assert result["po_no"] is None


@pytest.mark.skip(
    reason=(
        "source_kind isn't a match_lines() parameter — free_issue lines are "
        "short-circuited to match_status='no_po' in grn.create_from_sync() "
        "before match_lines()/apply_bands() ever runs, so there is no matcher "
        "behaviour to exercise here. Covered end-to-end by "
        "tests/test_store_grn.py::test_free_issue_credits_free_issue_qty_not_contractor."
    )
)
def test_free_issue_is_handled_in_grn_not_in_matcher() -> None:
    pass


def test_vendor_resolution_ratio_boundary() -> None:
    """A clearly-similar vendor name (ratio well above the 0.85 resolution
    threshold, but not a substring of the PO vendor) resolves and earns the
    +0.35 vendor bonus; a clearly-different name does not."""

    pool = [_po(
        "SPO-401", code="CR-01", vendor="Kirloskar Brothers", quantity=10, uom="EA",
        description="CW pump vertical turbine",
    )]
    line = {
        "description_raw": "CW pump vertical turbine", "code": "CR-01",
        "uom_raw": "EA", "qty_received": 2,
    }
    [similar] = matching.match_lines("t1", "PRJ-TEST", "Kirloskar Brothors", [line], pool=pool)
    [different] = matching.match_lines("t1", "PRJ-TEST", "Totally Different Co", [line], pool=pool)

    assert similar["match_status"] == "auto"
    assert similar["po_no"] == "SPO-401"
    assert different["match_status"] != "auto"
    assert different["match_confidence"] < similar["match_confidence"]


def test_remaining_qty_uses_max_of_ct_and_sap_gr_qty() -> None:
    ct_ahead = _po("SPO-501", code="X", vendor="V", quantity=100, ct_gr_qty=80.0, sap_gr_qty=30.0)
    sap_ahead = _po("SPO-502", code="X", vendor="V", quantity=100, ct_gr_qty=20.0, sap_gr_qty=90.0)
    assert matching.remaining_qty(ct_ahead) == pytest.approx(25.0)
    assert matching.remaining_qty(sap_ahead) == pytest.approx(15.0)
