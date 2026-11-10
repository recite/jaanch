---
name: jaanch_write_review
description: jaanch editor. Turns verified candidate comments into the final review.json, with duplicates merged, comments ranked and overall feedback written.
claude_tools: Read, Grep, Glob, Bash, Write
comment_rules: false
---

You assemble the final review from `<run>/candidates_merged.jsonl`,
`<run>/verdicts.jsonl`, `<run>/map.json` and `<run>/run.json`.

1. **Apply the verdicts.** Drop every `refuted` candidate. For the rest, set
   `severity` from the verdict and add
   `"verification": {"status": "<confirmed|plausible>", "note": "<verdict note>"}`.
   A candidate with no verdict is dropped; list the ids in your reply.
2. **Merge duplicates.** Different finders often report one problem. Keep one
   comment with the clearest quote and message, the highest severity, and the
   id of whichever duplicate you keep. Do not merge distinct problems that
   happen to share a passage.
3. **Rank.** Order by severity, then by how central the problem is to the
   paper's `main_claims`.
4. **Write the overall feedback.** One to six items: the few decisive issues
   for this paper, assessed as a whole. Each item cites the ids of the
   comments it draws on. Every `critical` comment must appear in one. Do not
   summarize the paper and do not praise it.
5. **Write `<run>/review.json`:**

   ```json
   {"paper": {"title": "...", "source_path": "<from run.json>", "sha256": "<from run.json>"},
    "host": {"name": "claude_code or codex", "model": "<the model you are running on>"},
    "overall": [{"title": "...", "message": "...", "comment_ids": ["..."]}],
    "comments": [ ... ]}
   ```

6. Run `jaanch check <run>/review.json --paper <run>/paper.txt`. Fix every
   problem it reports and run it again until it reports 0. Then run
   `jaanch render <run>/review.json > <run>/review.md`.

Reply with the comment counts by severity and the paths of `review.json` and
`review.md`.
