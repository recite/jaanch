"""The check register: every canonical check, keyed by what it protects and how it catches a problem.

Pillars follow the validity typology (Shadish, Cook & Campbell 2002;
construct validity after Cronbach & Meehl 1955; external validity after
Cronbach's units, treatments, outcomes and settings), plus record
integrity, claim-evidence fit and contribution. Mechanisms are how a
problem is caught, independent of what it threatens. Keeping the two
apart is what lets the grid show where no check exists.
"""

import json
from collections import Counter
from functools import cache
from importlib.resources import files

from jsonschema import Draft202012Validator

from jaanch.check import Problem

PILLARS = ["record", "construct", "internal", "statistical", "external", "claim_fit", "contribution"]
OTHER = ["presentation", "process"]
MECHANISMS = ["exact", "cross_reference", "checklist", "retrieval", "rerun", "judgment"]


@cache
def load_register() -> list[dict]:
    text = files("jaanch").joinpath("checks", "register.jsonl").read_text()
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def validate_register(rows: list[dict]) -> list[Problem]:
    schema = json.loads(files("jaanch").joinpath("register.schema.json").read_text())
    validator = Draft202012Validator(schema)
    problems = [
        Problem(f"register {row.get('cid', number)}", error.message)
        for number, row in enumerate(rows, start=1)
        for error in validator.iter_errors(row)
    ]
    seen = Counter(row.get("cid") for row in rows)
    problems += [Problem(f"register {cid}", "cid is not unique") for cid, n in seen.items() if n > 1]
    return problems


def grid(rows: list[dict], ours_only: bool = False) -> dict[str, dict[str, int]]:
    """Count of checks per pillar and mechanism; second pillars count too, since a check serves both."""
    counts = {pillar: Counter() for pillar in PILLARS + OTHER}
    for row in rows:
        if ours_only and not row["ours"]:
            continue
        for pillar in filter(None, [row["pillar"], row.get("second_pillar")]):
            counts[pillar][row["mechanism"]] += 1
    return {pillar: {m: counts[pillar][m] for m in MECHANISMS} for pillar in PILLARS + OTHER}


def select(rows: list[dict], pillar=None, mechanism=None, design=None, ours=None) -> list[dict]:
    def keep(row):
        return (
            (pillar is None or pillar in (row["pillar"], row.get("second_pillar")))
            and (mechanism is None or row["mechanism"] == mechanism)
            and (design is None or row.get("design") == design)
            and (ours is None or bool(row["ours"]) == ours)
        )

    return [row for row in rows if keep(row)]


PILLAR_TEXT = {
    "record": "What is reported is what was done: numbers, tables, text, data, code and citations agree.",
    "construct": "Measures and manipulations capture the constructs the claims name (Cronbach & Meehl 1955).",
    "internal": "The design supports the causal claim: estimand, identifying assumptions, evidence for them.",
    "statistical": "The uncertainty is right: assignment-level SEs, power, multiplicity, specification.",
    "external": "Results generalize to the units, treatments, outcomes and settings claimed (Cronbach UTOS).",
    "claim_fit": "Conclusions follow from the evidence at the strength stated.",
    "contribution": "The work is new relative to prior work, and matters.",
}


def render_page(rows: list[dict], modules: dict[str, dict]) -> str:
    """The atlas page: pillars, pillar x mechanism grid, methods -> implications, and the register."""
    data = {
        "rows": rows,
        "pillars": PILLARS,
        "other": OTHER,
        "mechanisms": MECHANISMS,
        "pillar_text": PILLAR_TEXT,
        "modules": [
            {"title": m["title"], "designs": m["designs"], "checks": m["checks"]}
            for name, m in modules.items()
            if name != "universal"
        ]
        + [
            {
                "title": modules["universal"]["title"],
                "designs": ["every empirical design"],
                "checks": modules["universal"]["checks"],
            }
        ],
    }
    template = files("jaanch").joinpath("atlas.html").read_text()
    return template.replace("__DATA__", json.dumps(data, ensure_ascii=False).replace("</", "<\\/"))
