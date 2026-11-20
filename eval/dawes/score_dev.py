"""Score jaanch candidates on Dawes papers against the planted errors, cheaply, during development.

A candidate catches a planted error when its quote, or a passage its
message quotes, shares a 25-character stretch of normalized text with the
error's modified snippet, so it points at the edited passage. The message
counts because a cross-reference comment names two passages and the edit
can be either one. That is localization only: it does not show
the candidate explains the error, which the benchmark's own judge decides.
Use it to compare versions of a check quickly; report milestone results
with the judge.

    python eval/dawes/score_dev.py <runs-dir> <error_insertions.csv> <mechanisms.jsonl> [--papers 1 3 4 9]

Runs are <runs-dir>/mod_<n> and <runs-dir>/orig_<n>; every candidates/*.jsonl
in a run counts. A candidate on a modified paper whose quote also matches a
candidate on the original is "shared": it is about the original paper, not
the planted error, and cannot count as a catch (the benchmark's own rule).
Unshared candidates that miss every planted error are reported separately:
they are either real problems the planted list does not include or false
alarms, and need reading.
"""

import argparse
import csv
import json
import re
from collections import Counter
from pathlib import Path

from rapidfuzz import fuzz

from jaanch.check import normalize_text

SPAN = 25


def norm(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", normalize_text(re.sub(r"[*_\\]", "", text)))


def overlaps(quote: str, snippet: str) -> bool:
    a, b = norm(quote), norm(snippet)
    if not a or not b:
        return False
    short, long = (a, b) if len(a) <= len(b) else (b, a)
    if len(short) < SPAN:
        return short in long
    return fuzz.partial_ratio(short[:200], long) >= 95 or any(
        short[i : i + SPAN] in long for i in range(0, len(short) - SPAN + 1, 5)
    )


def candidates(run: Path) -> list[dict]:
    """Every candidate in the run, minus those the skeptic refuted (verify/verdicts_*.jsonl)."""
    refuted = set()
    for path in (run / "verify").glob("verdicts_*.jsonl"):
        verdicts = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
        refuted |= {v["id"] for v in verdicts if v["verdict"] == "refuted"}
    found = []
    for path in sorted((run / "candidates").glob("*.jsonl")):
        rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
        found += [dict(row, _file=path.name) for row in rows if row.get("id") not in refuted]
    return found


def points_at(candidate: dict, snippet: str) -> bool:
    quoted = re.findall(r"[\"“]([^\"”]{25,})[\"”]", candidate.get("message", ""))
    return any(overlaps(text, snippet) for text in [candidate.get("quote", ""), *quoted])


def unshared(runs: Path, paper: int) -> list[dict]:
    original = [c.get("quote", "") for c in candidates(runs / f"orig_{paper}")]
    return [
        c
        for c in candidates(runs / f"mod_{paper}")
        if not any(overlaps(c.get("quote", ""), q) for q in original)
    ]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("runs", type=Path)
    parser.add_argument("errors", type=Path)
    parser.add_argument("mechanisms", type=Path)
    parser.add_argument("--papers", nargs="*", type=int, default=list(range(1, 11)))
    args = parser.parse_args()
    errors = list(csv.DictReader(args.errors.open()))
    mechanisms = [json.loads(line) for line in args.mechanisms.read_text().splitlines()]
    planted, caught, clean_flags, flags = Counter(), Counter(), Counter(), Counter()
    for error, mechanism in zip(errors, mechanisms):
        if int(error["paper"]) not in args.papers:
            continue
        kind = mechanism["mechanism"]
        planted[kind] += 1
        found = unshared(args.runs, int(error["paper"]))
        if any(points_at(c, error["modified_snippet"]) for c in found):
            caught[kind] += 1
    shared, unmatched = Counter(), Counter()
    for paper in args.papers:
        snippets = [e["modified_snippet"] for e in errors if int(e["paper"]) == paper]
        for c in candidates(args.runs / f"orig_{paper}"):
            clean_flags[c["_file"]] += 1
        mine = unshared(args.runs, paper)
        for c in candidates(args.runs / f"mod_{paper}"):
            flags[c["_file"]] += 1
            if c not in mine:
                shared[c["_file"]] += 1
            elif not any(points_at(c, s) for s in snippets):
                unmatched[c["_file"]] += 1
    print(f"{'mechanism':16} planted  caught")
    for kind in sorted(planted):
        print(f"{kind:16} {planted[kind]:7} {caught[kind]:7}")
    print(f"{'all':16} {sum(planted.values()):7} {sum(caught.values()):7}")
    print("candidates on modified papers, by file:", dict(flags))
    print("candidates on clean originals, by file:", dict(clean_flags))
    print("modified-paper candidates shared with the original:", dict(shared))
    print("modified-paper candidates neither shared nor on a planted error:", dict(unmatched))


if __name__ == "__main__":
    main()
