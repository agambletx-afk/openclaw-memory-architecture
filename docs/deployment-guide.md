# OpenClaw Memory Architecture: Deployment Guide

**Based on CoolmannS/openclaw-memory-architecture**
*Field-tested on a DigitalOcean 4GB droplet, February 2026*

This guide documents the real-world installation of CoolmannS's memory architecture on a production OpenClaw droplet. It covers what the README doesn't: actual deployment steps, permission gotchas, plugin registration, environment configuration, and every error encountered during a live install.

---

## Architecture Overview

The system has four stages, deployed incrementally:

| Stage | Components | What It Does |
|-------|-----------|--------------|
| 1. Core (this guide) | Schema + seed/query/search scripts | Manual fact storage and retrieval via CLI |
| 2. Auto-injection | graph-memory plugin | Automatically injects relevant facts into every agent conversation |
| 3. Auto-extraction | graph-ingest-daily.py cron | Extracts new facts from daily conversation logs |
| 4. Semantic search | plugin-continuity-fix + embeddings | Fuzzy/contextual recall for queries that don't match exact entities |

This guide covers Stages 1 and 2.

---

## Prerequisites

| Requirement | Details |
|-------------|---------|
| OpenClaw | v2026.2+ on a one-click DigitalOcean droplet (or equivalent Linux server) |
| RAM | 4GB minimum recommended |
| Python 3 | Pre-installed on Ubuntu droplets |
| Node.js | Pre-installed with OpenClaw |
| Build tools | Required for better-sqlite3 native compilation |
| SQLite3 CLI | For manual database operations and troubleshooting |

Install system packages:

```bash
apt install build-essential sqlite3 -y
```

---

## Stage 1: Core Database and Scripts

### Step 1: Create Directory Structure

All memory data lives under the OpenClaw home directory. The openclaw user must own everything.

```bash
mkdir -p /home/openclaw/.openclaw/memory
mkdir -p /home/openclaw/.openclaw/scripts
```

### Step 2: Clone and Copy

Clone the repository to a temporary directory, copy only what you need, then clean up.

```bash
cd /tmp
git clone https://github.com/coolmanns/openclaw-memory-architecture.git

# Schema
cp /tmp/openclaw-memory-architecture/schema/facts.sql /home/openclaw/.openclaw/memory/

# Core scripts
cp /tmp/openclaw-memory-architecture/scripts/graph-search.py /home/openclaw/.openclaw/scripts/
cp /tmp/openclaw-memory-architecture/scripts/query-facts.py /home/openclaw/.openclaw/scripts/
cp /tmp/openclaw-memory-architecture/scripts/seed-facts.py /home/openclaw/.openclaw/scripts/
cp /tmp/openclaw-memory-architecture/scripts/graph-init.py /home/openclaw/.openclaw/scripts/
cp /tmp/openclaw-memory-architecture/scripts/fts_helper.py /home/openclaw/.openclaw/scripts/

# Clean up
rm -rf /tmp/openclaw-memory-architecture
```

### Step 3: Initialize the Database

Apply the schema directly using sqlite3. Do not rely on graph-init.py for first-time setup as older versions crash on empty databases.

```bash
sqlite3 /home/openclaw/.openclaw/memory/facts.db < /home/openclaw/.openclaw/memory/facts.sql
```

Verify the tables were created:

```bash
sqlite3 /home/openclaw/.openclaw/memory/facts.db ".tables"
```

Expected output:

```
aliases              facts_fts_data       relations_fts_config
co_occurrences       facts_fts_docsize    relations_fts_data
facts                facts_fts_idx        relations_fts_docsize
facts_fts            relations            relations_fts_idx
facts_fts_config     relations_fts
```

> **Note:** If graph-init.py has been updated with the fix for the fresh-database crash, you can use `python3 graph-init.py --db-path /path/to/facts.db` instead.

### Step 4: Set File Ownership

