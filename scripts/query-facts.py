#!/usr/bin/env python3
"""
Query facts.db from the command line.

Usage:
    python3 scripts/query-facts.py "birthday"           # FTS search
    python3 scripts/query-facts.py --entity Alice       # All facts about Alice
    python3 scripts/query-facts.py --entity Alice --key birthday  # Exact lookup
    python3 scripts/query-facts.py --category decision   # All decisions
    python3 scripts/query-facts.py --stats               # Database stats
"""

import sqlite3
import argparse
import os
import json
from pathlib import Path

from fts_helper import build_or_match_query

DEFAULT_LEGACY_DB_PATH = Path("memory/facts.db")


def resolve_db_path(cli_db_path: str | None = None) -> Path:
    """Resolve facts.db path from CLI, FACTS_DB env var, then legacy fallback."""
    if cli_db_path:
        return Path(cli_db_path).expanduser()

    env_db_path = os.environ.get("FACTS_DB")
    if env_db_path:
        return Path(env_db_path).expanduser()

    return DEFAULT_LEGACY_DB_PATH


def main():
    parser = argparse.ArgumentParser(description="Query facts.db")
    parser.add_argument("query", nargs="?", help="Full-text search query")
    parser.add_argument("--db-path", help="Path to facts.db (overrides FACTS_DB env var)")
    parser.add_argument("--entity", help="Filter by entity")
    parser.add_argument("--key", help="Filter by key (requires --entity)")
    parser.add_argument("--category", help="Filter by category")
    parser.add_argument("--stats", action="store_true", help="Show database statistics")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    db_path = resolve_db_path(args.db_path)
    if not db_path.exists():
        print(f"❌ {db_path} not found. Run init-facts-db.py first.")
        return

    db = sqlite3.connect(str(db_path))
    db.row_factory = sqlite3.Row

    if args.stats:
        total = db.execute("SELECT COUNT(*) FROM facts").fetchone()[0]
        permanent = db.execute("SELECT COUNT(*) FROM facts WHERE permanent=1").fetchone()[0]
        categories = db.execute(
            "SELECT category, COUNT(*) as c FROM facts GROUP BY category ORDER BY c DESC"
        ).fetchall()
        print(f"Total facts: {total} ({permanent} permanent)")
        print("\nBy category:")
        for row in categories:
            print(f"  {row['category']}: {row['c']}")
        return

    if args.entity and args.key:
        # Exact lookup
        row = db.execute(
            "SELECT * FROM facts WHERE entity=? AND key=?",
            (args.entity, args.key)
        ).fetchone()
        if row:
            if args.json:
                print(json.dumps(dict(row)))
            else:
                print(f"{row['entity']}.{row['key']} = {row['value']}")
                print(f"  category: {row['category']} | source: {row['source']} | permanent: {bool(row['permanent'])}")
        else:
            print("No match found.")
        return

    if args.entity:
        rows = db.execute("SELECT * FROM facts WHERE entity=?", (args.entity,)).fetchall()
    elif args.category:
        rows = db.execute("SELECT * FROM facts WHERE category=?", (args.category,)).fetchall()
    elif args.query:
        fts_query = build_or_match_query(args.query, min_len=1)
        if not fts_query:
            rows = []
        else:
            rows = db.execute(
                "SELECT f.* FROM facts_fts fts JOIN facts f ON f.id = fts.rowid WHERE facts_fts MATCH ? ORDER BY fts.rank",
                (fts_query,)
            ).fetchall()
    else:
        parser.print_help()
        return

    if args.json:
        print(json.dumps([dict(r) for r in rows], indent=2))
    else:
        if not rows:
            print("No results.")
            return
        for row in rows:
            perm = " 📌" if row['permanent'] else ""
            print(f"  {row['entity']}.{row['key']} = {row['value']}{perm}")

    db.close()


if __name__ == "__main__":
    main()
