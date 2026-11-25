---
name: jaanch-review
description: Review a draft paper or submission folder for the errors an expert referee would catch, with parallel subagents and a skeptic pass. Not for re-checking a revision (use jaanch-recheck).
---

# Review a paper with jaanch

You orchestrate. Subagents do the reading. Keep the paper's text out of your
own context as far as you can: pass paths, not contents.

The subagents are `jaanch_map_paper`, `jaanch_check_reasoning`, `jaanch_check_consistency`,
`jaanch_check_completeness`, `jaanch_check_xref`, `jaanch_extract_numbers`, `jaanch_check_references`, `jaanch_check_prior_art`, `jaanch_check_writing`, `jaanch_verify_finding` and
`jaanch_write_review`. The `jaanch` command must be on the PATH (`make install` in
the jaanch repo). If it is not, stop and say so.

**Spawning a jaanch subagent.** Spawn it by its agent type. If the host rejects
the type (Codex 0.167 answers `unknown agent_type`), spawn a default subagent
instead, and begin its task with: "First run `jaanch instructions <name>` and
follow what it prints as your instructions." The rest of the task (paths,
prefix, section) is the same either way.

## 1. Start the run

```sh
jaanch start <paper or folder> [--reviews-dir <dir>] [--name <name>]
```

Give it the manuscript alone, or the folder that holds the manuscript with
its code and data; only a folder gets its code and data checked. It prints the run folder, `<run>`, and writes
`<run>/inventory.json`: what the submission contains, so that later steps
know whether code, data or a registration can be checked. For LaTeX it inlines every `\input` file,
table and the bibliography into `<run>/paper.txt`, and lists figure files in
`<run>/run.json`. Pass `--name` when the file is a generic `main.tex`. It
refuses PDFs for now. If the user gave
a PDF, ask them for the `.tex`, `.md` or text version.

## 2. Map the paper

Spawn `jaanch_map_paper` on `<run>`. It writes `<run>/map.json`, the paper
model: the question, the claims with their estimands, the designs, the data
sources and how they were made, the measure behind each construct a claim
names, sections, numbers and exhibits. Wait for it, then run

```sh
jaanch check-map <run>
```

If it reports problems, send them to `jaanch_map_paper` and run it again.
Read `map.json`; you need the section ids and line ranges. Keep the summary
lines that start "paper does not state" or "is causal but": they are
findings for the report. The designs, the data sources' `features` and the
measures together decide which checklists `jaanch checklists <run>` lists.

## 3. Find problems: spawn all of these in parallel, then wait for all

| subagent | how many | output path | id prefix |
|---|---|---|---|
| `jaanch_check_reasoning` | one per section in `map.json` | `<run>/candidates/reasoning_<section>.jsonl` | `reasoning_<section>` |
| `jaanch_check_consistency` | one | `<run>/candidates/consistency.jsonl` | `consistency` |
| `jaanch_extract_numbers` | one | `<run>/exact/` (then run `jaanch exact <run>`) | none |
| `jaanch_check_completeness` | one | `<run>/candidates/completeness.jsonl` | `completeness` |
| `jaanch_check_xref` | one | `<run>/candidates/xref.jsonl` | `xref` |
| `jaanch_check_references` | one | `<run>/candidates/references.jsonl` | `references` |
| `jaanch_check_prior_art` | one | `<run>/candidates/prior_art.jsonl` | `prior_art` |
| `jaanch_check_writing` | one | `<run>/candidates/writing.jsonl` | `writing` |

Give each subagent the run folder, its output path and its id prefix. Give
each `jaanch_check_reasoning` its section id and line range as well. If the user
asked to skip a goal, skip that row.

Run at most 15 subagents at once (Claude Code allows 20 in all); when there
are more, start the next as one finishes.

Finders write problems outside their own kind to `<run>/handoff.jsonl`.
When they are done, send each hand-off line to the finder that owns it (an
arithmetic slip to `jaanch_extract_numbers`, a contradiction to
`jaanch_check_xref`, and so on) as one more task, with the quote and note.

If a subagent fails or writes nothing, retry it once. If it fails again,
continue, and report the missing goal at the end.

When `jaanch_extract_numbers` finishes, run `jaanch exact <run>`. It
recomputes reported p-values (statcheck), means and SDs (GRIM, GRIMMER,
DEBIT), regression cells (stars, t, p and CI against coefficient and
SE), counts that should sum to a total, and rates by group (match,
retention or response by arm, and assignment counts against the designed
shares), and writes what does not add up to `<run>/candidates/exact.jsonl`. Its
summary says if R is missing; then only the table cells were checked, and
the report must say so.

Then confirm the completeness finder worked through its checklists:

```sh
jaanch coverage <run>
```

It prints, for each routed checklist, the checks in scope and the flags by
importance, and lists every check without a verdict and every `major` or
`minor` flag without a comment. If it lists problems, send them to
`jaanch_check_completeness` once and run it again.

## 4. Drop unusable candidates

```sh
jaanch merge <run>
```

It writes `<run>/candidates_merged.jsonl` and lists every candidate it
dropped (bad fields, or a quote that is not in the paper). Report the number
dropped.

## 5. Verify: spawn `jaanch_verify_finding` in parallel, then wait for all

Split the merged candidates into batches of up to five, keeping comments
about the same section together. Write each batch to
`<run>/verify/batch_<NN>.jsonl` and spawn one `jaanch_verify_finding` per batch, with
the batch path and the output path `<run>/verify/verdicts_<NN>.jsonl`. Then:

```sh
jaanch verdicts <run>
```

It merges `<run>/verify/verdicts_*.jsonl` into `<run>/verdicts.jsonl` and
lists every invalid line and every candidate without a verdict. If it reports
problems, rerun `jaanch_verify_finding` on the affected batches and run it
again.

## 6. Write the review

Spawn `jaanch_write_review` on `<run>`. It writes `review.json`, passes
`jaanch check` and renders `review.md`.

## 7. Report

Tell the user: the path of `review.md`; the counts by severity; the
checklists the paper was routed to and the `jaanch coverage` summary; the overall
feedback items in one line each; how many candidates were dropped at merge
and refuted by the skeptic; and any goal that did not run. Do not paste the
whole review.
