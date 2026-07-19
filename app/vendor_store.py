"""Runtime-additive supplier store.

Vendors that ship in `sample_data.py` are the static baseline. Users can
add more at runtime via POST /api/vendors; those land here and are merged
with the static list every time vendor_intel asks for "all suppliers".

State is persisted through `app.persistence` (write-through flush on every
mutation plus full snapshot every 120s + restore on boot) so user-created
vendors survive restarts.
"""

from __future__ import annotations

import logging

from ._cache import invalidates_cache

from collections import defaultdict
from typing import Dict, List, Optional

from .schemas import SupplierRecord


log = logging.getLogger("ct.vendor_store")

# tenant_id -> list of user-added suppliers (preserves insertion order)
_runtime: Dict[str, List[SupplierRecord]] = defaultdict(list)


def _flush_critical_safe() -> None:
    try:
        from .persistence import flush_critical

        flush_critical()
    except Exception:  # noqa: BLE001
        log.exception("flush_critical failed after vendor mutation")


@invalidates_cache
def add_supplier(tenant_id: str, supplier: SupplierRecord) -> SupplierRecord:
    """Add a supplier to the runtime store for a tenant.

    If a supplier with the same name already exists in the runtime store
    (case-insensitive), it is replaced — name acts as the natural key.
    """
    name_key = supplier.name.strip().lower()
    bucket = _runtime[tenant_id]
    for i, existing in enumerate(bucket):
        if existing.name.strip().lower() == name_key:
            bucket[i] = supplier
            _flush_critical_safe()
            return supplier
    bucket.append(supplier)
    _flush_critical_safe()
    return supplier


def list_runtime(tenant_id: Optional[str]) -> List[SupplierRecord]:
    if tenant_id is None:
        # No tenant context — return everything (used by audit / system paths).
        return [s for bucket in _runtime.values() for s in bucket]
    return list(_runtime.get(tenant_id, []))


@invalidates_cache
def remove_supplier(tenant_id: str, name: str) -> bool:
    name_key = name.strip().lower()
    bucket = _runtime.get(tenant_id, [])
    for i, s in enumerate(bucket):
        if s.name.strip().lower() == name_key:
            del bucket[i]
            _flush_critical_safe()
            return True
    return False


# --- persistence hooks (called by app.persistence) ---------------------------

def dump() -> dict:
    """Serialize for snapshot."""
    return {
        tenant_id: [s.model_dump(mode="json") for s in bucket]
        for tenant_id, bucket in _runtime.items()
    }


def load(data: dict) -> None:
    """Restore from snapshot."""
    _runtime.clear()
    for tenant_id, items in (data or {}).items():
        _runtime[tenant_id] = [SupplierRecord(**item) for item in items]
