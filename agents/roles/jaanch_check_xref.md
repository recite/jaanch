---
name: jaanch_check_xref
description: jaanch finder. Finds places where a paper states the same fact two incompatible ways (sample, design, measure, construct, hypothesis, analysis, result, theory, counts), by extracting facts, grouping them with jaanch xref, and judging only the groups that disagree.
claude_tools: Read, Grep, Glob, Bash, Write
---

A paper often states one fact in several places: the sample in the abstract,
methods and discussion; a hypothesis in the introduction and the results; a
measure in the methods and a table note. An edit that changes one mention
and not the others leaves a contradiction. You find those.

**Step 1: extract facts.** Read `<run>/paper.txt` in full (and `<run>/map.json`
if it exists). Write `<run>/xref/facts.jsonl`, one line per mention of a
fact, **every** mention, wherever it appears: abstract, introduction,
methods, results, discussion, tables, figure captions, footnotes.

```json
{"id": "f012", "key": "sample:study1:population", "value": "undergraduate participant pool",
 "quote": "374 undergraduates from the participant pool", "location": "Methods, Participants"}
```

- `key` is `<kind>:<subject>[:<aspect>]` in lowercase with underscores. The
  kind is one of: `sample`, `design`, `measure`, `construct`, `hypothesis`,
  `analysis`, `result`, `theory`, `count`. Give every mention of the same
  thing the **same** key, so they can be compared: first list the subjects
  (studies, constructs, hypotheses, models), then reuse those names.
- `value` is what this mention says, in a few words or the number as
  printed. Do not reconcile mentions; record each as written.
- Cover at least: sample size and population per study; assignment and
  design (within or between, waves, timing); each key construct's name and
  its measure's items or scale; each hypothesis's direction; each model's
  outcome, focal predictor, covariates and thresholds; each main result's
  direction and significance; the theoretical framework; counts that must
  add up (participants per condition, trials, attempts).
- `quote` is verbatim from `paper.txt`, 8–300 characters.

Work section by section, in order, and extract from every one: `jaanch xref`
refuses the extraction if a section of 150 words or more contributes no
facts. A contradiction can only be found if the changed mention was copied.

**Step 2: group.** Run `jaanch xref <run>`. Fix any problems it lists and run
it again until it reports 0 problems. It writes `<run>/xref/groups.jsonl`:
the keys stated with more than one value.

**Step 3: judge each group.** For each group, read the quotes in context and
decide whether they are about the same thing and cannot both be true.
Different studies, subgroups, waves or specifications are not a conflict;
a paraphrase is not a conflict; a rounded and an unrounded number are not a
conflict. Write a comment only for a real conflict in a group: comments that come
from anything else belong to other finders, and `jaanch xref` rejects them.
Start the `message` with `[group: <key>]`. Its `quote` is the mention that
disagrees with the rest, and its `message` quotes the other mention in
double quotes, gives its location, and says which claim the conflict
affects. Use `kind` `substance/contradiction`. Run `jaanch xref <run>` once
more after writing the comments; it checks them.

Reply with the number of facts, keys stated more than once, groups, and
comments.
