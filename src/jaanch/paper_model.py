"""Validate the paper model (map.json) that every later stage reads.

The mapper is a model, so its output is checked here before anything is
built on it: the fields exist, every quote is in the paper, the sections
cover every line, and the claims point at exhibits that exist.
"""

import json
import re
from functools import cache
from importlib.resources import files
from pathlib import Path

from jsonschema import Draft202012Validator

from jaanch.check import Problem, anchor_quote, normalize_text

REQUIRED_ESTIMAND = ["unit", "population", "outcome", "comparison"]
NOT_STATED = "not stated"
EXHIBIT_REF = re.compile(r"^((?:Table|Figure)\s+[A-Z]?\d+[a-z]?)", re.IGNORECASE)


@cache
def _validator() -> Draft202012Validator:
    return Draft202012Validator(json.loads(files("jaanch").joinpath("paper_model.schema.json").read_text()))


def _quotes(model: dict) -> list[tuple[str, str]]:
    found = []
    for key in ("claims", "designs", "data_sources", "numbers"):
        for index, item in enumerate(model.get(key, [])):
            if item.get("quote"):
                found.append((f"{key}[{index}]", item["quote"]))
    return found


def _section_problems(sections: list[dict], line_count: int) -> list[Problem]:
    problems = []
    expected = 1
    for section in sections:
        where = f"sections {section['id']}"
        if section["start_line"] != expected:
            problems.append(Problem(where, f"starts at line {section['start_line']}, expected {expected}"))
        if section["end_line"] < section["start_line"]:
            problems.append(Problem(where, "ends before it starts"))
        expected = section["end_line"] + 1
    if sections and expected - 1 != line_count:
        problems.append(Problem("sections", f"cover lines 1-{expected - 1}, but paper.txt has {line_count}"))
    return problems


def check_map(run_dir: Path) -> tuple[list[str], list[Problem]]:
    """Problems with the map itself, and a summary that lists gaps in how the paper states its claims."""
    model = json.loads((run_dir / "map.json").read_text())
    errors = sorted(_validator().iter_errors(model), key=lambda error: list(error.path))
    if errors:
        return [], [Problem(f"map.json {'/'.join(map(str, e.path)) or '(root)'}", e.message) for e in errors]

    text = (run_dir / "paper.txt").read_text()
    paper = normalize_text(text)
    problems = [
        Problem(where, "quote is not in paper.txt")
        for where, q in _quotes(model)
        if not anchor_quote(q, paper)
    ]
    problems += _section_problems(model["sections"], len(text.splitlines()))

    claim_ids = [claim["id"] for claim in model["claims"]]
    if len(set(claim_ids)) != len(claim_ids):
        problems.append(Problem("claims", "claim ids are not unique"))
    exhibits = {item["id"].casefold() for item in model["tables"] + model["figures"]}
    sections = {section["id"] for section in model["sections"]}
    for claim in model["claims"]:
        for ref in claim["evidence"]:
            match = EXHIBIT_REF.match(ref)
            if match and match.group(1).casefold() not in exhibits:
                problems.append(
                    Problem(
                        f"claims {claim['id']}", f"evidence {ref!r} names an exhibit not in tables or figures"
                    )
                )
            elif (
                not match
                and ref.split(",")[0].strip() not in sections
                and not ref.lower().startswith("section")
            ):
                problems.append(
                    Problem(
                        f"claims {claim['id']}", f"evidence {ref!r} is neither an exhibit nor a section id"
                    )
                )
    for design in model["designs"]:
        for claim_id in design.get("claims", []):
            if claim_id not in claim_ids:
                problems.append(Problem(f"designs {design['design']}", f"claim {claim_id} does not exist"))

    summary = [
        f"{len(model['claims'])} claims ({', '.join(c['type'] for c in model['claims'])}); "
        f"designs: {', '.join(d['design'] + '/' + d['role'] for d in model['designs']) or 'none'}; "
        f"{len(model['data_sources'])} data sources; {len(model['numbers'])} numbers; "
        f"{len(model['tables'])} tables; {len(model['figures'])} figures"
    ]
    # An estimand element the paper never states is not an error in the map.
    # It is a finding about the paper, reported here so the review can use it.
    for claim in model["claims"]:
        missing = [
            key for key in REQUIRED_ESTIMAND if claim["estimand"].get(key, "").strip().lower() == NOT_STATED
        ]
        if missing:
            summary.append(f"paper does not state the {', '.join(missing)} for {claim['id']}")
        causal_designs = [
            d for d in model["designs"] if d["design"] != "descriptive" and claim["id"] in d.get("claims", [])
        ]
        if claim["type"] == "causal" and not causal_designs:
            summary.append(f"{claim['id']} is causal but no identification design is linked to it")
    return summary, problems
