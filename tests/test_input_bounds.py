"""Forms, uploads and device sync reject nonsense numbers and unsafe IDs."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.ingest import _validate_rows
from app.store.db import MEDIA_DIR
from tests.test_store_grn import enrol, make_store, sync_grn


def _project_id(client: TestClient, headers: dict[str, str]) -> str:
    projects = client.get("/api/projects", headers=headers).json()
    return next(p["project_id"] for p in projects if p["project_id"].startswith("PRJ-AF"))


def _post_json(client: TestClient, url: str, headers: dict[str, str], body: dict):
    # json.dumps writes NaN/Infinity literals, which is what a buggy client sends.
    return client.post(url, headers={**headers, "content-type": "application/json"}, content=json.dumps(body))


@pytest.mark.parametrize(
    "overrides",
    [{"quantity": -5}, {"quantity": 0}, {"quantity": float("nan")}, {"budget_value_usd": -100}],
)
def test_pr_rejects_bad_numbers(client: TestClient, head_headers: dict[str, str], overrides: dict) -> None:
    body = {"project_id": _project_id(client, head_headers), "code": "X-1", "description": "x", **overrides}
    assert _post_json(client, "/api/prs", head_headers, body).status_code == 422


@pytest.mark.parametrize(
    "overrides",
    [
        {"unit_price_usd": -100},
        {"unit_price_usd": float("inf")},
        {"quantity": -10},
        {"lead_time_days": -1},
        {"validity_days": -3},
    ],
)
def test_quote_rejects_bad_numbers(client: TestClient, head_headers: dict[str, str], overrides: dict) -> None:
    pr = client.post(
        "/api/prs", headers=head_headers,
        json={"project_id": _project_id(client, head_headers), "code": "QB-1", "description": "Bounds", "quantity": 10},
    )
    rfq = client.post("/api/rfqs", headers=head_headers, json={"pr_no": pr.json()["pr_no"], "vendors": ["V1"]})
    body = {"vendor": "V1", "unit_price_usd": 100, "lead_time_days": 30, **overrides}
    res = _post_json(client, f"/api/rfqs/{rfq.json()['rfq_no']}/quotes", head_headers, body)
    assert res.status_code == 422


def test_rfq_needs_vendors_and_sane_due_date(client: TestClient, head_headers: dict[str, str]) -> None:
    pr = client.post(
        "/api/prs", headers=head_headers,
        json={"project_id": _project_id(client, head_headers), "code": "RB-1", "description": "Bounds", "quantity": 1},
    )
    pr_no = pr.json()["pr_no"]
    assert client.post("/api/rfqs", headers=head_headers, json={"pr_no": pr_no, "vendors": []}).status_code == 422
    assert client.post(
        "/api/rfqs", headers=head_headers, json={"pr_no": pr_no, "vendors": ["V"], "due_in_days": -2}
    ).status_code == 422


@pytest.mark.parametrize(
    "overrides",
    [{"on_time_delivery_pct": 250}, {"quality_ppm": -10}, {"annual_spend_usd": -1e9}, {"name": "   "}],
)
def test_vendor_rejects_impossible_values(client: TestClient, head_headers: dict[str, str], overrides: dict) -> None:
    body = {
        "name": f"Bounds Vendor {uuid4().hex[:6]}", "category": "Valves", "country": "India",
        "lead_time_days": 30, "on_time_delivery_pct": 95, "quality_ppm": 100, "annual_spend_usd": 1000,
        **overrides,
    }
    assert client.post("/api/vendors", headers=head_headers, json=body).status_code == 422


def test_bom_csv_rejects_bad_rows(client: TestClient, head_headers: dict[str, str]) -> None:
    pid = _project_id(client, head_headers)
    csv_text = (
        "code,description,quantity,unit_cost_usd,long_lead_days\n"
        "OK-1,Good line,5,100,30\n"
        "NEG-1,Negative qty,-3,100,30\n"
        "NAN-1,NaN qty,nan,100,30\n"
        "COST-1,Negative cost,5,-100,30\n"
        "LEAD-1,Bad lead,5,100,soon\n"
    )
    res = client.post(
        f"/api/projects/{pid}/bom/upload", headers=head_headers,
        files={"file": ("bom.csv", csv_text.encode(), "text/csv")},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["rows_accepted"] == 1
    assert [i["code"] for i in body["bom_items"]] == ["OK-1"]
    assert len(body["errors"]) == 4


def test_bom_csv_size_cap(client: TestClient, head_headers: dict[str, str]) -> None:
    pid = _project_id(client, head_headers)
    big = b"code,description,quantity\n" + b"A,B,1\n" * (2 * 1024 * 1024)
    res = client.post(
        f"/api/projects/{pid}/bom/upload", headers=head_headers,
        files={"file": ("bom.csv", big, "text/csv")},
    )
    assert res.status_code == 413


def test_ingest_bad_supplier_row_is_an_error_not_a_crash() -> None:
    mapping = {"name": 0, "category": 1, "country": 2, "on_time_delivery_pct": 3, "quality_ppm": 4}
    rows = [
        ["Good Co", "Valves", "India", "0", "100"],
        ["Bad Co", "Valves", "India", "250", "100"],
        ["Neg Co", "Valves", "India", "90", "-10"],
    ]
    out, errors = _validate_rows("supplier", mapping, rows)
    assert [r["name"] for r in out] == ["Good Co"]
    assert out[0]["on_time_delivery_pct"] == 0.0, "a real 0 must not become the 90 default"
    assert len(errors) == 2


def test_ingest_bom_rejects_nan_and_negative_cost() -> None:
    mapping = {"code": 0, "description": 1, "quantity": 2, "unit_cost_usd": 3}
    out, errors = _validate_rows(
        "bom", mapping, [["A", "a", "nan", "1"], ["B", "b", "2", "-5"], ["C", "c", "2", "5"]]
    )
    assert [r["code"] for r in out] == ["C"]
    assert len(errors) == 2


@pytest.fixture()
def device_headers(client: TestClient, admin_headers: dict[str, str]) -> dict[str, str]:
    headers, _ = enrol(client, admin_headers, make_store(client, admin_headers))
    return headers


def test_grn_id_path_traversal_rejected(client: TestClient, device_headers: dict[str, str]) -> None:
    res = sync_grn(client, device_headers, grn_id="../../../../PWNED_x")
    assert res.status_code == 422
    assert not list(MEDIA_DIR.parent.parent.glob("**/PWNED_x*"))


def test_non_image_photo_rejected(client: TestClient, device_headers: dict[str, str]) -> None:
    assert sync_grn(client, device_headers, photo=b"MZ\x90\x00not-an-image").status_code == 415


def test_oversized_photo_rejected(client: TestClient, device_headers: dict[str, str]) -> None:
    big = b"\xff\xd8\xff\xe0" + b"\0" * (15 * 1024 * 1024)
    assert sync_grn(client, device_headers, photo=big).status_code == 413


def test_png_photo_kept_as_png(client: TestClient, device_headers: dict[str, str], admin_headers: dict[str, str]) -> None:
    png = b"\x89PNG\r\n\x1a\n" + b"pixels"
    res = sync_grn(client, device_headers, photo=png)
    assert res.status_code == 200, res.text
    photo = client.get(f"/api/store/grns/{res.json()['grn_id']}/photo", headers=admin_headers)
    assert photo.status_code == 200
    assert photo.headers["content-type"] == "image/png"


def test_device_id_must_be_safe(client: TestClient, admin_headers: dict[str, str]) -> None:
    store_id = make_store(client, admin_headers)
    invite = client.post(
        "/api/field-admin/enrolments", headers=admin_headers,
        json={"store_id": store_id, "person_name": "Tester", "person_role": "storekeeper"},
    )
    res = client.post("/api/v1/field/enrol", json={"code": invite.json()["code"], "device_id": "../evil"})
    assert res.status_code == 422
