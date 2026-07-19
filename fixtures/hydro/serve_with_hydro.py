"""Boot uvicorn with the Mahadev Hydro fixture injected.

Patches `app.sample_data.build_demo_request` BEFORE any other app module is
imported so that every M4/M5 module (vendor_intel, expediting, logistics,
commercial, simulations) sees the extended supplier/inventory/PO list when
it pulls from `build_demo_request()`.
"""

from __future__ import annotations

# 1) Patch the demo builder first — only sample_data has been imported.
import app.sample_data as _sd
from fixtures.hydro.hydro_seed import build_hydro_demo

_demo = build_hydro_demo()
_orig_build = _sd.build_demo_request


def _patched_build():
    req = _orig_build()
    req.suppliers.extend(_demo.suppliers)
    req.inventory.extend(_demo.inventory)
    req.purchase_orders.extend(_demo.purchase_orders)
    req.demand_signals.extend(_demo.demand_signals)
    req.incidents.extend(_demo.incidents)
    return req


_sd.build_demo_request = _patched_build  # noqa: F811

# 2) Now seed the planning store (project + BOM live in module-level dicts).
from app import planning  # noqa: E402

planning._seed()  # type: ignore[attr-defined]
planning._projects[_demo.project.project_id] = _demo.project  # type: ignore[attr-defined]
planning._bom_items.setdefault(_demo.project.project_id, {})  # type: ignore[attr-defined]
for _item in _demo.bom_items:
    planning._bom_items[_demo.project.project_id][_item.bom_item_id] = _item  # type: ignore[attr-defined]

print(
    f"[hydro] injected project {_demo.project.project_id} "
    f"({len(_demo.bom_items)} BOM items, "
    f"+{len(_demo.suppliers)} suppliers, "
    f"+{len(_demo.purchase_orders)} POs, "
    f"+{len(_demo.incidents)} incidents)"
)

# 3) Serve.
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=8010,
        log_level="warning",
    )
