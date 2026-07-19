"""Load the Mahadev Hydro fixture into a running backend.

Two modes:

  python -m fixtures.hydro.load_hydro --inject
      Inject directly into the in-memory stores. Must be run inside the same
      Python process as the FastAPI app (e.g. an ipython session attached to
      uvicorn) — convenient when you can import `app.*` directly.

  python -m fixtures.hydro.load_hydro --upload-bom http://127.0.0.1:8010 HYD-MAHADEV-220
      POST the BOM CSV to a live backend's /api/projects/{id}/bom/upload
      endpoint. Useful for testing the upload path end-to-end. Note: this
      assumes the project itself is already seeded (or that you've added the
      project via a separate path).

The two modes intentionally do different work — injection is the "all the
data, all the modules" path; upload-bom is the "exercise the CSV pipeline"
path.
"""

from __future__ import annotations

import argparse
import os
import sys
import urllib.request
from typing import Any

from fixtures.hydro.hydro_seed import PROJECT_ID, build_hydro_demo


def inject_into_stores(verbose: bool = True) -> None:
    """Push every entity into the running app's in-memory stores."""

    from app import planning, sourcing  # noqa: F401  (force seed init)
    from app.planning import _projects, _bom_items  # type: ignore
    from app.planning import _seed as _planning_seed
    from app.sample_data import build_demo_request

    _planning_seed()  # ensure baseline demo data is in place first

    demo = build_hydro_demo()

    # Project + milestones
    _projects[demo.project.project_id] = demo.project
    if verbose:
        print(f"[ok] project   : {demo.project.project_id} ({demo.project.name})")

    # BOM
    _bom_items.setdefault(demo.project.project_id, {})
    for item in demo.bom_items:
        _bom_items[demo.project.project_id][item.bom_item_id] = item
    if verbose:
        print(f"[ok] bom       : {len(demo.bom_items)} items")

    # Suppliers, inventory, POs, incidents — these live in the legacy
    # AgentRequest demo scenario. We patch them in by extending the demo
    # dataset that build_demo_request() returns.
    base = build_demo_request()
    base.suppliers.extend(demo.suppliers)
    base.inventory.extend(demo.inventory)
    base.purchase_orders.extend(demo.purchase_orders)
    base.demand_signals.extend(demo.demand_signals)
    base.incidents.extend(demo.incidents)

    if verbose:
        print(f"[ok] suppliers : extended +{len(demo.suppliers)}")
        print(f"[ok] inventory : extended +{len(demo.inventory)}")
        print(f"[ok] POs       : extended +{len(demo.purchase_orders)}")
        print(f"[ok] demand    : extended +{len(demo.demand_signals)}")
        print(f"[ok] incidents : extended +{len(demo.incidents)}")
    print(
        "Note: suppliers/inventory/POs come from build_demo_request() each call;\n"
        "      to make this persist across requests you'll need to wire a\n"
        "      module-level demo cache or seed your own tenant store."
    )


def upload_bom(api_base: str, project_id: str) -> None:
    """POST the BOM CSV to /api/projects/{project_id}/bom/upload."""

    here = os.path.dirname(os.path.abspath(__file__))
    csv_path = os.path.join(here, "bom_hydro.csv")
    with open(csv_path, "rb") as fh:
        body = fh.read()

    url = f"{api_base.rstrip('/')}/api/projects/{project_id}/bom/upload"

    boundary = "----HydroBOMBoundary"
    payload = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="bom_hydro.csv"\r\n'
        f"Content-Type: text/csv\r\n\r\n"
    ).encode() + body + f"\r\n--{boundary}--\r\n".encode()

    req = urllib.request.Request(
        url,
        data=payload,
        method="POST",
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
    )
    try:
        with urllib.request.urlopen(req) as resp:
            print(resp.read().decode())
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code}: {e.read().decode()}")
        sys.exit(1)


def main() -> None:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="mode", required=True)

    sub.add_parser("inject", help="inject into in-memory stores (in-process)")

    up = sub.add_parser("upload-bom", help="POST the BOM CSV to a running backend")
    up.add_argument("api_base", help="e.g. http://127.0.0.1:8010")
    up.add_argument("project_id", nargs="?", default=PROJECT_ID,
                    help=f"Project ID (default: {PROJECT_ID}, must already exist)")

    args = p.parse_args()
    if args.mode == "inject":
        inject_into_stores()
    elif args.mode == "upload-bom":
        upload_bom(args.api_base, args.project_id)


if __name__ == "__main__":
    main()
