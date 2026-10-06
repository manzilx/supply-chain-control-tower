"""One tenant's audit volume must not evict another tenant's history."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app import audit
from app.schemas import AuditEvent


def _event(tenant: str, n: int, at: datetime) -> AuditEvent:
    return AuditEvent(
        event_id=f"T-{tenant}-{n}", occurred_at=at, actor="t", action="created",
        entity_kind="system", entity_id=str(n), subject="s", summary="s",
        source="system", tenant_id=tenant,
    )


def test_busy_tenant_does_not_evict_others() -> None:
    ring = audit._TenantRing(maxlen=5)
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    ring.append(_event("quiet", 0, t0))
    for i in range(50):
        ring.append(_event("busy", i, t0 + timedelta(seconds=i + 1)))

    assert [e.event_id for e in ring.snapshot("quiet")] == ["T-quiet-0"]
    assert len(ring.snapshot("busy")) == 5
    merged = list(ring)
    assert merged[0].event_id == "T-quiet-0"
    assert [e.occurred_at for e in merged] == sorted(e.occurred_at for e in merged)


def test_restore_extend_keeps_order_and_unscoped_bucket() -> None:
    ring = audit._TenantRing(maxlen=3)
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    events = [_event("a", i, t0 + timedelta(minutes=10 - i)) for i in range(5)]  # out of order
    events.append(_event("", 99, t0))  # e.g. unmatched SAP event
    ring.extend(events)
    a = ring.snapshot("a")
    assert len(a) == 3
    assert [e.occurred_at for e in a] == sorted(e.occurred_at for e in a)
    assert any(e.event_id == "T--99" for e in ring)
