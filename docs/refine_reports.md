# What users report about Refine

Collected 2026-11-09. "Firsthand" means the author ran Refine on their own
paper. Refine's own claims and competitors' comparisons are labeled as such.

## The two independent measurements

| source | what was measured | result |
|---|---|---|
| [Daniel Litt](https://daniellitt.com/published-paper-reviews.html) (mathematics, Toronto), Aug 2026 | all 278 Refine comments on 20 of his published algebraic geometry papers, rated with a GPT-written rubric plus his spot checks (not blind) | 89.2% correct, 8.6% partly correct, **2.2% wrong**; 78% were local, correctable errors; 5 comments (1.8%) corrected a main result; it missed one known lemma error |
| [Litvak / Dawes Institute](https://www.paullitvak.com/p/how-well-does-ai-peer-review-work) ([repo](https://github.com/Dawes-Institute/ai-peer-review-benchmark)), Aug 2026 | 100 planted errors in 10 psychology papers, scored by an LLM judge | **Refine 57**, GPT-5.5 single review 71, Reviewer3 30; GPT-5.5 and Refine pooled reached 80; Refine caught **5 of 24 omissions**; about $8.77 per error caught for Refine against $0.04 for GPT-5.5; false positives not measured |

No other measurement of precision was found. Nguyen et al. 2026
(arXiv:2606.19749) cites Refine but does not evaluate it.

## What users say it catches

- **Sign errors and typos that change meaning.** Joshua Goodman (BU): its
  first comment caught "reduces" written for "increases" in an abstract
  ([post](https://bsky.app/profile/joshua-goodman.com/post/3m5e52e6mok2n)).
  John Cochrane: "a negative sign that slipped"
  ([post](https://www.grumpy-economist.com/p/refine)). Matt Notowidigdo: an
  approximation-formula error that led to a QJE corrigendum
  ([post](https://bsky.app/profile/profnoto.bsky.social/post/3mihgiplxyc2o)).
- **Text against tables, notation and citations.** Jessica Leight (Yale):
  "mismatches btw text and table… incorrect citations… coding errors"
  ([post](https://bsky.app/profile/leightjessica.bsky.social/post/3m2ucwum67g2o)).
- **Proofs.** Litt: "a missing technical hypothesis in a main theorem".
- **Argument structure.** Cochrane: it flagged circular evidence.
- **High-level feedback.** Jessica Hullman (Northwestern): "much closer to
  what I'd expect from experts"
  ([post](https://bsky.app/profile/jessicahullman.bsky.social/post/3mgnnvdfa222c)).

## What users say it misses or gets wrong

Each count is the number of independent sources that made the complaint.

| complaint | sources | examples |
|---|---|---|
| wrong or disputed comments | 4 | Toda: "sophisticated but contained incorrect statements" ([arXiv:2606.05383](https://arxiv.org/abs/2606.05383)); Litt: about 2–3% wrong |
| misses central errors, or errors of omission | 4 | Toda: nothing serious until he steered it in chat; Leight: "I didn't learn that much about the core arguments"; Dawes: 5 of 24 omissions |
| cost | 4 | $40–50 a paper; Hullman: about $3 with an Opus scaffold matched its minor catches |
| misreads the PDF | 3 | Golub (vendor): tables and figures often aren't parsed; a commenter on Cochrane's post: equations pasted as images were ignored; by the research agent's count, 3 of Litt's 6 wrong comments came from text extraction |
| nitpicking | 2 | Toda: "nitpicking"; Litt: "typically quite minor" |
| different results on repeated runs | 1 | an Econometrica editor ([post](https://bsky.app/profile/marciano.bsky.social/post/3msgtzarsp224)) |

## What this means for jaanch

- **Benchmarks.** Dawes and Litt are public and include Refine's results;
  `success.md` uses both.
- **Parse source, not PDFs.** Text extraction caused half of Litt's wrong
  comments. jaanch reads TeX or Markdown, and `jaanch check` rejects quotes
  that are not in the source.
- **Omissions.** These are Refine's weakest category, so they get their own
  subagent, `jaanch_check_completeness`.
- **Citations.** 4 of Litt's 6 wrong comments were about citations, and
  Refine's FAQ says it does not check citations against live databases.
  `jaanch_check_references` looks every reference up.
- **Run-to-run variance.** It is reported in `success.md`. Merging two runs
  is a cheap fix if it turns out to be large.
- **The bar.** About 90% of comments fully correct and fewer than 3% wrong;
  reliable catches of flipped signs, text–table mismatches and missing
  hypotheses; overall feedback that experts call referee-grade.
