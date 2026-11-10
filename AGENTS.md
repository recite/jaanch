# jaanch: instructions for agents working in this repo

jaanch reviews draft papers. The host CLI (Claude Code or Codex) runs the
pipeline with subagents; the `jaanch` Python command does only the
deterministic steps (start a run, merge and validate candidates, check the
review, render it).

- To **review a paper**, use the `jaanch-review` skill. To **check a
  revision**, use `jaanch-recheck`.
- What counts as success, and how it is measured: `docs/success.md`. Read it
  before changing any prompt; a prompt change is good only if it moves those
  numbers.
- Design, the mapping to Refine's features, and open decisions:
  `docs/design.md`.

## Where things live

| path | what |
|---|---|
| `agents/roles/<name>.md` | each subagent's instructions, the single source |
| `agents/comment_rules.md` | output rules appended to every finder |
| `.claude/agents/`, `.codex/agents/` | **generated** by `make agents`; never edit |
| `.agents/skills/` | the orchestrating skills (Codex path); `.claude/skills` links here |
| `src/jaanch/review.schema.json` | the review and comment schema |
| `src/jaanch/` | the `jaanch` command |
| `reviews/` | run folders; gitignored, because papers are usually unpublished |

## Checks

`make ci` runs black, isort, flake8, the stale-agents check and pytest. It
must pass clean. `make ci-docker` runs the same in `python:3.12-slim`.
After editing `agents/`, run `make agents`.
