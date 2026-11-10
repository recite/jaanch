# What success means

jaanch reads a draft paper and returns the errors an expert referee would
catch: each tied to a quoted passage, verified, ranked by how much it matters,
with a suggested fix. It runs inside Claude Code or Codex, which supply the
model, the tools and the parallel subagents.

## The claim we have to earn

**On papers with known errors, jaanch finds more of them than a single
review by the same model, without raising more false alarms.**

The baseline is the thing every author can already do: paste the paper into
Claude or Codex and ask for a referee report. If jaanch cannot beat that, at
several times the cost, it has no reason to exist. Refine benchmarks against
the same baseline, which also lets us compare with its published numbers.

Everything below makes that claim measurable, and makes it able to fail.

## Test sets

Each set answers a different question. The first two are public and already
include Refine's results, so we can compare with Refine without paying for it.

**B: the Dawes planted-error benchmark (the first milestone).**
[Dawes-Institute/ai-peer-review-benchmark](https://github.com/Dawes-Institute/ai-peer-review-benchmark)
(MIT license, Paul Litvak, August 2026) planted 100 errors in 10 psychology
papers: statistics, design, causal inference, consistency, and 24 errors of
omission. It provides the original and modified papers, an answer key with the
exact snippets (`error_insertions.csv`), its matching code, and each system's
findings. Scores out of 100: **GPT-5.5 single review 71, Refine 57, Reviewer3
30**, with GPT-5.5 and Refine pooled reaching 80. Refine caught 5 of the 24
omissions. We score jaanch with the benchmark's own `matching.py`, so the
numbers are comparable. Caveats: it covers only one field and ten papers, and
since it has been public since August 2026, newer models may have seen it.

**L: Litt's archive (precision, on proofs).** Daniel Litt ran Refine on 20 of
his own published algebraic geometry papers and posted all 278 comments with a
validity rating ([daniellitt.com/published-paper-reviews.html](https://daniellitt.com/published-paper-reviews.html)).
He rated 89.2% correct, 8.6% partly correct and 2.2% wrong. We run jaanch on
the same papers, from their arXiv TeX source, and rate its comments with the
same rubric. That gives a comment-by-comment head-to-head on precision, and on
what each system finds that the other misses. Caveat: Litt's rubric was
applied with GPT plus his spot checks; it was not blind.

**S: our seeded errors (fields B and L do not cover).** Twenty open-access
papers from economics, statistics and political science. Into each we inject
3–5 errors from a fixed menu:

| injected error | topline goal it tests |
|---|---|
| a number in the text that disagrees with its table | consistency |
| a discussion that cites the wrong column or coefficient | consistency |
| a flipped sign or inequality in a derivation | reasoning |
| a dropped case or assumption in a proof | reasoning |
| a conclusion stronger than the estimate supports | reasoning |
| a robustness check, test or disclosure that the design requires, removed | completeness |
| a claim attributed to a cited paper that does not make it | references |
| a reference that does not exist | references |

A script makes each injection and records its exact span and kind in a file
the reviewer never sees. Eight papers are the development set. Twelve are held
out and run only at milestones, so we cannot tune prompts to them.

Two things could make B or S misleading, and each has a guard:

- *The injection is detectable for the wrong reason* (odd phrasing, a
  different model's style). Guard: a different model family than the reviewer
  writes our injections, and each one must be a minimal edit.
- *The paper already had an error at that spot.* Guard: we also review the
  unmodified paper. A finding that appears in both versions does not count as
  catching the injection.

**D: documented errors (does it find errors that happened by accident?).**
Planted errors are not natural ones. D is 20–30 papers whose errors were
documented by someone else: corrections and errata that say what was wrong,
retractions for honest error (Retraction Watch reasons such as "Error in
Analyses", already used in `propagation_of_error`), and I4R replication
reports that found an error visible in the paper itself. We review the version
from *before* the correction. One ready example: Notowidigdo's QJE
approximation error, which Refine found and which led to a corrigendum. D
contains only errors a reader could see in the text. A coding error that never
surfaces in a table is out of scope here (see "Not in v1").

**P: precision ratings (are its findings right?).** For ten papers, a person
(you or a coauthor) rates every critical and major comment, without knowing
which system wrote it, as *right and material*, *right but minor*, or *wrong*.
A panel of models from other families rates the same comments. We use the
panel as a cheap stand-in only if it agrees with the human ratings at Cohen's
κ ≥ 0.6, and we always report the agreement.

## When an error counts as found

A comment finds a ground-truth error when **both** hold:

1. its quote overlaps the error's span, or falls in the same paragraph,
   equation or table; and
2. its message identifies the same problem. A comment that happens to flag
   the right sentence for the wrong reason does not count.

A judge model from a different family than the reviewer applies rule 2 with a
written rubric. A person audits a random 20% of the judge's match decisions,
and we report the disagreement rate.

## Targets for v1

Intervals are paired bootstrap intervals over papers.

| criterion | target |
|---|---|
| **Recall on B** | ≥ 72 of 100: beats the best single review (GPT-5.5, 71) and Refine (57). Stretch: ≥ 80, the two pooled |
| **Recall gain over a single review by the same model** (on B and held-out S, using the benchmark's own prompt) | ≥ 10 points, and the 95% interval excludes 0 |
| Omissions found on B | ≥ 12 of 24 (Refine: 5) |
| Wrong comments on L, under Litt's rubric | no more than Refine's 2.2% on the same papers; ≤ 5% is the floor for release |
| Recall on D | above the single-review baseline; no absolute bar until we see first numbers |
| Critical or major comments rated *right and material* (set P) | ≥ 80% |
| Revision check: injected errors that are later repaired are marked `fully_addressed`; unrepaired ones `not_addressed` | ≥ 90% correct |
| Claude Code and Codex runs of the same paper | both pass the hygiene gates; recall within 10 points on B |
| One 15,000-word paper | ≤ 60 minutes wall clock; cost recorded per run |

We also run coarse (open source, about $2 a review) on B, S and D as a second
baseline. If jaanch does not beat coarse, we should use coarse.

Cost matters as much as recall. Users' most common complaint about Refine is
price: $40–50 a paper, against about $3 for a scaffold Hullman built on Opus.
The benchmark priced Refine at about $8.77 per error caught, against $0.04
for GPT-5.5. We report cost per error caught on B for every system.

## Each topline goal has its own measure

Each goal is its own subagent, so we can tell which one is weak.

| goal (subagent) | measure |
|---|---|
| reasoning (`jaanch_check_reasoning`) | recall on planted derivation, proof, statistics and overclaim errors |
| completeness (`jaanch_check_completeness`) | recall on the 24 planted omissions in B, and on omissions in S |
| consistency (`jaanch_check_consistency`) | recall on injected text/table/figure mismatches |
| references (`jaanch_check_references`) | recall on misattributions and nonexistent references; every reference either resolved or flagged |
| missing literature (`jaanch_check_prior_art`) | every suggested work exists, checked against Crossref or OpenAlex (gate: 100%); relevance rated in P |
| writing (`jaanch_check_writing`) | precision only, in P |
| skeptic (`jaanch_verify_finding`) | run B and S-dev with and without it: it must remove ≥ 30% of wrong comments while losing ≤ 5% of true detections. Standing check: a batch with planted wrong comments, all of which it must refute (it refuted 3 of 3 on 2026-11-09) |
| overall feedback (`jaanch_write_review`) | in P: does the overall section include every comment rated critical? |

## Hygiene gates (necessary, not evidence)

`jaanch check` enforces these on every review. Passing them says the output is
well formed and that every quote exists. It says nothing about whether the
findings are right.

- every comment validates against `src/jaanch/review.schema.json`;
- every quote appears in the source text, exactly or by fuzzy match;
- severity, kind and fix effort come from the fixed vocabulary;
- every comment ID cited by the overall feedback exists.

## Reported, not gated

- run-to-run stability: overlap of critical findings across two runs of the
  same paper (an Econometrica editor reports that repeated Refine runs catch
  different issues);
- an optional paid head-to-head with Refine on held-out S papers (about
  $40–50 each). B and L already give us Refine's output on 30 papers, so this
  is needed only for economics and political science. jaanch uses Refine's
  severity, kind and fix-effort vocabulary, so the two reviews can be matched
  comment by comment.

## Not in v1

- **Code and data.** Refine does not check replication packages, and this is
  where recite's other repos (softverse, milaan, kasauti, not_to_code) give us
  an advantage. It is the natural v2, with its own test set.
- A web interface or chat. The host CLI is the chat.
- Grant applications, legal documents and other non-paper formats.
