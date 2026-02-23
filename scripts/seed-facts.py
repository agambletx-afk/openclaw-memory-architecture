#!/usr/bin/env python3
"""
Seed facts.db with your personal facts.
Edit the FACTS list below with your own data, then run:
    python3 scripts/seed-facts.py
"""

import sqlite3
import os
import argparse
from pathlib import Path

DEFAULT_LEGACY_DB_PATH = Path("memory/facts.db")


# ─── Edit these with your own facts ─────────────────────────────────────────
# Format: (entity, key, value, category, source, permanent)
# Categories: person, project, decision, convention, credential, preference, date, location

FACTS = [
    # People
    # ("Alice", "birthday", "March 15, 1990", "date", "USER.md", 1),
    # ("Alice", "relationship", "My partner", "person", "USER.md", 1),
    # ("Bob", "birthday", "June 3, 2015", "date", "USER.md", 1),
    # ("Bob", "relationship", "My daughter", "person", "USER.md", 1),

    # Preferences
    # ("user", "theme", "dark mode", "preference", "conversation", 1),
    # ("user", "communication_style", "Direct, no fluff", "preference", "USER.md", 1),
    # ("user", "timezone", "America/New_York", "preference", "USER.md", 1),

    # Projects
    # ("MyProject", "stack", "Next.js 15, PostgreSQL, Docker", "project", "codebase", 0),
    # ("MyProject", "url", "https://myproject.com", "project", "config", 0),

    # Decisions (permanent by default — they capture rationale)
    # ("decision", "SQLite over PostgreSQL for agent memory", "Local-first, no server dependency, FTS5 built-in", "decision", "2026-02-15", 1),
    # ("decision", "Hybrid memory over pure vector search", "80% of queries are structured lookups, vector is overkill", "decision", "2026-02-15", 1),

    # Conventions (rules your agent should always follow)
    # ("convention", "use trash not rm", "Recoverable deletes beat permanent ones", "convention", "AGENTS.md", 1),
    # ("convention", "always check timezone before stating time", "Run TZ command, never do mental math", "convention", "AGENTS.md", 1),
]


def resolve_db_path(cli_db_path: str | None = None) -> Path:
    """Resolve facts.db path from CLI, FACTS_DB env var, then legacy fallback."""
    if cli_db_path:
        return Path(cli_db_path).expanduser()

    env_db_path = os.environ.get("FACTS_DB")
    if env_db_path:
        return Path(env_db_path).expanduser()

    return DEFAULT_LEGACY_DB_PATH


def parse_args():
    parser = argparse.ArgumentParser(description="Seed facts into facts.db")
    parser.add_argument("--db-path", help="Path to facts.db (overrides FACTS_DB env var)")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned inserts and estimates, then rollback instead of committing.",
    )
    return parser.parse_args()


def seed(db_path: Path, dry_run: bool = False):
    if not db_path.exists():
        print(f"❌ {db_path} not found. Run init-facts-db.py first.")
        return

    if not FACTS:
        print("⚠️  No facts to seed. Edit FACTS list in this file first.")
        return

    db = sqlite3.connect(str(db_path))

    inserted = 0
    skipped = 0
    planned_inserts = []
    for entity, key, value, category, source, permanent in FACTS:
        # Check for duplicates
        existing = db.execute(
            "SELECT id FROM facts WHERE entity=? AND key=? AND value=?",
            (entity, key, value)
        ).fetchone()
        if existing:
            skipped += 1
            continue
        planned_inserts.append((entity, key, category, source, permanent))
        db.execute(
            "INSERT INTO facts (entity, key, value, category, source, permanent) VALUES (?, ?, ?, ?, ?, ?)",
            (entity, key, value, category, source, permanent)
        )
        inserted += 1

    total_before = db.execute("SELECT COUNT(*) FROM facts").fetchone()[0] - inserted
    total_after_estimate = total_before + inserted
    print(f"Planned inserts: {inserted}")
    print(f"Planned duplicates skipped: {skipped}")
    print(f"Estimated total rows after run: {total_after_estimate}")
    if dry_run and planned_inserts:
        print("Planned operations:")
        for entity, key, category, source, permanent in planned_inserts:
            print(
                f"  + INSERT facts(entity={entity!r}, key={key!r}, category={category!r}, "
                f"source={source!r}, permanent={permanent})"
            )

    if dry_run:
        db.rollback()
        print("Dry run complete. Rolled back all changes.")
    else:
        db.commit()
        total = db.execute("SELECT COUNT(*) FROM facts").fetchone()[0]
        print(f"✅ Seeded {inserted} facts ({skipped} duplicates skipped). Total: {total}")
    db.close()


if __name__ == "__main__":
    args = parse_args()
    seed(db_path=resolve_db_path(args.db_path), dry_run=args.dry_run)
