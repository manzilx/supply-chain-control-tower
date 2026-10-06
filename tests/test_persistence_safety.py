"""Restore must survive a damaged snapshot without losing the other stores."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import approvals, persistence, sourcing, vendor_store
from tests.conftest import TENANT


def _supplier(name: str) -> dict:
    return {
        "name": name,
        "category": "Restore widgets",
        "country": "Sweden",
        "lead_time_days": 30,
        "on_time_delivery_pct": 95.0,
        "quality_ppm": 200,
        "annual_spend_usd": 100_000.0,
    }


@pytest.fixture()
def snapshot_dir(
    client: TestClient, head_headers: dict[str, str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Path:
    """A private copy of a real snapshot (one vendor + its approval)."""

    res = client.post("/api/vendors", json=_supplier("Restore Vendor"), headers=head_headers)
    assert res.status_code == 200
    assert persistence.flush_critical()["ok"]
    for name in ("vendors.json", "approvals.json", "sourcing.json", "audit.json", ".version"):
        shutil.copy2(persistence.STATE_DIR / name, tmp_path / name)
    monkeypatch.setattr(persistence, "STATE_DIR", tmp_path)
    return tmp_path


def _wipe_memory() -> None:
    vendor_store._runtime.clear()
    approvals._approvals.clear()


def test_truncated_file_does_not_wipe_other_stores(snapshot_dir: Path) -> None:
    good_sourcing = (snapshot_dir / "sourcing.json").read_text()
    (snapshot_dir / "sourcing.json").write_text(good_sourcing[: len(good_sourcing) // 2])
    prs_before = dict(sourcing._prs)
    _wipe_memory()

    result = persistence.restore_all()

    assert "sourcing.json" in result["errors"]
    assert [n for n in result["quarantined"] if n.startswith("sourcing.json.corrupt-")]
    # The other stores came back even though sourcing failed first.
    assert any(s.name == "Restore Vendor" for s in vendor_store._runtime.get(TENANT, []))
    assert approvals._approvals.get(TENANT)
    # Sourcing kept its in-memory state rather than being half-cleared.
    assert dict(sourcing._prs) == prs_before

    # The next flush must not destroy the damaged original's copy.
    assert persistence.flush_critical()["ok"]
    copies = list(snapshot_dir.glob("sourcing.json.corrupt-*"))
    assert copies and copies[0].read_text() == good_sourcing[: len(good_sourcing) // 2]


def test_one_bad_record_is_skipped_not_the_whole_file(snapshot_dir: Path) -> None:
    path = snapshot_dir / "approvals.json"
    data = json.loads(path.read_text())
    bucket = data["approvals"][TENANT]
    good_id = next(iter(bucket))
    bucket["APR-BAD"] = {**bucket[good_id], "approval_id": "APR-BAD", "status": "on_hold"}
    path.write_text(json.dumps(data))
    _wipe_memory()

    result = persistence.restore_all()

    assert result["skipped_records"] == {"approvals.json": 1}
    assert good_id in approvals._approvals[TENANT]
    assert "APR-BAD" not in approvals._approvals[TENANT]
    assert list(snapshot_dir.glob("approvals.json.corrupt-*")), "file with the bad row is kept aside"


def test_newer_snapshot_version_refuses_to_boot(snapshot_dir: Path) -> None:
    (snapshot_dir / ".version").write_text(str(persistence.SNAPSHOT_VERSION + 1))
    with pytest.raises(RuntimeError, match="newer build|this build reads"):
        persistence.restore_all()


def test_writes_are_atomic_and_leave_no_temp_files(snapshot_dir: Path) -> None:
    assert persistence.snapshot_all()["ok"]
    assert not list(snapshot_dir.glob(".*.tmp"))
    json.loads((snapshot_dir / "vendors.json").read_text())


def test_failed_projects_restore_does_not_seed_demo_projects(
    snapshot_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app import planning

    (snapshot_dir / "projects.json").write_text("{not json")
    monkeypatch.setattr(planning, "_restore_failed", False)
    monkeypatch.setattr(planning, "_projects", {})

    result = persistence.restore_all()

    assert "projects.json" in result["errors"]
    assert planning._restore_failed is True
    planning._seed()
    assert planning._projects == {}, "demo projects must not fill a failed restore"
