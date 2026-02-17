# Changelog

## v3.0 — 2026-02-17

### Added
- **Layer 9: Continuity Plugin** — runtime cross-session conversation memory via `openclaw-plugin-continuity`
  - Conversation archive with SQLite + SQLite-vec embeddings (384d, all-MiniLM-L6-v2)
  - Topic tracking with fixation detection (configurable thresholds)
  - Continuity anchors preserving identity moments and contradictions through compaction
  - Context budgeting with priority-tiered token allocation (essential/high/medium/low/minimal pools)
  - Cross-session semantic search ("what did we discuss last week?")
  - `[CONTINUITY CONTEXT]` injected into every prompt with session stats and active topics
- **Layer 10: Stability Plugin** — runtime behavioral monitoring via `openclaw-plugin-stability`
  - Entropy monitoring (0.0 stable → 1.0+ drift) with configurable warning/critical thresholds
  - Principle alignment tracking from each agent's SOUL.md `## Core Principles` section
  - Loop detection — tool loops (5+ consecutive) and file re-reads (3+ same file)
  - Heartbeat decision framework with structured logging
  - Confabulation detection (temporal mismatches, quality decay, recursive meta-reasoning)
  - `[STABILITY CONTEXT]` injected into every prompt with entropy score and principle alignment
- **Plugin installation guide** in README
- **Runtime vs boot-time distinction** — plugins operate during conversations, file layers at boot

### Changed
- Architecture diagram updated with plugin layers below the file-based stack
- Agent count updated: 11 → 14 agents in production
- Credits updated with CoderofTheWest plugin attributions
- ARCHITECTURE.md expanded with Layer 9 and Layer 10 documentation

## v2.1 — 2026-02-16

### Added
- **Importance tagging for daily logs** — tiered retention system with five tag types (`decision`, `milestone`, `lesson`, `task`, `context`) and importance scores controlling auto-pruning
- **Auto-pruning script** — `scripts/prune-memory.py` enforces retention tiers (STRUCTURAL permanent, POTENTIAL 30d, CONTEXTUAL 7d) with `--dry-run` support
- **SLEEP session lifecycle** — the other half of Wake/Sleep: active-context update, tagged observations, MEMORY.md distillation before session end or compaction
- **Memory maintenance via heartbeats** — periodic consolidation: review daily files, update MEMORY.md, prune stale info, cross-check USER.md for missed personal details
- **USER.md maintenance pattern** — explicit guidance on keeping your human's profile current
- **5 battle-tested gating policies** (GP-008 through GP-012):
  - GP-008: Full-array replacement for config.patch (partial patch destroys lists)
  - GP-009: Read active-context.md after model/session switch
  - GP-010: Update USER.md immediately when learning about your human
  - GP-011: Re-embed entire index after embedding model changes
  - GP-012: Run writing quality pipeline before publishing

### Changed
- `README.md` — Layer 4 (Daily Logs) expanded with importance tagging reference, retention tiers, and auto-pruning docs; Session Boot Sequence now includes SLEEP lifecycle
- `templates/agents-memory-section.md` — renamed "Boot Sequence" to "Wake/Sleep Pattern", added SLEEP phase with importance tags, added Memory Maintenance section, added USER.md section
- `templates/gating-policies.md` — 5 new real-world policies from production failures

## v2.0 — 2026-02-15

### Added
- **Layer 2.5: Project Memory** — per-project institutional knowledge files (`memory/project-{slug}.md`)
  - Agent-independent: survives resets, compaction, session purges
  - Created by Project Setup Wizard, read by all project agents at boot, updated by PM at phase close
  - Template: `templates/project-memory.md`
- **Hardware documentation** — full specs for our reference deployment (AMD Ryzen AI MAX+ 395, 96GB unified VRAM)
- **AMD ROCm docker-compose** — complete Ollama GPU setup with device passthrough, group IDs, environment flags
- **Embedding model pinning** — how to keep nomic-embed-text permanently in VRAM with `keep_alive: -1`
- **Cross-agent flow diagrams** — how knowledge flows from wizard → agents → phase close → next boot
- **Split boot sequences** — separate docs for main agent vs project agents

### Changed
- `docs/ARCHITECTURE.md` — major expansion (102 → 475 lines)
- `docs/embedding-setup.md` — added ROCm docker-compose section with all flags documented
- Diagram updated with project memory layer between strategic memory and structured facts

## v1.1 — 2026-02-14

### Added
- Semantic code search layer via grepai integration
- `docs/code-search.md` — setup and usage guide

## v1.0 — 2026-02-14

### Added
- Initial release: 8-layer memory architecture
- `docs/ARCHITECTURE.md` — full architecture documentation
- `docs/embedding-setup.md` — Ollama, QMD, and OpenAI embedding options
- `schema/facts.sql` — SQLite + FTS5 schema for structured facts
- `scripts/init-facts-db.py`, `seed-facts.py`, `query-facts.py`
- `templates/` — active-context.md, gating-policies.md, agents-memory-section.md
