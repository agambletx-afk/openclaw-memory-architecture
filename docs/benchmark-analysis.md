# Memory Search Benchmark — First Run Analysis
> Date: 2026-02-18 | Method: QMD BM25 | Queries: 60 | Top-K: 6

## Results Summary

| Category | Score | Pct |
|----------|-------|-----|
| FACTS | 9/10 | 90% |
| PEOPLE | 6/10 | 60% |
| DAILY | 3/5 | 60% |
| IDENTITY | 3/5 | 60% |
| OPERATIONAL | 4/10 | 40% |
| TOOLS | 2/10 | 20% |
| PROJECTS | 1/10 | 10% |
| **TOTAL** | **28/60** | **46.7%** |

## Root Causes

### 1. QMD BM25 returns too few results for generic queries
Most memory-dir files (tools-*, project-*) never surface because BM25 needs exact keyword overlap.
Queries like "Postiz URL" don't match because tools-infrastructure.md uses different phrasing.

### 2. Root file keyword fallback is too aggressive
The benchmark's fallback scans SOUL.md, USER.md, AGENTS.md for keyword matches.
These large files match *everything* loosely, crowding out the correct specialized files.

### 3. Vector search (vsearch) too slow for benchmarking
embeddinggemma-300M loads per query. ~7s/query = 7 min for 60 queries.
Not practical for rapid iteration.

### 4. family-contacts.md invisible to many queries
Despite having phone numbers, addresses, birthdays — BM25 can't match
"Mama's phone number" to the file because "Mama" doesn't appear as a keyword
(file uses "Heidi Karin Kuhlmann-Becker").

## Improvement Plan (ordered by expected impact)

### A. Add keyword headers to specialized files (+15-20 points estimated)
Each memory file should have a YAML frontmatter or keyword header line:
```
<!-- keywords: postiz, social media, scheduler, posting, queue -->
```
This gives BM25 something to match on for generic queries.

### B. Split multi-topic files (+5-10 points)
- `tools-infrastructure.md` → separate files for komodo, ghost, goplaces, khal, remarkable
- `tools-social-media.md` → separate files per platform

### C. Add aliases/synonyms to people files (+3-5 points)
family-contacts.md needs:
- "Mama" alias for Heidi
- "JoJo" alias for Johanna
- Common query patterns: "phone", "address", "birthday" in section headers

### D. Fix benchmark search method
Current QMD BM25 + root-file keyword fallback doesn't match how OpenClaw actually searches.
Need to test with OpenClaw's actual search pipeline (QMD BM25 + vector + RRF fusion).

### E. Consider nomic-embed-text for vsearch
embeddinggemma-300M (256d) is the weakest embedding. nomic-embed-text (768d) scored
same as OpenAI in the Reddit post. Would need to patch QMD or run Ollama embeddings separately.

## Reference
- Inspired by: https://old.reddit.com/r/openclaw/comments/1r7nd4y/
- Their baseline: 34/50 (68%) → optimized to 41/50 (82%)
- Our baseline: 28/60 (46.7%) — lower but harder benchmark (more categories, more generic queries)
- Their key insight: "memory is a content problem, not a technology problem" — confirmed by our data
