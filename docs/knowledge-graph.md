# Knowledge Graph Layer

> Lightweight entity-relationship graph built on SQLite. Zero API cost, sub-millisecond lookups, 100% recall on structured queries.

## The Problem

BM25 and vector search work for fuzzy recall — *"what were we discussing about infrastructure?"* — but fail spectacularly for entity-relationship queries:

- "What port does Keystone run on?" → BM25 can't match "port" to the right file
- "Mama's phone number" → Vector search returns USER.md (wrong), not family-contacts.md (right)
- "What does Sascha own?" → No single file answers this; it's scattered across 5 project files

These are **graph queries**, not search queries. The answer lives in relationships between entities, not keywords in documents.

## The Evidence: Benchmark Results

We built a 60-query benchmark across 7 categories and measured recall (correct file in top-6 results):

| Method | Score | Notes |
|--------|-------|-------|
| QMD BM25 only | 28/60 (46.7%) | Baseline — keyword search |
| Graph only | 33/60 (55.0%) | Entity resolution + facts |
| Hybrid v1 (graph + BM25) | 40/60 (66.7%) | Combined search |
| + entity fixes | 43/60 (71.7%) | More entities seeded |
| + doc entities + alias tuning | 54/60 (90.0%) | Documents modeled as entities |
| + event entities + edge cases | **60/60 (100%)** | Temporal events as entities |

**Key finding:** PROJECTS category went from **10% → 100%** with the graph layer. PEOPLE went from **60% → 100%**. These are the categories where real data lives.

