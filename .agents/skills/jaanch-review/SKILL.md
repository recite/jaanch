---
name: jaanch-review
description: Review a draft academic paper for the errors an expert referee would catch (logic, proofs, method, text-table consistency, references, missing literature, clarity), with parallel subagents and a skeptic pass. Use when asked to review, referee, audit, or check a paper or manuscript before submission. Not for revising prose; not for re-checking a revision (use jaanch-recheck).
---

# Review a paper with jaanch

You orchestrate. Subagents do the reading. Keep the paper's text out of your
own context as far as you can: pass paths, not contents.

The subagents are `jaanch_map_paper`, `jaanch_check_reasoning`, `jaanch_check_consistency`,
`jaanch_check_completeness`, `jaanch_check_references`, `jaanch_check_prior_art`, `jaanch_check_writing`, `jaanch_verify_finding` and
`jaanch_write_review`. The `jaanch` command must be on the PATH (`make install` in
the jaanch repo). If it is not, stop and say so.

**Spawning a jaanch subagent.** Spawn it by its agent type. If the host rejects
the type (Codex 0.167 answers `unknown agent_type`), spawn a default subagent
instead, and begin its task with: "First run `jaanch instructions <name>` and
follow what it prints as your instructions." The rest of the task (paths,
prefix, section) is the same either way.

## 1. Start the run

```sh
jaanch start <paper> [--reviews-dir <dir>] [--name <name>]
```

It prints the run folder, `<run>`. For LaTeX it inlines every `\input` file,
table and the bibliography into `<run>/paper.txt`, and lists figure files in
`<run>/run.json`. Pass `--name` when the file is a generic `main.tex`. It
refuses PDFs for now. If the user gave
a PDF, ask them for the `.tex`, `.md` or text version.

## 2. Map the paper

Spawn `jaanch_map_paper` on `<run>`. Wait for it. Read `<run>/map.json`; you need the
section ids and line ranges.

## 3. Find problems: spawn all of these in parallel, then wait for all

| subagent | how many | output path | id prefix |
|---|---|---|---|
| `jaanch_check_reasoning` | one per section in `map.json` | `<run>/candidates/reasoning_<section>.jsonl` | `reasoning_<section>` |
| `jaanch_check_consistency` | one | `<run>/candidates/consistency.jsonl` | `consistency` |
| `jaanch_check_completeness` | one | `<run>/candidates/completeness.jsonl` | `completeness` |
| `jaanch_check_references` | one | `<run>/candidates/references.jsonl` | `references` |
| `jaanch_check_prior_art` | one | `<run>/candidates/prior_art.jsonl` | `prior_art` |
| `jaanch_check_writing` | one | `<run>/candidates/writing.jsonl` | `writing` |

Give each subagent the run folder, its output path and its id prefix. Give
each `jaanch_check_reasoning` its section id and line range as well. If the user
asked to skip a goal, skip that row.

If a subagent fails or writes nothing, retry it once. If it fails again,
continue, and report the missing goal at the end.

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
cat <run>/verify/verdicts_*.jsonl > <run>/verdicts.jsonl
```

## 6. Write the review

Spawn `jaanch_write_review` on `<run>`. It writes `review.json`, passes
`jaanch check` and renders `review.md`.

## 7. Report

Tell the user: the path of `review.md`; the counts by severity; the overall
feedback items in one line each; how many candidates were dropped at merge
and refuted by the skeptic; and any goal that did not run. Do not paste the
whole review.