Everything must be owned by the openclaw user. Files created as root will cause "attempt to write a readonly database" errors at runtime.

```bash
chown -R openclaw:openclaw /home/openclaw/.openclaw/memory/
chown -R openclaw:openclaw /home/openclaw/.openclaw/scripts/
```

> **Warning:** This is the most common installation failure. If you create files or directories as root (which you will be when SSH'd in), the openclaw service cannot write to them. Always chown after creating or modifying files.

### Step 5: Set Environment Variables

Scripts resolve database paths using environment variables. These must be set in two places.

**For the OpenClaw service** (reads from /opt/openclaw.env):

```bash
echo 'OPENCLAW_WORKSPACE=/home/openclaw/.openclaw' >> /opt/openclaw.env
```

**For the openclaw user's shell** (for CLI usage and troubleshooting):

```bash
cat >> /home/openclaw/.profile << 'EOF'
export OPENCLAW_WORKSPACE=/home/openclaw/.openclaw
export FACTS_DB=/home/openclaw/.openclaw/memory/facts.db
EOF
```

> **Warning:** Do not put these in `.bashrc`. Ubuntu's default .bashrc has a non-interactive guard at the top that prevents exports from running in non-login shells (including `su -c` commands). Use `.profile` instead.

### Step 6: Seed Test Data

Insert a few facts to verify the system works:

```bash
sqlite3 /home/openclaw/.openclaw/memory/facts.db << 'SQL'
INSERT INTO facts (entity, key, value, category, importance, source)
  VALUES ('YourName', 'role', 'Your job title', 'identity', 0.9, 'manual-seed');
INSERT INTO facts (entity, key, value, category, importance, source)
  VALUES ('YourName', 'location', 'Your city', 'identity', 0.8, 'manual-seed');
SQL
```

### Step 7: Test the Search

Run the search as the openclaw user to verify path resolution and database access:

```bash
su - openclaw -c "python3 /home/openclaw/.openclaw/scripts/graph-search.py 'YourName' --json"
```

Expected: JSON array with your seeded facts, scored at 70 (entity match).

> **If you see** `using legacy facts.db path /home/coolmann/...` the environment variables aren't being picked up. Verify `.profile` has the exports and re-run.

---

## Stage 2: Auto-Injection Plugin

The graph-memory plugin hooks into OpenClaw's `before_agent_start` event. Every incoming message is automatically searched against the knowledge graph. Relevant facts are injected as context before the agent processes the message. The agent doesn't decide to use memory. It just has it.

### How the Plugin Works

On each message, the plugin:

1. Extracts the user's last message text
2. Strips context blocks (continuity, stability, previous graph memory) to isolate the actual query
3. Spawns `graph-search.py` with the cleaned query (500ms timeout)
4. Filters results: entity matches (score 65+) always pass, FTS-only results only included if entity matches exist
5. Bumps activation scores on retrieved facts (Hebbian learning)
6. Wires co-occurrence links between facts retrieved together
7. Injects a `[GRAPH MEMORY]` block into the agent's context

Messages under 5 characters are skipped. Repeated queries hit the LRU cache (10 entries, 60s TTL). If the search returns nothing, zero context is injected and the agent never sees it.

### Step 1: Copy the Plugin

```bash
cd /tmp
git clone https://github.com/coolmanns/openclaw-memory-architecture.git
mkdir -p /home/openclaw/.openclaw/extensions
cp -r /tmp/openclaw-memory-architecture/plugin-graph-memory /home/openclaw/.openclaw/extensions/graph-memory
rm -rf /tmp/openclaw-memory-architecture
```

### Step 2: Install Dependencies

```bash
cd /home/openclaw/.openclaw/extensions/graph-memory
npm install
```

This compiles better-sqlite3 natively. If it fails, verify build-essential is installed.

### Step 3: Set Ownership

```bash
chown -R openclaw:openclaw /home/openclaw/.openclaw/extensions/graph-memory/
```

### Step 4: Register the Plugin

Add the plugin to your `openclaw.json`. **Only use the minimal config shown below.** Do NOT pass properties like `dbPath`, `scriptPath`, or `timeoutMs` through openclaw.json. They cause schema validation errors. The plugin reads its own defaults from `OPENCLAW_WORKSPACE`.

Add to `plugins.entries` in `~/.openclaw/openclaw.json`:

```json
"graph-memory": {
  "enabled": true
}
```

Example using Python to safely edit the JSON:

```bash
python3 << 'PYEOF'
import json
config_path = "/home/openclaw/.openclaw/openclaw.json"
with open(config_path) as f:
    config = json.load(f)
config["plugins"]["entries"]["graph-memory"] = {"enabled": True}
with open(config_path, "w") as f:
    json.dump(config, f, indent=2)
print("graph-memory plugin added")
PYEOF
```

> **Warning:** Use a JSON editor or Python script to modify openclaw.json. Hand-editing large JSON files from the command line risks syntax errors that prevent OpenClaw from starting.

### Step 5: Restart and Verify

```bash
systemctl restart openclaw
sleep 3
journalctl -u openclaw --no-pager -n 30 | grep -i graph
```

**Success output:**

```
[plugins] graph-memory v2: armed (db=/home/openclaw/.openclaw/memory/facts.db, co-occurrences=0, cache=10)
[plugins] Graph Memory v2 plugin registered
```

### Common Failure Modes

| Log Message | Cause | Fix |
|-------------|-------|-----|
| `attempt to write a readonly database` | Files owned by root, not openclaw | `chown -R openclaw:openclaw` on memory/ and extensions/ |
| `armed WITHOUT activation` | Database not writable by the plugin process | Check ownership and file permissions (664 for .db files) |
| `invalid config: must NOT have additional properties` | Config properties passed through openclaw.json | Use only `{"enabled": true}` in plugins.entries |
| `facts.db not found` | OPENCLAW_WORKSPACE not set in service environment | Add to /opt/openclaw.env |
| Plugin registered but no search on messages | Scripts directory not accessible | Verify script paths and OPENCLAW_WORKSPACE |

---

## Understanding the Search Cascade

The `graph-search.py` script uses a 4-phase search strategy, returning the first high-confidence matches and falling back to broader searches only when needed.

| Phase | Method | Score | When It Fires |
|-------|--------|-------|---------------|
| 1 | Entity + Intent | 90-95 | User mentions a known entity AND query intent matches a fact key |
| 2 | Entity (all facts) | 65-70 | Entity found but no specific intent matched. Returns all facts. |
| 3 | FTS on facts | 50 | No entity resolved. Full-text search across all fact values. |
| 4 | FTS on relations | 40 | Still under top-k. Full-text search across relation triples. |

The plugin applies an additional filter: FTS-only results (score below 65) are discarded unless at least one entity match exists. This prevents noise injection from tangential keyword matches.

### Intent Patterns

Phase 1 matches query words against these intent patterns to find specific fact keys:

| Intent Key | Trigger Words |
|-----------|---------------|
| birthday | birthday, born, birth, birthdate |
| phone | phone, number, call, contact, reach |
| email | email, mail, address.*@, contact |
| address | address, live, lives, location, where does .* live |
| relationship | who is, relationship, partner, wife, husband |
| role | role, what does .* do, job |
| full_name | full name, real name, name |
| url | url, website, domain, site |
| stack | stack, tech, built with, uses, framework |
| runs_on | port, runs on, hosted, server |

> **Tip:** If you store facts with keys that don't match these patterns (e.g., `key='location'` instead of `key='address'`), Phase 1 won't fire for those facts. Phase 2 will still catch them. Consider aligning your fact keys with these patterns for optimal scoring.

---

## Seeding Facts

### Fact Schema

| Field | Type | Purpose |
|-------|------|---------|
| entity | Text | The person, system, or concept (e.g., "Adam", "Jarvis") |
| key | Text | The attribute name (e.g., "role", "location", "birthday") |
| value | Text | The fact content (e.g., "RMO at Computacenter") |
| category | Text | Grouping: identity, system, preference, relationship, work |
| importance | Float 0-1 | 0.9 = structural/permanent, 0.5 = moderate, 0.3 = contextual |
| source | Text | Where it came from: manual-seed, conversation, daily-ingest |

### Inserting Facts via SQL

The most reliable method. Works regardless of script version.

```bash
sqlite3 /home/openclaw/.openclaw/memory/facts.db << 'SQL'
INSERT INTO facts (entity, key, value, category, importance, source)
  VALUES ('Adam', 'role', 'RMO at Computacenter', 'identity', 0.9, 'manual-seed');
INSERT INTO facts (entity, key, value, category, importance, source)
  VALUES ('Adam', 'location', 'Dallas, Texas', 'identity', 0.8, 'manual-seed');
INSERT INTO facts (entity, key, value, category, importance, source)
  VALUES ('Jarvis', 'runs_on', 'DigitalOcean 4GB droplet', 'system', 0.8, 'manual-seed');
SQL
```

### Adding Relations

Relations store connections between entities as subject-predicate-object triples.

```bash
sqlite3 /home/openclaw/.openclaw/memory/facts.db << 'SQL'
INSERT INTO relations (subject, predicate, object, source)
  VALUES ('Adam', 'manages', 'Jarvis', 'manual-seed');
INSERT INTO relations (subject, predicate, object, source)
  VALUES ('Jarvis', 'runs_on', 'DigitalOcean', 'manual-seed');
SQL
```

### Adding Aliases

Aliases let the search resolve informal names to canonical entities.

```bash
sqlite3 /home/openclaw/.openclaw/memory/facts.db << 'SQL'
INSERT INTO aliases (alias, entity) VALUES ('the server', 'DigitalOcean');
INSERT INTO aliases (alias, entity) VALUES ('my agent', 'Jarvis');
SQL
```

### Verifying Seeded Data

```bash
# Count all facts
sqlite3 /home/openclaw/.openclaw/memory/facts.db "SELECT count(*) FROM facts;"

# List all entities
sqlite3 /home/openclaw/.openclaw/memory/facts.db "SELECT DISTINCT entity FROM facts;"

# View all facts for an entity
sqlite3 /home/openclaw/.openclaw/memory/facts.db "SELECT key, value FROM facts WHERE entity='Adam';"
```

---

## Troubleshooting

### Diagnostic Script

Run this to check the health of your installation:

```bash
echo "=== File ownership ==="
ls -la /home/openclaw/.openclaw/memory/
echo ""
echo "=== Scripts ownership ==="
ls -la /home/openclaw/.openclaw/scripts/
echo ""
echo "=== Extensions ownership ==="
ls -la /home/openclaw/.openclaw/extensions/graph-memory/ | head -5
echo ""
echo "=== Environment (service) ==="
grep OPENCLAW /opt/openclaw.env
echo ""
echo "=== Plugin config ==="
cat /home/openclaw/.openclaw/openclaw.json | python3 -c \
  "import sys,json; d=json.load(sys.stdin); print(json.dumps(d['plugins']['entries'].get('graph-memory',{}), indent=2))"
echo ""
echo "=== DB test (as openclaw user) ==="
su - openclaw -c "sqlite3 /home/openclaw/.openclaw/memory/facts.db 'SELECT count(*) FROM facts;'"
echo ""
echo "=== Script test (as openclaw user) ==="
su - openclaw -c "python3 /home/openclaw/.openclaw/scripts/graph-search.py 'TestEntity' --json 2>&1 | head -5"
```

### Plugin shows "armed WITHOUT activation"

The plugin loaded but cannot write to the database. Activation bumping and co-occurrence learning are disabled. Search still works (read-only), but Hebbian learning features don't.

**Fix:** Check file ownership. Everything under `.openclaw/memory/` must be owned by the openclaw user with write permissions.

### Scripts show "using legacy facts.db path"

The `OPENCLAW_WORKSPACE` or `FACTS_DB` environment variable isn't being picked up. The script falls back to CoolmannS's personal path which doesn't exist on your machine.

**Fix:** Verify the exports are in `/home/openclaw/.profile` (not `.bashrc`), and that `/opt/openclaw.env` contains `OPENCLAW_WORKSPACE`.

### Plugin loads but never fires during messages

Check the full logs (not just grep for "graph"). The plugin might be failing silently during the `before_agent_start` hook. Verify graph-search.py is executable and the Python path works inside the OpenClaw process context.

```bash
# Watch logs in real time while sending a test message
journalctl -u openclaw -f | grep -i graph
```

### graph-init.py crashes on fresh database

Older versions try to print statistics before creating tables. This has been fixed in recent versions. Workaround: apply the schema manually.

```bash
sqlite3 /path/to/facts.db < /path/to/facts.sql
```

### openclaw.json validation errors

OpenClaw validates plugin config against a schema. The graph-memory plugin's custom config properties (`dbPath`, `scriptPath`, `timeoutMs`, etc.) are not in the OpenClaw schema. Only pass `{"enabled": true}` through openclaw.json. The plugin reads its own defaults internally and resolves paths from `OPENCLAW_WORKSPACE`.

---

## Security Considerations

### Telemetry

The plugin writes query telemetry to `/tmp/openclaw/memory-telemetry.jsonl` by default. On shared systems, this is world-readable and may leak entity names from queries.

For production, create a secured telemetry directory:

```bash
mkdir -p /home/openclaw/.openclaw/telemetry
chown openclaw:openclaw /home/openclaw/.openclaw/telemetry
chmod 700 /home/openclaw/.openclaw/telemetry
```

### Database File Permissions

The facts.db file should not be world-readable if it contains sensitive personal information.

```bash
chmod 660 /home/openclaw/.openclaw/memory/facts.db
chown openclaw:openclaw /home/openclaw/.openclaw/memory/facts.db
```

### Credential Storage

The schema supports a "credential" category for facts. **Do not store plaintext passwords, API keys, or tokens in the facts table.** There is no encryption at rest. Database backups and log files would expose secrets. Use OpenClaw's built-in credential management or environment variables instead.

---

## File Reference

| Path | Purpose |
|------|---------|
| `/home/openclaw/.openclaw/memory/facts.db` | The knowledge graph database |
| `/home/openclaw/.openclaw/memory/facts.sql` | Schema definition (for fresh installs) |
| `/home/openclaw/.openclaw/scripts/graph-search.py` | 4-phase search cascade, called by the plugin |
| `/home/openclaw/.openclaw/scripts/query-facts.py` | CLI tool for querying facts directly |
| `/home/openclaw/.openclaw/scripts/seed-facts.py` | Template script for bulk fact insertion |
| `/home/openclaw/.openclaw/scripts/graph-init.py` | Schema initialization and stats |
| `/home/openclaw/.openclaw/scripts/fts_helper.py` | FTS5 query sanitization helper |
| `/home/openclaw/.openclaw/extensions/graph-memory/` | The auto-injection plugin |
| `/opt/openclaw.env` | Service environment variables |
| `/home/openclaw/.profile` | User shell environment (FACTS_DB, OPENCLAW_WORKSPACE) |
| `/home/openclaw/.openclaw/openclaw.json` | OpenClaw config (plugin registration) |

---

## Credits

Memory architecture designed and built by [CoolmannS](https://github.com/coolmanns/openclaw-memory-architecture).

Security audit, bug fixes, and this deployment guide by [agambletx-afk](https://github.com/agambletx-afk/openclaw-memory-architecture) based on a production deployment.
