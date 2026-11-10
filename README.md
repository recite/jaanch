# jaanch

**जाँच**: inspection, examination.

An open reviewer for draft papers. It does what [Refine](https://refine.ink)
does, inside Claude Code or Codex: it reads a paper the way a careful referee
would and returns the errors that would embarrass the authors after
publication. Each comment quotes the passage it concerns, has been checked by
a separate skeptic, and is tagged by severity, kind and fix effort.

**Status: pre-alpha.** The agents and the checking tools exist, and a
smoke test on a short paper with 6 planted errors found all 6 under both
Claude Code and Codex. The
evaluation that decides whether jaanch is better than asking a model once
([docs/success.md](docs/success.md)) has not been run, so there are no
results yet.

## What it checks

Each goal is a separate subagent, and the reasoning check runs once per
section, in parallel:

| goal | subagent |
|---|---|
| logic, derivations, proofs, method, overclaiming | `jaanch_check_reasoning` |
| text, tables, figures and numbers agree; recomputes what it can | `jaanch_check_consistency` |
| what a paper of this design must report but leaves out | `jaanch_check_completeness` |
| cited works exist, are not retracted, and say what is claimed | `jaanch_check_references` |
| novelty claims that miss published work | `jaanch_check_prior_art` |
| passages that make readers work too hard | `jaanch_check_writing` |
| tries to refute every candidate comment | `jaanch_verify_finding` |
| merges, ranks and writes the overall feedback | `jaanch_write_review` |
| whether a revision addressed an earlier review | `jaanch_check_revision` |

## Install

```sh
git clone https://github.com/recite/jaanch && cd jaanch
make install
```

This installs the `jaanch` command with `uv tool` and links the skills and
subagents into `~/.claude` (Claude Code) and `~/.agents`, `~/.codex` (Codex).
`make uninstall` removes them.

## Use

In Claude Code or Codex, from any directory:

```
Use the jaanch-review skill on paper.tex
```

The review goes to `reviews/<paper>/review.md`, with the structured version
in `review.json`. To check a revision:

```
Use jaanch-recheck on paper_v2.tex against reviews/paper/review.json
```

Input is `.tex`, `.md` or plain text for now; PDF ingest is not built yet.

## Develop

```sh
make ci          # lint, stale-agent check, tests
make agents      # after editing agents/
```

See [AGENTS.md](AGENTS.md) for the layout and [docs/design.md](docs/design.md)
for the design.
