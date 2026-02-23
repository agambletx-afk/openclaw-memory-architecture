# Graph Memory Plugin Installation (OpenClaw One-Click Droplet)

This guide documents the proven installation flow for adding the graph-memory plugin to a standard OpenClaw one-click droplet.

## 1) Prerequisites

Install required system packages:

```bash
sudo apt update
sudo apt install -y build-essential sqlite3
```

## 2) Recommended directory structure

Use the OpenClaw workspace as the base and keep memory artifacts together:

```text
$OPENCLAW_WORKSPACE/
├── memory/
│   └── facts.db
├── scripts/
│   ├── graph-init.py
│   ├── graph-search.py
│   ├── query-facts.py
│   └── seed-facts.py
└── extensions/
    └── graph-memory/   (plugin extension)
```

If your deployment uses `.openclaw` directly, mirror the same layout under that directory.

## 3) Initialize schema

Run schema/bootstrap setup against the target database:

```bash
python3 graph-init.py --db-path /path/to/facts.db
```

If you are on an older `graph-init.py` that still fails on fresh databases, apply the schema manually:

```bash
sqlite3 /path/to/facts.db < facts.sql
```

## 4) Ownership and permissions

Everything under `.openclaw` must be owned by the `openclaw` user (not `root`).

If files are created as root, the plugin can fail with:

```text
attempt to write a readonly database
```

Fix ownership:

```bash
sudo chown -R openclaw:openclaw /home/openclaw/.openclaw
```

(Adjust path if your OpenClaw home differs.)

## 5) Required environment variables

Set both variables in **both** runtime and interactive-shell contexts:

- `/opt/openclaw.env` (service environment)
- `/home/openclaw/.profile` (CLI sessions)

Required values:

```bash
export OPENCLAW_WORKSPACE=/home/openclaw/.openclaw
export FACTS_DB=/home/openclaw/.openclaw/memory/facts.db
```

After editing service env, restart OpenClaw service.

## 6) Plugin registration in `openclaw.json`

Under `plugins.entries`, register the plugin with only:

```json
{"enabled": true}
```

Do **not** pass custom config like `dbPath` or `scriptPath` through `openclaw.json`; those cause schema validation errors. The plugin resolves its defaults from `OPENCLAW_WORKSPACE`.

## 7) Telemetry path hardening

By default, plugin telemetry may write under `/tmp/openclaw/`, which is world-readable on many systems.

For production, override telemetry output to a private directory owned by `openclaw` (for example under `.openclaw/logs`), and ensure directory mode is restrictive (such as `750` or tighter, depending on your ops policy).
