#!/usr/bin/env python3
"""
Importance-Based Memory Pruner — stolen from ClawVault's retention model.

Scans daily memory files and auto-prunes low-importance entries older than 7 days.
Promotes high-importance entries to MEMORY.md if not already there.

Importance tiers:
  i >= 0.8  STRUCTURAL — permanent, never pruned, promoted to MEMORY.md
  0.4-0.79  POTENTIAL  — kept for 30 days, then pruned
  i < 0.4   CONTEXTUAL — pruned after 7 days

Usage:
  python3 scripts/prune-memory.py              # Run pruning
  python3 scripts/prune-memory.py --dry-run    # Preview what would be pruned
"""

import os
import re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

WORKSPACE = None
MEMORY_DIR = None
MEMORY_MD = None


def resolve_workspace_dir(cli_workspace=None):
    """Resolve workspace using --workspace, OPENCLAW_WORKSPACE, then cwd."""
    if cli_workspace:
        return Path(cli_workspace).expanduser().resolve()

    env_workspace = os.environ.get("OPENCLAW_WORKSPACE")
    if env_workspace:
        return Path(env_workspace).expanduser().resolve()

    return Path.cwd()


def configure_paths(cli_workspace=None):
    """Configure and validate runtime paths."""
    workspace = resolve_workspace_dir(cli_workspace)
    memory_dir = workspace / "memory"
    memory_md = workspace / "MEMORY.md"

    if not workspace.exists():
        print(
            f"❌ Workspace directory does not exist: {workspace}\n"
            "   Provide --workspace <path> or set OPENCLAW_WORKSPACE to a valid workspace.",
            file=sys.stderr,
        )
        sys.exit(1)

    if not memory_dir.exists():
        print(
            f"❌ Memory directory not found: {memory_dir}\n"
            "   Expected <workspace>/memory. Create it or pass --workspace with the correct root.",
            file=sys.stderr,
        )
        sys.exit(1)

    return workspace, str(memory_dir), str(memory_md)

# Retention periods
CONTEXTUAL_DAYS = 7    # i < 0.4: auto-prune after 7 days
POTENTIAL_DAYS = 30    # 0.4 <= i < 0.8: auto-prune after 30 days
# i >= 0.8: never pruned

# Pattern to match tagged observations
OBS_PATTERN = re.compile(r'^- \[(\w+)\|i=(\d+\.\d+)\]\s+(.+)$')


def parse_date_from_filename(filename):
    """Extract date from YYYY-MM-DD.md filename."""
    match = re.match(r'^(\d{4}-\d{2}-\d{2})\.md$', filename)
    if match:
        try:
            return datetime.strptime(match.group(1), '%Y-%m-%d').date()
        except ValueError:
            pass
    return None


def should_prune(importance, file_age_days):
    """Determine if an observation should be pruned based on importance and age."""
    if importance >= 0.8:
        return False  # Structural — never prune
    elif importance >= 0.4:
        return file_age_days > POTENTIAL_DAYS  # Potential — 30 day retention
    else:
        return file_age_days > CONTEXTUAL_DAYS  # Contextual — 7 day retention


def prune_file(filepath, file_date, today, dry_run=False):
    """Process a single daily memory file. Returns (kept_lines, pruned_count, promoted)."""
    age_days = (today - file_date).days

    with open(filepath, 'r') as f:
        lines = f.readlines()

    kept = []
    pruned = 0
    promoted = []

    for line in lines:
        match = OBS_PATTERN.match(line.strip())
        if not match:
            # Non-observation lines: keep headers, manual notes, etc.
            kept.append(line)
            continue

        obs_type = match.group(1)
        importance = float(match.group(2))
        content = match.group(3)

        if should_prune(importance, age_days):
            pruned += 1
            continue

        kept.append(line)

        # Promote structural observations
        if importance >= 0.8:
            promoted.append({
                'type': obs_type,
                'importance': importance,
                'content': content,
                'date': file_date.isoformat(),
            })

    if not dry_run and pruned > 0:
        with open(filepath, 'w') as f:
            f.writelines(kept)

    return kept, pruned, promoted


def run(dry_run=False, workspace=None):
    """Main pruning loop."""
    global WORKSPACE, MEMORY_DIR, MEMORY_MD
    WORKSPACE, MEMORY_DIR, MEMORY_MD = configure_paths(workspace)

    today = datetime.now(timezone.utc).date()
    total_pruned = 0
    total_promoted = 0
    files_modified = 0
    all_promoted = []

    for filename in sorted(os.listdir(MEMORY_DIR)):
        file_date = parse_date_from_filename(filename)
        if not file_date:
            continue

        filepath = os.path.join(MEMORY_DIR, filename)
        age_days = (today - file_date).days

        # Skip files too new to prune
        if age_days < CONTEXTUAL_DAYS:
            continue

        kept, pruned, promoted = prune_file(filepath, file_date, today, dry_run)

        if pruned > 0:
            files_modified += 1
            total_pruned += pruned
            action = "would prune" if dry_run else "pruned"
            print(f"  {filename}: {action} {pruned} observations ({age_days}d old)")

        all_promoted.extend(promoted)

    # Report promotions (structural items to consider for MEMORY.md)
    if all_promoted:
        total_promoted = len(all_promoted)
        print(f"\n📌 {total_promoted} structural observations (i≥0.8) — candidates for MEMORY.md:")
        for p in all_promoted[:10]:
            print(f"  [{p['type']}] {p['date']}: {p['content'][:100]}")

    print(f"\nSummary: {total_pruned} pruned, {files_modified} files modified, {total_promoted} promotion candidates")


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Importance-based memory pruner')
    parser.add_argument('--dry-run', action='store_true', help='Preview without modifying')
    parser.add_argument('--workspace', type=str, help='Workspace root (defaults: --workspace, OPENCLAW_WORKSPACE, cwd)')
    args = parser.parse_args()
    run(dry_run=args.dry_run, workspace=args.workspace)
