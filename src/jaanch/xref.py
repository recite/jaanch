"""Cross-reference: find places where a paper states the same fact two incompatible ways.

A planted or accidental edit usually changes one mention of a fact and
leaves the others: the sample is called a student pool in Methods and a
general population in the Discussion. An extractor writes every fact the
paper states to <run>/xref/facts.jsonl with a key naming what it is about;
this module groups facts by key and lists the keys whose values disagree.
A model then judges only those groups: do the quotes refer to the same
thing, and are the values incompatible?

Grouping is deterministic so that every disagreement is surfaced, and the
judgment is narrow so that a confirmed comment rests on two quotes a
reader can compare.
"""

import json
import re
from collections import defaultdict
from pathlib import Path

from jaanch.check import Problem, anchor_quote, locate_line, normalize_text, read_jsonl

FOLDER = "xref"
COMMENTS = Path("candidates") / "xref.jsonl"
GROUP_TAG = re.compile(r"^\[group: ([a-z0-9_:]+)\]")
HEADING = re.compile(r"^(#{1,3} \S|\\(?:sub)*section\*?\{)")
# A section this long states facts; extraction that skips it is incomplete.
MIN_SECTION_WORDS = 150
FACTS = "facts.jsonl"
GROUPS = "groups.jsonl"
KEY = re.compile(r"^[a-z_]+(:[a-z0-9_]+)+$")
NUMBER = re.compile(r"-?\d[\d,]*\.?\d*")
# The vocabulary keeps keys comparable across sections; a fact about the same
# thing must get the same key wherever it appears.
KINDS = {
    "sample": "who and how many: size, population, recruitment, exclusions",
    "design": "assignment, conditions, timing, within or between, waves",
    "measure": "how a construct is measured: instrument, items, scale, coding",
    "construct": "what a construct means or is called",
    "hypothesis": "a stated hypothesis or prediction, with its direction",
    "analysis": "model, focal predictor, covariates, estimator, thresholds",
    "result": "a reported finding: direction, significance, magnitude",
    "theory": "the framework or account the paper says it draws on",
    "count": "a count that other counts must add up to",
}


def _value_key(value: str) -> str:
    """Comparable form of a value: numbers as numbers, text casefolded without punctuation."""
    numbers = [n.replace(",", "") for n in NUMBER.findall(value)]
    if numbers and len(" ".join(numbers)) >= len(re.sub(r"\D", "", value)) * 0.5:
        return "#" + "|".join(str(float(n)) for n in numbers)
    return re.sub(r"[^a-z0-9 ]", "", normalize_text(value))


def load_facts(run_dir: Path) -> tuple[list[dict], list[Problem]]:
    path = run_dir / FOLDER / FACTS
    paper = normalize_text((run_dir / "paper.txt").read_text())
    facts, problems = [], []
    for number, row in enumerate(read_jsonl(path) if path.exists() else [], start=1):
        where = f"{FOLDER}/{FACTS}:{number}"
        missing = [field for field in ("id", "key", "value", "quote", "location") if not row.get(field)]
        if missing:
            problems.append(Problem(where, f"missing {', '.join(missing)}"))
            continue
        if not KEY.match(row["key"]) or row["key"].split(":")[0] not in KINDS:
            problems.append(
                Problem(where, f"key {row['key']!r} must be <kind>:<subject>[:...], kind in {sorted(KINDS)}")
            )
            continue
        if not anchor_quote(row["quote"], paper):
            problems.append(Problem(where, "quote is not in paper.txt"))
            continue
        facts.append(row)
    return facts, problems


def sections(run_dir: Path, lines: list[str]) -> list[tuple[str, int, int]]:
    """(heading, first line, last line) from map.json, or from markdown or LaTeX headings."""
    model = run_dir / "map.json"
    if model.exists():
        return [
            (s["heading"], s["start_line"], s["end_line"]) for s in json.loads(model.read_text())["sections"]
        ]
    starts = [i for i, line in enumerate(lines, start=1) if HEADING.match(line)] or [1]
    bounds = list(zip(starts, starts[1:] + [len(lines) + 1]))
    return [(lines[a - 1].strip()[:60], a, b - 1) for a, b in bounds]


def coverage_problems(run_dir: Path, facts: list[dict]) -> list[Problem]:
    """Every substantial section must contribute facts, so a changed mention is not simply missed."""
    text = (run_dir / "paper.txt").read_text()
    lines = text.splitlines()
    located = [locate_line(f["quote"], text) for f in facts]
    problems = []
    for heading, start, end in sections(run_dir, lines):
        words = len(" ".join(lines[start - 1 : end]).split())
        if words >= MIN_SECTION_WORDS and not any(n and start <= n <= end for n in located):
            problems.append(
                Problem(f"section {heading!r} (lines {start}-{end})", f"{words} words but no facts")
            )
    return problems


def comment_problems(run_dir: Path, groups: list[dict]) -> list[Problem]:
    """Each comment must judge one conflict group, named at the start of its message."""
    path = run_dir / COMMENTS
    keys = {group["key"] for group in groups}
    problems = []
    for number, comment in enumerate(read_jsonl(path) if path.exists() else [], start=1):
        match = GROUP_TAG.match(comment.get("message", ""))
        if not match:
            problems.append(Problem(f"{COMMENTS}:{number}", "message must start with [group: <key>]"))
        elif match.group(1) not in keys:
            problems.append(Problem(f"{COMMENTS}:{number}", f"{match.group(1)} is not a conflict group"))
    return problems


def conflicts(facts: list[dict]) -> list[dict]:
    """Keys stated with more than one distinct value, each value with the facts that state it."""
    by_key: dict[str, list[dict]] = defaultdict(list)
    for fact in facts:
        by_key[fact["key"]].append(fact)
    groups = []
    for key, members in sorted(by_key.items()):
        values: dict[str, list[dict]] = defaultdict(list)
        for fact in members:
            values[_value_key(fact["value"])].append(fact)
        if len(values) > 1:
            groups.append(
                {
                    "key": key,
                    "values": [
                        {
                            "value": stated[0]["value"],
                            "facts": [f["id"] for f in stated],
                            "quotes": [{"quote": f["quote"], "location": f["location"]} for f in stated],
                        }
                        for stated in values.values()
                    ],
                }
            )
    return groups


def run_xref(run_dir: Path) -> tuple[dict, list[Problem]]:
    facts, problems = load_facts(run_dir)
    problems += coverage_problems(run_dir, facts)
    groups = conflicts(facts)
    problems += comment_problems(run_dir, groups)
    out = run_dir / FOLDER / GROUPS
    out.parent.mkdir(exist_ok=True)
    out.write_text("".join(json.dumps(group) + "\n" for group in groups))
    keys = {fact["key"] for fact in facts}
    repeated = sum(1 for key in keys if sum(f["key"] == key for f in facts) > 1)
    summary = {
        "facts": len(facts),
        "keys": len(keys),
        "keys_stated_twice_or_more": repeated,
        "conflicts": len(groups),
    }
    return summary, problems
