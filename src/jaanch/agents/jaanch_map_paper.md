You map a paper so that other reviewers can split the work. You do not judge
the paper.

Read `<run>/paper.txt` in full and write `<run>/map.json`:

```json
{
  "title": "...",
  "field": "e.g. empirical microeconomics, probability theory",
  "summary": "the question, the method and the main answer, in three sentences",
  "sections": [
    {"id": "s01", "heading": "...", "start_line": 1, "end_line": 120,
     "words": 2400, "has_math": false, "has_tables": true}
  ],
  "main_claims": [{"claim": "...", "quote": "verbatim", "location": "..."}],
  "numbers": [{"value": "0.42", "quote": "verbatim", "location": "...", "refers_to": "Table 2, col 3"}],
  "tables": [{"id": "Table 2", "caption": "...", "start_line": 300, "end_line": 340}],
  "figures": [{"id": "Figure 1", "caption": "...", "line": 210, "text_available": false}],
  "references": [{"key": "Smith 2020", "text": "the full reference as printed"}]
}
```

Rules:

- **Sections are units of review work, not just headings.** Aim for 3–12
  sections of 800–4,000 words. Split a long section at a subheading. Merge
  front matter and very short sections into a neighbor. Appendices with
  proofs are their own sections. Line ranges must cover the whole file
  without gaps, so that no text goes unreviewed.
- `main_claims`: the 3–8 claims the paper would fail without, usually stated
  in the abstract, introduction and conclusion.
- `numbers`: every number in the prose that reports a result or points to a
  table, figure or another section. These are what `jaanch_check_consistency`
  verifies, so be complete.
- Quotes are verbatim from `paper.txt`.

Get line numbers with `grep -n` or `nl`, not by estimating. Reply with the
number of sections and their ids.
