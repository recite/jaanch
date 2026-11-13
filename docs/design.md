# Design

## What Refine does, and where each piece lives here

Sources: refine.ink's features, FAQ and benchmark pages, and its public
OpenAPI schema (`api.refine.ink/openapi.json`), read 2026-11-09. Refine's
internals are not public. The mapping of its comment types to internal workers
is our inference from that schema.

| Refine feature | Refine comment type | jaanch subagent |
|---|---|---|
| Substance and logic: arguments, derivations, proofs | `general` (segment level) | `jaanch_check_reasoning`, one per section, in parallel |
| Text, tables and figures agree | `general` | `jaanch_check_consistency` |
| (a weak spot: Refine caught 5 of 24 planted omissions in the Dawes benchmark) | none | `jaanch_check_completeness` |
| Reference checking (beta): cited works exist and say what is claimed | `external_references` | `jaanch_check_references` |
| Missing literature (beta) | `prior_art` | `jaanch_check_prior_art` |
| Writing feedback (beta) | `writing` | `jaanch_check_writing` |
| Hundreds of checks that cross-examine each other | `skeptic` | `jaanch_verify_finding`, one per batch of up to five candidates, in parallel |
| Overall feedback: the few decisive issues | `broad` | `jaanch_write_review` |
| Revision check: were earlier comments addressed? | verdicts | `jaanch_check_revision` |
| Severity, category and fix-effort tags | `severity`, `kind`, `fix_effort` | same vocabulary, in `src/jaanch/review.schema.json` |
| Chat about a finding | chat | the host CLI |

## Prior art and what we take from it

| project | what it is | what we use |
|---|---|---|
| [Refine](https://refine.ink) | closed source, about $40–50 a review | the comment vocabulary and the single-review baseline design |
| [coarse](https://github.com/davidvandijcke/coarse) | MIT license, Python; calls `claude -p` or `codex exec` as a plain model | its pipeline order (structure → overview → parallel section agents → proof checks → editorial dedupe → quote verification); a second baseline |
| [Nguyen et al. 2026](https://arxiv.org/abs/2606.19749) | an independent benchmark of review agents using injected errors | the seeded-error method behind test set S |
| [retract](https://github.com/recite/retract) | ours | retraction checks in `jaanch_check_references` |

**Why not use coarse as it is.** coarse runs the pipeline from Python and uses
the host CLI only as a text-in, text-out model. Each call loses the host's
tools: web search for reference checks, code execution to recompute a
percentage from a table, file reads, and native parallel subagents. jaanch
inverts this. The host runs the pipeline, and Python does only the
deterministic parts (validating, anchoring quotes, rendering). If coarse
scores as well as jaanch on S and D, that argument fails and we should use
coarse.

## Pipeline

```
paper (.md/.tex/.txt; PDF via ingest)
  │
  ├─ jaanch_map_paper ─────────────► map.json: sections, main claims, numbers, references
  │
  ├─ fan out, in parallel ──► candidates/<goal>[_<section>].jsonl
  │    jaanch_check_reasoning × each section
  │    jaanch_check_consistency
  │    jaanch_check_completeness
  │    jaanch_check_references
  │    jaanch_check_prior_art
  │    jaanch_check_writing
  │
  ├─ jaanch merge                 (drops comments whose quote is not in the paper)
  │
  ├─ jaanch_verify_finding × each batch of ≤5, in parallel ─► verdicts.jsonl
  │
  ├─ jaanch_write_review ─────────────► review.json: dedupe, rank, tag, overall feedback
  │
  └─ jaanch check review.json, then jaanch render → review.md
```

Each run writes to `reviews/<paper_slug>/`. That folder is gitignored because
papers are usually unpublished.

## One source of truth for two hosts

Codex and Claude Code read the same skill format (the agentskills.io
standard), but from different folders, and they define subagents in different
formats. So:

- the orchestrating skill lives at `.agents/skills/jaanch-review/` (Codex), and
  `.claude/skills/jaanch-review` is a symlink to it;
- each subagent's instructions live once, in `agents/<name>.md`, and
  `make agents` renders them to `.claude/agents/<name>.md` and
  `.codex/agents/<name>.toml`. A test fails if the rendered files are stale.

`make install` links the skills and agents into `~/.claude` and `~/.codex`, so either CLI can run jaanch from any directory.

Agents do not set a model. Each one inherits the session's model, so the
same definitions run on whatever Claude or Codex model you start with.

## Open decisions

- **PDF ingest.** The quote check needs text. The candidates are docling (MIT,
  local, heavy install), marker (restrictive model license) and Mistral OCR
  (paid, what coarse uses). Recommended: docling as an optional extra. Until
  ingest exists, give jaanch `.tex`, `.md` or text.
- **Network access in Codex.** `jaanch_check_references` and `jaanch_check_prior_art` need
  the web. Codex's sandbox may block network access; then those two goals run
  only under Claude Code, or with network access turned on.
