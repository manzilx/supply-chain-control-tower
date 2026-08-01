"""SQLite persistence for Storemark — site stores, capture devices, GRNs,
GRN lines and the append-only stock ledger.

Deliberately separate from app/persistence.py's JSON-snapshot dict stores:
this data is durable on its own (SQLite + WAL), so it sits outside the
periodic snapshot loop. store.db and challan photos both live under the
same STATE_DIR the rest of the app already backs up.
"""

from __future__ import annotations

import sqlite3
import uuid

from ..persistence import STATE_DIR


STORE_DB_PATH = STATE_DIR / "store.db"
MEDIA_DIR = STATE_DIR / "media"


def connect() -> sqlite3.Connection:
    """Fresh connection per call — sqlite3.Connection isn't safe to share
    across requests/threads. WAL + foreign keys are pragma'd on every open
    since PRAGMAs are per-connection, not persisted in the file."""

    conn = sqlite3.connect(STORE_DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def new_id() -> str:
    return uuid.uuid4().hex


# Seed aliases → canonical UOM. Never unit-converted in v1 — this table only
# normalises spelling/casing so the matcher can compare like-for-like.
_UOM_ALIASES = {
    "nos": "EA", "pcs": "EA", "ea": "EA", "no": "EA",
    "mtr": "M", "rmt": "M", "m": "M",
    "kgs": "KG", "kg": "KG",
    "mt": "T", "ton": "T",
    "bags": "BAG", "bag": "BAG",
    "ltr": "L", "l": "L",
    "sets": "SET", "set": "SET",
}


_SCHEMA = """
CREATE TABLE IF NOT EXISTS site_stores (
  store_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, project_id TEXT NOT NULL,
  name TEXT NOT NULL, location_note TEXT, active INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL, UNIQUE (tenant_id, project_id, name)
);

CREATE TABLE IF NOT EXISTS capture_devices (
  device_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL,
  token_hash TEXT NOT NULL,
  person_name TEXT NOT NULL, person_role TEXT NOT NULL,
  store_id TEXT REFERENCES site_stores(store_id), project_id TEXT,
  enrolled_at TEXT NOT NULL, enrolled_by TEXT NOT NULL, last_seen_at TEXT,
  last_sequence_no INTEGER NOT NULL DEFAULT 0,
  revoked_at TEXT
);

CREATE TABLE IF NOT EXISTS enrolment_invites (
  code TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, store_id TEXT NOT NULL,
  project_id TEXT NOT NULL, person_name TEXT NOT NULL, person_role TEXT NOT NULL,
  created_by TEXT NOT NULL, created_at TEXT NOT NULL, expires_at TEXT NOT NULL,
  used_at TEXT, device_id TEXT
);

CREATE TABLE IF NOT EXISTS grn (
  grn_id TEXT PRIMARY KEY,
  grn_no TEXT UNIQUE,
  tenant_id TEXT NOT NULL, store_id TEXT NOT NULL REFERENCES site_stores(store_id),
  project_id TEXT NOT NULL, device_id TEXT NOT NULL REFERENCES capture_devices(device_id),
  sequence_no INTEGER NOT NULL,
  status TEXT NOT NULL DEFAULT 'captured',
    -- captured -> extracting -> matched|suggested|triage -> confirmed | cancelled | superseded
  source_kind TEXT NOT NULL DEFAULT 'contractor',        -- 'contractor' | 'free_issue'
  challan_no TEXT, challan_date TEXT, vendor_name_raw TEXT, vendor_name TEXT,
  vehicle_no TEXT, remarks TEXT,
  photo_path TEXT NOT NULL, photo_sha256 TEXT NOT NULL,
  extraction_status TEXT NOT NULL DEFAULT 'pending',     -- pending|running|done|failed|skipped
  extraction_json TEXT, extraction_model TEXT,
  observed_at TEXT NOT NULL, device_clock_offset_ms INTEGER,
  clock_trust TEXT NOT NULL DEFAULT 'device', received_at TEXT NOT NULL,
  confirmed_at TEXT, confirmed_by TEXT, confirmed_via TEXT,  -- 'device' | 'office'
  effects_applied_at TEXT,   -- stamped once the dict-store effects landed; NULL = sweep me
  superseded_by TEXT REFERENCES grn(grn_id), created_at TEXT NOT NULL,
  UNIQUE (device_id, sequence_no)
);

CREATE TABLE IF NOT EXISTS grn_lines (
  grn_line_id TEXT PRIMARY KEY, grn_id TEXT NOT NULL REFERENCES grn(grn_id),
  line_no INTEGER NOT NULL,
  description_raw TEXT NOT NULL,
  code TEXT, uom_raw TEXT, uom TEXT,
  qty_challan REAL,
  qty_received REAL NOT NULL,
  qty_damaged REAL NOT NULL DEFAULT 0, qty_rejected REAL NOT NULL DEFAULT 0,
  batch_no TEXT,
  po_no TEXT,
  match_status TEXT NOT NULL DEFAULT 'unmatched',
    -- unmatched | auto | suggested | confirmed | no_po
  match_confidence REAL, match_candidates TEXT,
  matched_by TEXT, over_receipt INTEGER NOT NULL DEFAULT 0,
  UNIQUE (grn_id, line_no)
);
CREATE INDEX IF NOT EXISTS idx_grn_lines_grn_id ON grn_lines(grn_id);

CREATE TABLE IF NOT EXISTS stock_ledger (
  entry_id TEXT PRIMARY KEY,             -- append-only; no UPDATE/DELETE code path
  tenant_id TEXT NOT NULL, store_id TEXT NOT NULL, project_id TEXT NOT NULL,
  code TEXT NOT NULL, description TEXT NOT NULL, uom TEXT NOT NULL,
  movement TEXT NOT NULL,                -- receipt|issue|return|adjustment|transfer_in|transfer_out
  qty_signed REAL NOT NULL,
  source_kind TEXT NOT NULL DEFAULT 'contractor',
  batch_id TEXT, ref_kind TEXT NOT NULL, ref_id TEXT NOT NULL,
  po_no TEXT, vendor TEXT,
  effective_at TEXT NOT NULL,
  entered_at TEXT NOT NULL, entered_by TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_stock_ledger_code ON stock_ledger(tenant_id, code, store_id);
CREATE INDEX IF NOT EXISTS idx_stock_ledger_ref ON stock_ledger(ref_kind, ref_id);

-- Phase-2/3 shells: empty until later phases, DDL fixed now to avoid
-- mid-phase migrations.
CREATE TABLE IF NOT EXISTS material_issues (
  issue_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, store_id TEXT NOT NULL,
  project_id TEXT NOT NULL, status TEXT NOT NULL, issued_to TEXT, created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS issue_lines (
  issue_line_id TEXT PRIMARY KEY, issue_id TEXT NOT NULL, line_no INTEGER NOT NULL,
  code TEXT, description TEXT, uom TEXT, qty REAL, batch_id TEXT
);

CREATE TABLE IF NOT EXISTS batches (
  batch_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, code TEXT,
  batch_no TEXT, attrs_json TEXT, created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS vendor_deliveries (
  po_no TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, vendor TEXT,
  need_by TEXT, first_receipt_at TEXT, full_receipt_at TEXT, on_time INTEGER
);

CREATE TABLE IF NOT EXISTS uom_alias (
  alias TEXT PRIMARY KEY, canonical TEXT NOT NULL
);
"""


def init_db() -> None:
    """Create the schema (idempotent) and seed uom_alias. Safe to call on
    every boot."""

    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    conn = connect()
    try:
        conn.executescript(_SCHEMA)
        # Dev DBs created before effects_applied_at existed — CREATE TABLE IF
        # NOT EXISTS won't add it, so patch it in defensively.
        try:
            conn.execute("ALTER TABLE grn ADD COLUMN effects_applied_at TEXT")
        except sqlite3.OperationalError:
            pass  # column already present
        conn.executemany(
            "INSERT OR IGNORE INTO uom_alias (alias, canonical) VALUES (?, ?)",
            list(_UOM_ALIASES.items()),
        )
        conn.commit()
    finally:
        conn.close()
