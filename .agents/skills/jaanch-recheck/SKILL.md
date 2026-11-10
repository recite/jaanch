---
name: jaanch-recheck
description: Check whether a revised paper addresses the comments of an earlier jaanch review. Use when given a revised manuscript and a prior review.json.
---

# Re-check a revised paper

1. `jaanch start <revised paper> --reviews-dir <dir>` gives the new run
   folder, `<run>`.
2. Spawn `jaanch_check_revision` (if the host rejects that agent type, spawn a
   default subagent told to run `jaanch instructions jaanch_check_revision`
   first and follow it) with the prior `review.json`, `<run>/paper.txt`, and
   the output path `<run>/revision.jsonl`. For more than 30 prior comments,
   split them into batches of about 15, spawn one `jaanch_check_revision` per batch in
   parallel, give each its own output file, and concatenate the outputs into
   `<run>/revision.jsonl`.
3. Run `jaanch check-revision <run>/revision.jsonl --prior-review <prior
   review.json>`. It must report 0 problems.
4. Report the counts by status, and list each `not_addressed` and
   `partially_addressed` comment by id and title.

To look for new problems in the revision as well, run `jaanch-review` on it
separately.
