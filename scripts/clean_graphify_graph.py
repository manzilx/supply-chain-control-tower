#!/usr/bin/env python3
"""Remove common graphify false positives for this repo.

Rules:
- Drop INFERRED ``calls`` edges from Python/fixtures sources to npm dependency
  nodes declared in ``package.json`` (builtin ``next()`` vs package name ``next``).
- Relabel ``package.json`` dependency nodes as ``<name> (npm)`` for clarity.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _is_py_source(source_file: str) -> bool:
    p = source_file.replace("\\", "/")
    return p.endswith(".py") or "/fixtures/" in p or p.startswith("fixtures/")


def _is_package_json_dep(node: dict) -> bool:
    sf = (node.get("source_file") or "").replace("\\", "/")
    return sf.endswith("package.json") and node.get("file_type") == "code"


def _should_drop_edge(edge: dict, nodes_by_id: dict[str, dict]) -> bool:
    if edge.get("relation") != "calls" or edge.get("confidence") != "INFERRED":
        return False
    src = nodes_by_id.get(edge.get("source", ""), {})
    tgt = nodes_by_id.get(edge.get("target", ""), {})
    if not _is_package_json_dep(tgt):
        return False
    src_file = src.get("source_file") or edge.get("source_file") or ""
    return _is_py_source(src_file)


def clean_graph_data(data: dict) -> tuple[dict, int, int]:
    nodes = data.get("nodes", [])
    links = data.get("links", data.get("edges", []))
    nodes_by_id = {n["id"]: n for n in nodes if "id" in n}

    removed = 0
    kept = []
    for edge in links:
        if _should_drop_edge(edge, nodes_by_id):
            removed += 1
        else:
            kept.append(edge)

    relabeled = 0
    for node in nodes:
        if not _is_package_json_dep(node):
            continue
        label = node.get("label", "")
        if label and not label.endswith(" (npm)"):
            node["label"] = f"{label} (npm)"
            relabeled += 1

    out = dict(data)
    out["nodes"] = nodes
    if "links" in data:
        out["links"] = kept
    if "edges" in data:
        out["edges"] = kept
    return out, removed, relabeled


def clean_cache_file(path: Path) -> int:
    payload = json.loads(path.read_text(encoding="utf-8"))
    nodes_by_id = {n["id"]: n for n in payload.get("nodes", []) if "id" in n}
    removed = 0
    edges = payload.get("edges", [])
    kept = []
    for edge in edges:
        if _should_drop_edge(edge, nodes_by_id):
            removed += 1
        else:
            kept.append(edge)
    if removed:
        payload["edges"] = kept
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return removed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--graph",
        type=Path,
        default=Path("graphify-out/graph.json"),
        help="Path to graph.json",
    )
    parser.add_argument(
        "--cache-root",
        type=Path,
        default=Path("graphify-out/cache"),
        help="AST/semantic cache directory",
    )
    parser.add_argument("--no-cache", action="store_true", help="Skip cache cleanup")
    args = parser.parse_args()

    graph_path = args.graph.resolve()
    if not graph_path.exists():
        print(f"error: {graph_path} not found", file=sys.stderr)
        return 1

    raw = json.loads(graph_path.read_text(encoding="utf-8"))
    cleaned, removed, relabeled = clean_graph_data(raw)
    graph_path.write_text(json.dumps(cleaned, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"graph: removed {removed} spurious edge(s), relabeled {relabeled} npm dep(s)")

    cache_removed = 0
    if not args.no_cache and args.cache_root.exists():
        for cache_file in args.cache_root.rglob("*.json"):
            cache_removed += clean_cache_file(cache_file)
        print(f"cache: removed {cache_removed} spurious edge(s)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