**Key insight from a parallel community effort** ([r/openclaw post](https://old.reddit.com/r/openclaw/comments/1r7nd4y/)): *"Memory is a content problem, not a technology problem."* Better embeddings didn't help. Better content structure did. Our graph layer proves this at a deeper level — structure your data as entities and relationships, not just better-organized files.

## Architecture

Three tables extend the existing `facts.db`:

```
┌─────────────┐     ┌──────────────┐     ┌──────────────┐
│   facts     │     │  relations   │     │   aliases    │
│  (existing) │     │  (new)       │     │   (new)      │
├─────────────┤     ├──────────────┤     ├──────────────┤
│ entity      │◄────│ subject      │     │ alias        │
│ key         │     │ predicate    │     │ entity       │
│ value       │     │ object   ────│──►  │              │
│ category    │     │ weight       │     │ COLLATE      │
│ source      │     │ source       │     │ NOCASE       │
│ (FTS5)      │     │ (FTS5)       │     │              │
└─────────────┘     └──────────────┘     └──────────────┘
```

### Tables

**`relations`** — Subject-predicate-object triples:
```sql
CREATE TABLE relations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subject TEXT NOT NULL,        -- "Janna"
    predicate TEXT NOT NULL,      -- "partner_of"
    object TEXT NOT NULL,         -- "Sascha"
    weight REAL DEFAULT 1.0,
    source TEXT,                  -- "USER.md"
    created_at TEXT DEFAULT (datetime('now')),
    UNIQUE(subject, predicate, object)
);
```

**`aliases`** — Fuzzy entity resolution:
```sql
CREATE TABLE aliases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    alias TEXT NOT NULL COLLATE NOCASE,  -- "Mama", "Heidi", "Mom"
    entity TEXT NOT NULL,                 -- "Mama" (canonical)
    UNIQUE(alias, entity)
);
```

Both tables have FTS5 virtual tables for full-text search.

## Search Pipeline

The graph search runs a 4-phase pipeline, highest confidence first:

```
Query: "What port does Keystone run on?"
  │
  ├─ Phase 1: Entity + Intent (score: 95)
  │   Extract candidates: ["Keystone"]
  │   Resolve alias: "Keystone" → "Project Keystone"
  │   Extract intent: "runs_on" (from "port" keyword)
  │   Match: relations WHERE subject="Project Keystone" AND predicate="runs_on"
  │   → Project Keystone → runs_on → port 3055 (source: project-keystone.md) ✅
  │
  ├─ Phase 2: All entity facts (score: 70)
  │   Fallback: return all facts for resolved entity
  │
  ├─ Phase 3: FTS on facts (score: 50)
  │   When no entity resolves, search facts_fts
  │
  └─ Phase 4: FTS on relations (score: 40)
      Search relations_fts for keyword matches
```

### Entity Extraction

Candidates are extracted from queries via:
1. **Capitalized words** — "Keystone", "Janna", "ClawSmith"
2. **Multi-word combos** — "Home Assistant", "Dan Verakis"
3. **Possessives** — "Janna's" → "Janna"
4. **Self-reference** — "Who am I?" → agent identity entity
5. **Alias DB scan** — multi-word aliases matched as phrases, single-word aliases on word boundaries

### Intent Extraction

Query keywords map to fact keys:
- "birthday", "born" → `birthday`
- "phone", "number", "call" → `phone`
- "port", "runs on" → `runs_on`
- "stack", "tech", "uses" → `stack`
- And 8 more patterns

## Entity Types

The graph models 5 categories of entities:

### People
Entities with `category=person`. Facts: birthday, full_name, relationship, phone, email, address, birthplace.
Relations: `partner_of`, `parent_of`, `child_of`, `sibling_of`, `friend_of`, `pet_of`, `married_to`.

### Projects
Entities with `category=project`. Facts: type, stack, status, url, server, github.
Relations: `owns` (person → project), `uses` (project → technology), `runs_on` (project → port/server), `hosted_on`, `domain`.

### Infrastructure
Entities with `category=infrastructure`. Facts: fqdn, hardware, services, systemd config.
Relations: `hosts` (server → service), `runs_on` (service → port), `configured_via`.

### Documents
Entities with `category=document`. Model procedural docs as entities when they're the *answer* to a query.
Facts: type, file, purpose, includes, checks, schedule.
Relations: `prevents`, `covers`, `described_in`.

### Events
Entities with `category=event`. Model significant incidents for temporal queries.
Facts: type, fix, details, reason.
Aliases map natural language to event entities: "OOM crash" → "OOM Crash Feb 17".

## Setup

### 1. Run graph-init.py

```bash
python3 scripts/graph-init.py
```

This creates the `relations`, `aliases`, and `relations_fts` tables in your existing `facts.db`, then seeds with your entities. Edit the seed data in `graph-init.py` to match your setup.

### 2. Run graph-export.py (for visualization)

```bash
python3 scripts/graph-export.py
# → memory/graph-data.json
```

### 3. Open the viewer

Serve `memory/graph-viewer.html` + `memory/graph-data.json` via any static server:

```bash
cd memory && python3 -m http.server 8099
# → http://localhost:8099/graph-viewer.html
```

Features: force-directed layout, hover tooltips with facts + relations, click-to-highlight connections, category filters, search.

## Maintaining the Graph

### Adding entities

```python
import sqlite3
db = sqlite3.connect('memory/facts.db')

# Add facts
db.execute('INSERT OR IGNORE INTO facts (entity, key, value, category, source) VALUES (?,?,?,?,?)',
    ('New Project', 'stack', 'React, Supabase', 'project', 'project-new.md'))

# Add aliases
db.execute('INSERT OR IGNORE INTO aliases (alias, entity) VALUES (?,?)',
    ('new project', 'New Project'))

# Add relations
db.execute('INSERT OR IGNORE INTO relations (subject, predicate, object, source) VALUES (?,?,?,?)',
    ('Sascha', 'owns', 'New Project', 'project-new.md'))

db.commit()
# Rebuild FTS
db.execute("INSERT INTO facts_fts(facts_fts) VALUES('rebuild')")
db.commit()
```

### When to add what

| You learn... | Add to... |
|-------------|-----------|
| New person (name, birthday, contact) | `facts` + `aliases` + family `relations` |
| New project | `facts` (type, stack, url) + `relations` (owns, uses, runs_on) |
| New tool/service | `facts` (infrastructure) + `relations` (hosts, runs_on) |
| Major incident | `facts` (event) + `aliases` (natural language triggers) |
| New procedural doc | `facts` (document) + `aliases` |

### Graph hygiene

Run `scripts/graph-export.py` after changes to regenerate the visualization data. The benchmark (`scripts/memory-benchmark.py`) can verify that new entities are findable.

## Benchmark

60 queries across 7 categories. Each query has an expected file. A query passes if the expected file appears in the top-6 results.

```bash
# Run all queries
python3 scripts/memory-benchmark.py --method hybrid

# Run one category
python3 scripts/memory-benchmark.py --method hybrid --category PROJECTS

# Verbose (show per-query results)
python3 scripts/memory-benchmark.py --method hybrid --verbose

# Save results to JSON
python3 scripts/memory-benchmark.py --method hybrid --output results.json
```

### Categories

| Category | Queries | Tests |
|----------|---------|-------|
| PEOPLE | 10 | Birthdays, phones, addresses, relationships |
| TOOLS | 10 | API tokens, URLs, ports, workflows |
| PROJECTS | 10 | Tech stacks, status, features, ports |
| FACTS | 10 | Personal info, preferences, certifications |
| OPERATIONAL | 10 | Gating policies, cron, heartbeat, architecture |
| IDENTITY | 5 | Self-awareness, principles, name |
| DAILY | 5 | Recent events, incidents, milestones |

### Methods

| Method | Description | Speed |
|--------|-------------|-------|
| `qmd` | QMD BM25 + root file keyword fallback | ~10s |
| `vsearch` | QMD vector search (slow, loads model per query) | ~7min |
| `graph` | Graph search only (facts.db + relations + aliases) | ~2s |
| `hybrid` | Graph + QMD BM25 combined (recommended) | ~15s |

## What the Graph Can't Do

- **Fuzzy semantic recall** — "What were we talking about re: infrastructure?" needs embeddings, not graph lookups.
- **Temporal reasoning** — "What happened last Tuesday?" requires date-aware search. Event entities are a workaround, not a real solution.
- **Discovery** — The graph only finds what's been explicitly modeled. Unknown entities return nothing. Semantic search can discover related content the graph doesn't know about.

That's why **hybrid** (graph + BM25/vector) is the recommended approach. Graph for precision, search for discovery.
