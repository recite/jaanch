# Scoring jaanch on the Dawes benchmark

Test set B in [docs/success.md](../../docs/success.md): 100 planted errors in
10 psychology papers, from
[Dawes-Institute/ai-peer-review-benchmark](https://github.com/Dawes-Institute/ai-peer-review-benchmark)
(MIT).

1. **Inputs.** Convert each modified paper with pandoc and drop the
   watermark paragraph:

   ```sh
   pandoc -f docx -t gfm --wrap=none "modified papers/$n.docx" \
     | grep -v 'BENCHMARK ARTIFACT' > paper_$n.md
   ```

   The benchmark's own extractor (`docx_extract.py`, python-docx) produced the
   text the published systems saw. pandoc formats tables differently, but the
   text is otherwise the same: 76 of the 83 planted errors that change text are
   found verbatim in the pandoc output.

2. **Review** each paper with the `jaanch-review` skill.

3. **Export** each review into the benchmark's format:

   ```sh
   python eval/dawes/export_review.py <run>/review.json --paper-id $n \
     --results-dir <benchmark>/benchmark/results
   ```

4. **Check the judge before trusting a score.** `matching.py` treats any API
   error as "no match", so a missing key or a retired judge model scores
   zero rather than failing. Score a control provider whose findings are the
   answer key's own descriptions; it must match nearly all 100.

5. **Score** from the benchmark's `benchmark/` folder, with
   `ANTHROPIC_API_KEY` in `benchmark/.env`:

   ```sh
   uv run score_reviews.py --provider jaanch
   ```

Published scores to compare with: GPT-5.5 single review 71, Refine 57, Claude
Opus single reviews 52–62, and 16–28 when the same systems review the
unmodified originals (matches by chance).
