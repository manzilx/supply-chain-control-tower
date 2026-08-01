"""Enrolment invites + device bearer-token auth for Storemark field capture.

Fully separate from the office JWT (app/auth.py): no JWT ever ships to a
device, no device token grants office access. Tenant/store/project are
stamped from the enrolment row at enrol time and re-read from the device row
on every call — never trusted from a device payload.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Annotated, List, Optional

from fastapi import Depends, Header, HTTPException

from .db import connect
from ..schemas import (
    CaptureDeviceOut,
    CreateEnrolmentRequest,
    DeviceContext,
    EnrolDeviceReply,
    EnrolDeviceRequest,
    EnrolmentInviteOut,
)


INVITE_TTL_MINUTES = 15
LAST_SEEN_THROTTLE_SECONDS = 60


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _last_seen_is_stale(last_seen_at: Optional[str], now: datetime) -> bool:
    """True when last_seen_at is missing, unparseable, or older than the
    throttle window."""

    if not last_seen_at:
        return True
    try:
        seen = datetime.fromisoformat(last_seen_at)
    except ValueError:
        return True
    return (now - seen).total_seconds() >= LAST_SEEN_THROTTLE_SECONDS


def _device_out(row) -> CaptureDeviceOut:
    return CaptureDeviceOut(
        device_id=row["device_id"], person_name=row["person_name"],
        person_role=row["person_role"], store_id=row["store_id"],
        project_id=row["project_id"], enrolled_at=row["enrolled_at"],
        enrolled_by=row["enrolled_by"], last_seen_at=row["last_seen_at"],
        last_sequence_no=row["last_sequence_no"], revoked_at=row["revoked_at"],
    )


def create_enrolment(tenant_id: str, actor: str, req: CreateEnrolmentRequest) -> EnrolmentInviteOut:
    conn = connect()
    try:
        store = conn.execute(
            "SELECT store_id, tenant_id, project_id FROM site_stores WHERE store_id = ?",
            (req.store_id,),
        ).fetchone()
        if store is None or store["tenant_id"] != tenant_id:
            raise HTTPException(status_code=404, detail="Store not found")

        code = secrets.token_urlsafe(16)
        now = _now()
        expires_at = now + timedelta(minutes=INVITE_TTL_MINUTES)
        conn.execute(
            """INSERT INTO enrolment_invites
               (code, tenant_id, store_id, project_id, person_name, person_role,
                created_by, created_at, expires_at, used_at, device_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL)""",
            (
                code, tenant_id, req.store_id, store["project_id"], req.person_name,
                req.person_role, actor, _iso(now), _iso(expires_at),
            ),
        )
        conn.commit()
        return EnrolmentInviteOut(
            code=code, store_id=req.store_id, person_name=req.person_name,
            person_role=req.person_role, expires_at=_iso(expires_at),
        )
    finally:
        conn.close()


def enrol_device(req: EnrolDeviceRequest) -> EnrolDeviceReply:
    conn = connect()
    try:
        invite = conn.execute(
            "SELECT * FROM enrolment_invites WHERE code = ?", (req.code,)
        ).fetchone()
        if invite is None:
            raise HTTPException(status_code=404, detail="Unknown enrolment code")
        if invite["used_at"] is not None:
            raise HTTPException(status_code=409, detail="Enrolment code already used")
        if datetime.fromisoformat(invite["expires_at"]) < _now():
            raise HTTPException(status_code=410, detail="Enrolment code expired")

        secret = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(secret.encode("utf-8")).hexdigest()
        now = _iso(_now())

        existing = conn.execute(
            "SELECT last_sequence_no FROM capture_devices WHERE device_id = ?",
            (req.device_id,),
        ).fetchone()

        if existing is None:
            last_sequence_no = 0
            conn.execute(
                """INSERT INTO capture_devices
                   (device_id, tenant_id, token_hash, person_name, person_role,
                    store_id, project_id, enrolled_at, enrolled_by, last_seen_at,
                    last_sequence_no, revoked_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, 0, NULL)""",
                (
                    req.device_id, invite["tenant_id"], token_hash, invite["person_name"],
                    invite["person_role"], invite["store_id"], invite["project_id"],
                    now, invite["created_by"],
                ),
            )
        else:
            # Re-enrolment (reinstall / revoke-then-reissue): rotate the token
            # and re-stamp the posting from the fresh invite, but keep the
            # sequence watermark so the client resumes above it rather than
            # replaying GRNs the server already has.
            last_sequence_no = existing["last_sequence_no"]
            conn.execute(
                """UPDATE capture_devices SET token_hash = ?, tenant_id = ?,
                   person_name = ?, person_role = ?, store_id = ?, project_id = ?,
                   revoked_at = NULL WHERE device_id = ?""",
                (
                    token_hash, invite["tenant_id"], invite["person_name"],
                    invite["person_role"], invite["store_id"], invite["project_id"],
                    req.device_id,
                ),
            )

        conn.execute(
            "UPDATE enrolment_invites SET used_at = ?, device_id = ? WHERE code = ?",
            (now, req.device_id, req.code),
        )
        conn.commit()

        return EnrolDeviceReply(
            device_id=req.device_id, token=secret, store_id=invite["store_id"],
            project_id=invite["project_id"], tenant_id=invite["tenant_id"],
            person_name=invite["person_name"], person_role=invite["person_role"],
            last_sequence_no=last_sequence_no,
        )
    finally:
        conn.close()


def current_device(
    authorization: Annotated[Optional[str], Header(alias="Authorization")] = None,
) -> DeviceContext:
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(status_code=401, detail="Authorization header must be 'Bearer <token>'")
    token_hash = hashlib.sha256(parts[1].encode("utf-8")).hexdigest()

    conn = connect()
    try:
        row = conn.execute(
            "SELECT * FROM capture_devices WHERE token_hash = ?", (token_hash,)
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=401, detail="Unknown device token")
        if row["revoked_at"] is not None:
            raise HTTPException(status_code=403, detail="Device revoked")
        # last_seen_at is a liveness hint, not an audit record — one write per
        # minute per device is enough, and every field call goes through here.
        now = _now()
        if _last_seen_is_stale(row["last_seen_at"], now):
            conn.execute(
                "UPDATE capture_devices SET last_seen_at = ? WHERE device_id = ?",
                (_iso(now), row["device_id"]),
            )
            conn.commit()
        return DeviceContext(
            device_id=row["device_id"], tenant_id=row["tenant_id"],
            store_id=row["store_id"], project_id=row["project_id"],
            person_name=row["person_name"], person_role=row["person_role"],
        )
    finally:
        conn.close()


def storekeeper_device(
    device: Annotated[DeviceContext, Depends(current_device)],
) -> DeviceContext:
    if device.person_role != "storekeeper":
        raise HTTPException(status_code=403, detail="Storekeeper role required")
    return device


def revoke_device(tenant_id: str, device_id: str) -> CaptureDeviceOut:
    conn = connect()
    try:
        row = conn.execute(
            "SELECT * FROM capture_devices WHERE device_id = ?", (device_id,)
        ).fetchone()
        if row is None or row["tenant_id"] != tenant_id:
            raise HTTPException(status_code=404, detail="Device not found")
        conn.execute(
            "UPDATE capture_devices SET revoked_at = ? WHERE device_id = ?",
            (_iso(_now()), device_id),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM capture_devices WHERE device_id = ?", (device_id,)
        ).fetchone()
        return _device_out(row)
    finally:
        conn.close()


def list_devices(tenant_id: str) -> List[CaptureDeviceOut]:
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT * FROM capture_devices WHERE tenant_id = ? ORDER BY enrolled_at DESC",
            (tenant_id,),
        ).fetchall()
        return [_device_out(r) for r in rows]
    finally:
        conn.close()
