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
| [Chau and Little 2026](https://osf.io/preprints/socarxiv/zk26u_v1) (AMICUS) | method-specific and universal checklists built from the methods literature, applied by a model to 798 political science preprints; the checklists are announced but not yet public | fixed design checklists for `jaanch_check_completeness`, routing a paper to them, the per-check fields (applies to, pass if, flag if, if silent, severity, sources) and a per-paper importance rating of each flag. Their finding behind this: a review by the same model without a checklist misses issues the checklists catch |
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
  ├─ jaanch start <folder|file>  ──► inventory.json: what inputs exist (docs/intake.md)
  │
  ├─ jaanch_map_paper ─────────────► map.json, the paper model: claims and estimands, designs,
  │                                   data sources and their features, measures, sections,
  │                                   numbers, exhibits, references
  ├─ jaanch check-map             (quotes anchored, sections cover every line, every claim's
  │                                 outcome and causal treatment has a measure)
  │
  ├─ fan out, in parallel ──► candidates/<goal>[_<section>].jsonl
  │    jaanch_check_reasoning × each section
  │    jaanch_check_consistency
  │    jaanch_check_completeness
  │    jaanch_check_xref ──► jaanch xref (groups facts by key; judged only where they disagree)
  │    jaanch_extract_numbers ──► jaanch exact (statcheck, GRIM/GRIMMER/DEBIT, table cells,
  │                                 sums, rates by group, design analysis)
  │    jaanch forensics (with deposited data: duplicate and near-duplicate records,
  │                       last digits)
  │    jaanch_check_references
  │    jaanch_check_prior_art
  │    jaanch_check_writing
  │
  ├─ jaanch coverage              (every routed check has a verdict in checklists.jsonl;
  │                                 every major or minor flag has a comment)
  │
  ├─ jaanch merge                 (drops comments whose quote is not in the paper)
  │
  ├─ jaanch controls make        (mixes known-wrong comments into each skeptic batch)
  ├─ jaanch_verify_finding × each batch of ≤5, in parallel ─► verdicts.jsonl
  │
  ├─ jaanch_write_review ─────────────► review.json: dedupe, rank, tag, overall feedback
  │
  └─ jaanch check review.json, then jaanch render → review.md
```

Each run writes to `reviews/<paper_slug>/`. That folder is gitignored because
papers are usually unpublished.

## Pillars, mechanisms and modules

Every check in `src/jaanch/checks/register.jsonl` protects one **pillar**,
what a paper must get right, and uses one **mechanism**, how a problem is
caught. `jaanch checks grid` prints the pillar × mechanism table, and
`jaanch checks page` renders it with the register as an HTML atlas.

| pillar | question | foundation |
|---|---|---|
| record | is what is reported what was done? | reproducibility; statcheck, GRIM |
| construct | do the measures capture the constructs the claims name? | Cronbach and Meehl (1955) |
| internal | does the design identify the causal claim: estimand, assumptions, evidence? | Rubin; Holland; Shadish, Cook and Campbell (2002) |
| statistical | is the uncertainty right? | Shadish, Cook and Campbell (2002) |
| external | does it carry to the units, treatments, outcomes and settings claimed? | Cronbach (1982) |
| claim_fit | do the conclusions follow, at the strength stated? | Meehl |
| contribution | is it new, and does it matter? | the literature map |

Presentation and process are tracked too, outside the pillars. The
mechanisms are `exact` (arithmetic on reported numbers), `cross_reference`
(the paper against itself), `checklist` (against a citable convention),
`retrieval` (against outside records), `rerun` (code on data) and
`judgment` (a model's reading, always verified).

**Modules** in `src/jaanch/checklists/` say what using a design, or a kind of
data, commits a paper to. Design modules (experiment, did, latent
comparison, proof) route on `designs`. Data modules route on how the data
were made, because one defect lands on several pillars: a linkage error
changes N (record), attenuates (construct), differs by arm (internal) and
invalidates p-values computed as if links were true (statistical). So
each data-module item states the defect, its `consequence` for the
estimate, and the `tools` that test it when code and data are present:

| module | routed by | tools |
|---|---|---|
| `measurement` | a measure that is a scale, an index, a self-report or human-coded | |
| `linked_data` | a data source or measure built by record linkage | preclink, causal_linkage, `jaanch exact` rates |
| `predicted_data` | a variable that is a model's or classifier's output | total_error |
| `survey_data` | survey weights, a complex sample, or interviewers | studyframe, interviewer-checks |

Running those tools on a replication package is not built yet; today the
items are judged from the paper, and match rates by arm are tested by
`jaanch exact`. Every item cites its sources by key in
`src/jaanch/checks/sources.bib`, added with `jaanch sources add`.

## One source of truth for two hosts

Codex and Claude Code read the same skill format (the agentskills.io
standard), but from different folders, and they define subagents in different
formats. So:

- the orchestrating skill lives at `.agents/skills/jaanch-review/` (Codex), and
  `.claude/skills/jaanch-review` is a symlink to it;
- each subagent's instructions live once, in `agents/roles/<name>.md`, and
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
