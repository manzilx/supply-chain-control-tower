"""Storemark API surface: field device routes (/api/v1/field/*), field-admin
enrolment/device management, and the office store/GRN/stock routes
(/api/store/*).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import ValidationError

from . import db, extraction, ledger, matching
from . import devices as devices_mod
from . import grn as grn_mod
from .devices import storekeeper_device
from ..auth import require_perm
from ..schemas import (
    CaptureDeviceOut,
    ConfirmGrnReply,
    ConfirmGrnRequest,
    CreateEnrolmentRequest,
    CreateStoreRequest,
    DeviceContext,
    EnrolDeviceReply,
    EnrolDeviceRequest,
    EnrolmentInviteOut,
    FieldContext,
    FieldContextPO,
    FieldGrnRecord,
    GrnDetail,
    GrnSummary,
    GrnSyncReply,
    LedgerEntryOut,
    RejectGrnRequest,
    SiteStoreOut,
    StockBalance,
    User,
    VendorOtdRow,
)


router = APIRouter()


# --- Field device (Bearer device token) ---------------------------------------


@router.post("/api/v1/field/enrol", response_model=EnrolDeviceReply)
async def api_field_enrol(body: EnrolDeviceRequest) -> EnrolDeviceReply:
    return devices_mod.enrol_device(body)


@router.get("/api/v1/field/context", response_model=FieldContext)
async def api_field_context(
    device: Annotated[DeviceContext, Depends(storekeeper_device)],
    if_none_match: Annotated[Optional[str], Header(alias="If-None-Match")] = None,
) -> Response:
    from .. import sourcing

    pool = [
        po for po in sourcing.list_pos(tenant_id=device.tenant_id)
        if po.project_id == device.project_id
        and po.status in ("released", "in_transit")
        and matching.remaining_qty(po) > 0
    ]
    pos = [
        FieldContextPO(
            po_no=po.po_no, vendor=po.vendor, code=po.code, description=po.description,
            quantity=po.quantity, uom=po.uom, ct_gr_qty=po.ct_gr_qty or 0,
            need_by=po.need_by.isoformat() if po.need_by else None,
        )
        for po in pool
    ]

    conn = db.connect()
    try:
        alias_rows = conn.execute("SELECT alias, canonical FROM uom_alias").fetchall()
    finally:
        conn.close()

    body = FieldContext(
        store_id=device.store_id, project_id=device.project_id, tenant_id=device.tenant_id,
        pos=pos, vendors=sorted({po.vendor for po in pool}), bom_codes=sorted({po.code for po in pool}),
        uom_aliases={r["alias"]: r["canonical"] for r in alias_rows},
        recent_receipts=grn_mod.list_grns(device.tenant_id, store_id=device.store_id)[:20],
    )
    payload = body.model_dump_json().encode("utf-8")
    etag = hashlib.sha256(payload).hexdigest()
    if if_none_match == etag:
        return Response(status_code=304)
    return Response(content=payload, media_type="application/json", headers={"ETag": etag})


@router.post("/api/v1/field/grns", response_model=GrnSyncReply)
async def api_field_sync_grn(
    device: Annotated[DeviceContext, Depends(storekeeper_device)],
    record: Annotated[str, Form()],
    photo: Annotated[UploadFile, File()],
) -> GrnSyncReply:
    try:
        field_record = FieldGrnRecord.model_validate(json.loads(record))
    except (json.JSONDecodeError, ValidationError) as e:
        raise HTTPException(status_code=422, detail=f"Invalid record JSON: {e}")

    photo_bytes = await photo.read()
    # Blocking photo write + SQLite work — keep it off the event loop.
    reply = await asyncio.to_thread(grn_mod.create_from_sync, device, field_record, photo_bytes)

    if not reply.duplicate:
        conn = db.connect()
        try:
            row = conn.execute(
                "SELECT extraction_status FROM grn WHERE grn_id = ?", (field_record.grn_id,)
            ).fetchone()
        finally:
            conn.close()
        if row and row["extraction_status"] != "skipped":
            asyncio.create_task(extraction.run_extraction(field_record.grn_id))

    return reply


@router.get("/api/v1/field/grns/{grn_id}", response_model=GrnDetail)
async def api_field_get_grn(
    grn_id: str,
    device: Annotated[DeviceContext, Depends(storekeeper_device)],
) -> GrnDetail:
    return grn_mod.get_grn_detail(grn_id, device.tenant_id, device.store_id)


@router.post("/api/v1/field/grns/{grn_id}/confirm", response_model=ConfirmGrnReply)
async def api_field_confirm_grn(
    grn_id: str,
    req: ConfirmGrnRequest,
    device: Annotated[DeviceContext, Depends(storekeeper_device)],
) -> ConfirmGrnReply:
    return grn_mod.confirm_grn(
        grn_id, req, actor=device.person_name, via="device",
        tenant_id=device.tenant_id, store_id=device.store_id,
    )


# --- Field admin (office JWT) --------------------------------------------------


@router.post("/api/field-admin/enrolments", response_model=EnrolmentInviteOut)
async def api_create_enrolment(
    body: CreateEnrolmentRequest,
    user: Annotated[User, Depends(require_perm("device", "enrol"))],
) -> EnrolmentInviteOut:
    return devices_mod.create_enrolment(user.tenant_id, user.user_id, body)


@router.get("/api/field-admin/devices", response_model=List[CaptureDeviceOut])
async def api_list_devices(
    user: Annotated[User, Depends(require_perm("device", "enrol"))],
) -> List[CaptureDeviceOut]:
    return devices_mod.list_devices(user.tenant_id)


@router.post("/api/field-admin/devices/{device_id}/revoke", response_model=CaptureDeviceOut)
async def api_revoke_device(
    device_id: str,
    user: Annotated[User, Depends(require_perm("device", "revoke"))],
) -> CaptureDeviceOut:
    return devices_mod.revoke_device(user.tenant_id, device_id)


# --- Office store / GRN / stock (office JWT) -----------------------------------


@router.post("/api/store/stores", response_model=SiteStoreOut)
async def api_create_store(
    body: CreateStoreRequest,
    user: Annotated[User, Depends(require_perm("store", "create"))],
) -> SiteStoreOut:
    from ..planning import get_project
    if not get_project(body.project_id, tenant_id=user.tenant_id):
        raise HTTPException(status_code=404, detail="Project not found")

    conn = db.connect()
    try:
        store_id = db.new_id()
        now = datetime.now(timezone.utc).isoformat()
        try:
            conn.execute(
                """INSERT INTO site_stores
                   (store_id, tenant_id, project_id, name, location_note, active, created_at)
                   VALUES (?, ?, ?, ?, ?, 1, ?)""",
                (store_id, user.tenant_id, body.project_id, body.name, body.location_note, now),
            )
        except sqlite3.IntegrityError:
            raise HTTPException(status_code=409, detail="Store with this name already exists for the project")
        conn.commit()
        return SiteStoreOut(
            store_id=store_id, tenant_id=user.tenant_id, project_id=body.project_id,
            name=body.name, location_note=body.location_note, active=True, created_at=now,
        )
    finally:
        conn.close()


@router.get("/api/store/stores", response_model=List[SiteStoreOut])
async def api_list_stores(
    user: Annotated[User, Depends(require_perm("stock", "read"))],
) -> List[SiteStoreOut]:
    conn = db.connect()
    try:
        rows = conn.execute(
            "SELECT * FROM site_stores WHERE tenant_id = ? ORDER BY created_at DESC",
            (user.tenant_id,),
        ).fetchall()
        return [
            SiteStoreOut(
                store_id=r["store_id"], tenant_id=r["tenant_id"], project_id=r["project_id"],
                name=r["name"], location_note=r["location_note"], active=bool(r["active"]),
                created_at=r["created_at"],
            )
            for r in rows
        ]
    finally:
        conn.close()


@router.get("/api/store/grns", response_model=List[GrnSummary])
async def api_list_grns(
    user: Annotated[User, Depends(require_perm("grn", "read"))],
    status: Optional[str] = None,
    store_id: Optional[str] = None,
    triage: bool = False,
) -> List[GrnSummary]:
    return grn_mod.list_grns(user.tenant_id, status=status, store_id=store_id, triage=triage)


@router.get("/api/store/grns/{grn_id}", response_model=GrnDetail)
async def api_get_grn(
    grn_id: str,
    user: Annotated[User, Depends(require_perm("grn", "read"))],
) -> GrnDetail:
    return grn_mod.get_grn_detail(grn_id, user.tenant_id)


@router.get("/api/store/grns/{grn_id}/photo")
async def api_get_grn_photo(
    grn_id: str,
    user: Annotated[User, Depends(require_perm("grn", "read"))],
) -> FileResponse:
    conn = db.connect()
    try:
        row = conn.execute(
            "SELECT tenant_id, photo_path FROM grn WHERE grn_id = ?", (grn_id,)
        ).fetchone()
    finally:
        conn.close()
    if row is None or row["tenant_id"] != user.tenant_id:
        raise HTTPException(status_code=404, detail="GRN not found")
    return FileResponse(row["photo_path"], media_type="image/jpeg")


@router.post("/api/store/grns/{grn_id}/confirm", response_model=ConfirmGrnReply)
async def api_confirm_grn(
    grn_id: str,
    req: ConfirmGrnRequest,
    user: Annotated[User, Depends(require_perm("grn", "confirm"))],
) -> ConfirmGrnReply:
    return grn_mod.confirm_grn(grn_id, req, actor=user.user_id, via="office", tenant_id=user.tenant_id)


@router.post("/api/store/grns/{grn_id}/reject", response_model=GrnDetail)
async def api_reject_grn(
    grn_id: str,
    body: RejectGrnRequest,
    user: Annotated[User, Depends(require_perm("grn", "confirm"))],
) -> GrnDetail:
    return grn_mod.reject_grn(grn_id, body.reason, actor=user.user_id, tenant_id=user.tenant_id)


@router.get("/api/store/stock", response_model=List[StockBalance])
async def api_stock_balances(
    user: Annotated[User, Depends(require_perm("stock", "read"))],
    store_id: Optional[str] = None,
) -> List[StockBalance]:
    return ledger.stock_balances(user.tenant_id, store_id=store_id)


@router.get("/api/store/stock/{code}/ledger", response_model=List[LedgerEntryOut])
async def api_code_ledger(
    code: str,
    user: Annotated[User, Depends(require_perm("stock", "read"))],
    store_id: Optional[str] = None,
) -> List[LedgerEntryOut]:
    return ledger.code_ledger(user.tenant_id, code, store_id=store_id)


@router.get("/api/store/vendor-otd", response_model=List[VendorOtdRow])
async def api_vendor_otd(
    user: Annotated[User, Depends(require_perm("po", "read"))],
) -> List[VendorOtdRow]:
    return ledger.vendor_otd(user.tenant_id)
