/**
 * openclaw-plugin-graph-memory — Knowledge Graph Memory Search
 *
 * Augments OpenClaw's memory pipeline with knowledge graph lookups.
 * Runs graph-search.py against the user's message and injects
 * matching entities/facts/relations via prependContext.
 *
 * Hook: before_agent_start (priority 5 — runs before continuity plugin)
 *
 * Flow:
 * 1. Extract user's last message
 * 2. Spawn graph-search.py with the query
 * 3. Parse JSON results
 * 4. Format as prependContext block
 */

const { execFile } = require('child_process');
const path = require('path');
const fs = require('fs');

// ---------------------------------------------------------------------------
// Defaults
// ---------------------------------------------------------------------------

const DEFAULTS = {
    enabled: true,
    maxResults: 6,
    minScore: 50,
    timeoutMs: 2000,
};

// ---------------------------------------------------------------------------
// Plugin export
// ---------------------------------------------------------------------------

module.exports = {
    id: 'graph-memory',
    name: 'Knowledge Graph Memory Search',

    register(api) {
        const userConfig = api.pluginConfig || {};
        const config = { ...DEFAULTS, ...userConfig };

        if (!config.enabled) {
            api.logger?.info?.('graph-memory: disabled by config');
            return;
        }

        // Resolve paths
        const workspaceDir = process.env.OPENCLAW_WORKSPACE
            || process.env.MOLTBOT_WORKSPACE
            || path.join(process.env.HOME || '/home/user', 'clawd');

        const dbPath = config.dbPath || path.join(workspaceDir, 'memory', 'facts.db');
        const scriptPath = config.scriptPath || path.join(workspaceDir, 'scripts', 'graph-search.py');

        // Verify files exist at startup
        if (!fs.existsSync(dbPath)) {
            api.logger?.warn?.(`graph-memory: facts.db not found at ${dbPath}`);
            return;
        }
        if (!fs.existsSync(scriptPath)) {
            api.logger?.warn?.(`graph-memory: graph-search.py not found at ${scriptPath}`);
            return;
        }

        api.logger?.info?.(`graph-memory: armed (db=${dbPath}, minScore=${config.minScore})`);
        console.log('[plugins] Graph Memory plugin registered — knowledge graph search active');

        // -------------------------------------------------------------------
        // HOOK: before_agent_start — Inject graph search results
        // Priority 5 (runs before continuity plugin at 10)
        // -------------------------------------------------------------------

        api.on('before_agent_start', async (event, ctx) => {
            try {
                // Extract last user message
                const messages = event.messages || [];
                const lastUser = [...messages].reverse().find(m => m?.role === 'user');
                if (!lastUser) return { prependContext: '' };

                const userText = _extractText(lastUser);
                if (!userText || userText.length < 5) return { prependContext: '' };

                // Strip context injection blocks from user text to get the real query
                const cleanText = _stripContextBlocks(userText).trim();
                if (!cleanText || cleanText.length < 5) return { prependContext: '' };

                // Run graph search
                const results = await _runGraphSearch(scriptPath, cleanText, config);

                if (!results || results.length === 0) {
                    return { prependContext: '' };
                }

                // Filter: entity-matched results (score >= 65) always pass;
                // FTS-only results (score < 65) only pass if score >= minScore AND
                // there's at least one entity-matched result (validates relevance)
                const entityMatched = results.filter(r => r.score >= 65);
                const ftsOnly = results.filter(r => r.score < 65 && r.score >= config.minScore);
                const filtered = entityMatched.length > 0
                    ? [...entityMatched, ...ftsOnly]
                    : []; // No entity match = query doesn't hit the graph, skip entirely
                if (filtered.length === 0) {
                    return { prependContext: '' };
                }

                // Format as context block
                const lines = ['[GRAPH MEMORY]'];
                const topResults = filtered.slice(0, config.maxResults);

                // Group by entity for cleaner presentation
                const byEntity = new Map();
                for (const r of topResults) {
                    const entity = r.entity || 'unknown';
                    if (!byEntity.has(entity)) byEntity.set(entity, []);
                    byEntity.get(entity).push(r);
                }

                for (const [entity, facts] of byEntity) {
                    // Deduplicate answers
                    const seen = new Set();
                    const uniqueFacts = facts.filter(f => {
                        if (seen.has(f.answer)) return false;
                        seen.add(f.answer);
                        return true;
                    });

                    for (const f of uniqueFacts) {
                        lines.push(`• ${f.answer}`);
                    }
                }

                return { prependContext: lines.join('\n') };

            } catch (err) {
                console.error(`[graph-memory] before_agent_start failed: ${err.message}`);
                return { prependContext: '' };
            }
        }, { priority: 5 });
    },
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function _extractText(message) {
    if (!message) return '';
    if (typeof message.content === 'string') return message.content;
    if (Array.isArray(message.content)) {
        return message.content
            .filter(p => p.type === 'text')
            .map(p => p.text || '')
            .join(' ');
    }
    return '';
}

function _stripContextBlocks(text) {
    // Remove [CONTINUITY CONTEXT], [STABILITY CONTEXT], [GRAPH MEMORY], etc.
    return text
        .replace(/\[CONTINUITY CONTEXT\][\s\S]*?(?=\n\n|\n[A-Z]|$)/g, '')
        .replace(/\[STABILITY CONTEXT\][\s\S]*?(?=\n\n|\n[A-Z]|$)/g, '')
        .replace(/\[GRAPH MEMORY\][\s\S]*?(?=\n\n|\n[A-Z]|$)/g, '')
        .replace(/Conversation info \(untrusted metadata\):[\s\S]*?```\n/g, '')
        .replace(/Replied message \(untrusted[\s\S]*?```\n/g, '')
        .replace(/System:.*?\n/g, '')
        .trim();
}

function _runGraphSearch(scriptPath, query, config) {
    return new Promise((resolve, reject) => {
        const timeout = config.timeoutMs || 2000;

        const child = execFile(
            'python3',
            [scriptPath, query, '--json', '--top-k', String(config.maxResults || 6)],
            {
                timeout,
                maxBuffer: 1024 * 64,
                env: { ...process.env },
            },
            (error, stdout, stderr) => {
                if (error) {
                    if (error.killed) {
                        console.error(`[graph-memory] search timed out after ${timeout}ms`);
                        resolve([]);
                        return;
                    }
                    console.error(`[graph-memory] search error: ${error.message}`);
                    resolve([]);
                    return;
                }

                try {
                    const results = JSON.parse(stdout.trim());
                    resolve(Array.isArray(results) ? results : []);
                } catch (parseErr) {
                    console.error(`[graph-memory] JSON parse error: ${parseErr.message}`);
                    resolve([]);
                }
            }
        );
    });
}
