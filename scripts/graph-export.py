#!/usr/bin/env python3
"""Export knowledge graph from facts.db to JSON for the viewer."""

import sqlite3
import json
import os
import sys
import argparse
from pathlib import Path
from collections import defaultdict

DEFAULT_LEGACY_DB_PATH = Path("/path/to/workspace/memory/facts.db")
DEFAULT_LEGACY_OUT_PATH = Path("/path/to/workspace/memory/graph-data.json")


def resolve_paths(cli_db_path: str | None = None, cli_out_path: str | None = None) -> tuple[Path, Path]:
    """Resolve DB and output paths from CLI, OPENCLAW_WORKSPACE, CWD, then legacy fallback."""
    if cli_db_path:
        db_path = Path(cli_db_path).expanduser()
    else:
        workspace = os.environ.get("OPENCLAW_WORKSPACE")
        if workspace:
            db_path = Path(workspace).expanduser() / "memory" / "facts.db"
        else:
            cwd_candidate = Path.cwd() / "memory" / "facts.db"
            db_path = cwd_candidate if cwd_candidate.exists() else DEFAULT_LEGACY_DB_PATH

    if cli_out_path:
        out_path = Path(cli_out_path).expanduser()
    else:
        if db_path != DEFAULT_LEGACY_DB_PATH and db_path.parent.exists():
            out_path = db_path.parent / "graph-data.json"
        else:
            workspace = os.environ.get("OPENCLAW_WORKSPACE")
            if workspace:
                out_path = Path(workspace).expanduser() / "memory" / "graph-data.json"
            else:
                out_path = DEFAULT_LEGACY_OUT_PATH

    return db_path, out_path

def main():
    parser = argparse.ArgumentParser(description="Export knowledge graph to JSON")
    parser.add_argument("--db-path", help="Path to facts.db (overrides OPENCLAW_WORKSPACE)")
    parser.add_argument("--out-path", help="Path to output JSON file")
    args = parser.parse_args()

    db_path, out_path = resolve_paths(args.db_path, args.out_path)
    if db_path == DEFAULT_LEGACY_DB_PATH and not os.environ.get("OPENCLAW_WORKSPACE") and not args.db_path:
        print(
            f"[graph-export] warning: using legacy db path {DEFAULT_LEGACY_DB_PATH}. "
            "Set OPENCLAW_WORKSPACE or --db-path for portability.",
            file=sys.stderr,
        )
    if out_path == DEFAULT_LEGACY_OUT_PATH and not os.environ.get("OPENCLAW_WORKSPACE") and not args.out_path:
        print(
            f"[graph-export] warning: using legacy output path {DEFAULT_LEGACY_OUT_PATH}. "
            "Set OPENCLAW_WORKSPACE or --out-path for portability.",
            file=sys.stderr,
        )
    if not db_path.exists():
        print(f"[graph-export] error: facts.db not found at {db_path}", file=sys.stderr)
        sys.exit(2)

    out_path.parent.mkdir(parents=True, exist_ok=True)

    db = sqlite3.connect(str(db_path))
    
    # Get all entities from facts + relations
    entities = set()
    categories = {}
    
    # From facts
    for row in db.execute("SELECT DISTINCT entity, category FROM facts").fetchall():
        entities.add(row[0])
        categories[row[0]] = row[1]
    
    # From relations (subjects and objects that are also subjects)
    for row in db.execute("SELECT DISTINCT subject FROM relations").fetchall():
        entities.add(row[0])
    for row in db.execute("SELECT DISTINCT object FROM relations WHERE object IN (SELECT DISTINCT entity FROM facts UNION SELECT DISTINCT subject FROM relations)").fetchall():
        entities.add(row[0])
    
    # Build nodes
    nodes = []
    for entity in sorted(entities):
        cat = categories.get(entity, "other")
        nodes.append({"id": entity, "category": cat})
    
    # Build edges from relations
    edges = []
    entity_set = entities
    for row in db.execute("SELECT subject, predicate, object FROM relations").fetchall():
        subj, pred, obj = row
        # Only include edges where both endpoints are known entities
        if subj in entity_set and obj in entity_set:
            edges.append({"source": subj, "target": obj, "predicate": pred})
        elif subj in entity_set:
            # Object is a value, not an entity — skip for graph viz
            pass
    
    # Build facts per entity
    facts = defaultdict(list)
    for row in db.execute("SELECT entity, key, value FROM facts ORDER BY entity, key").fetchall():
        facts[row[0]].append({"key": row[1], "value": row[2]})
    
    data = {
        "nodes": nodes,
        "edges": edges,
        "facts": dict(facts),
        "stats": {
            "entities": len(nodes),
            "relations": len(edges),
            "facts": sum(len(v) for v in facts.values()),
            "aliases": db.execute("SELECT COUNT(*) FROM aliases").fetchone()[0],
        }
    }
    
    out_path.write_text(json.dumps(data, indent=2))
    print(f"✅ Exported: {len(nodes)} nodes, {len(edges)} edges, {sum(len(v) for v in facts.values())} facts")
    print(f"   → {out_path}")
    
    db.close()

if __name__ == "__main__":
    main()
