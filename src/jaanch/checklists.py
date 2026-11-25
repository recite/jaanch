"""Design checklists, and the gate that the completeness finder worked through them.

The finder used to invent the list of what a design must report on every run.
Fixed checklists make that list the same for every paper of a design, and the
audit log lets a script confirm each check got a verdict. The approach and the
per-check fields follow Chau and Little (2026), SocArXiv zk26u.
"""

import json
from collections import Counter
from functools import cache
from importlib.resources import files
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

from jaanch.check import Problem, read_jsonl

AUDIT_FILE = "checklists.jsonl"
COMMENTS_FILE = Path("candidates") / "completeness.jsonl"
# A negligible flag is real but does not bear on a main claim, so it is logged
# and not sent on as a comment.
REPORTED_IMPORTANCE = {"minor", "major"}


@cache
def _validator(definition: str) -> Draft202012Validator:
    schema = json.loads(files("jaanch").joinpath("checklist.schema.json").read_text())
    return Draft202012Validator({"$ref": f"#/$defs/{definition}", "$defs": schema["$defs"]})


def _schema_problems(record: object, definition: str, where: str) -> list[Problem]:
    return [
        Problem(where, f"{'/'.join(map(str, error.path)) or '(root)'}: {error.message}")
        for error in _validator(definition).iter_errors(record)
    ]


def checklist_text(module: str) -> str | None:
    path = files("jaanch").joinpath("checklists", f"{module}.yaml")
    return path.read_text() if path.is_file() else None


@cache
def load_checklists() -> dict[str, dict]:
    folder = files("jaanch").joinpath("checklists")
    paths = sorted((item for item in folder.iterdir() if item.name.endswith(".yaml")), key=lambda p: p.name)
    return {path.name.removesuffix(".yaml"): yaml.safe_load(path.read_text()) for path in paths}


def validate_checklists(checklists: dict[str, dict]) -> list[Problem]:
    problems = []
    seen: dict[str, str] = {}
    prefixes: dict[str, str] = {}
    for name, checklist in checklists.items():
        where = f"checklists/{name}.yaml"
        found = _schema_problems(checklist, "checklist", where)
        problems += found
        if found:
            continue
        if checklist["module"] != name:
            problems.append(Problem(where, f"module {checklist['module']!r} must match the file name"))
        if not checklist["designs"] and not checklist.get("data"):
            problems.append(Problem(where, "routes no paper: give designs or data"))
        prefix = checklist["prefix"]
        if prefix in prefixes:
            problems.append(Problem(where, f"prefix {prefix} is also used by {prefixes[prefix]}"))
        prefixes[prefix] = name
        for check in checklist["checks"]:
            if not check["id"].startswith(prefix + "-"):
                problems.append(Problem(where, f"{check['id']} does not start with {prefix}-"))
            if check["id"] in seen:
                problems.append(Problem(where, f"{check['id']} is also in {seen[check['id']]}"))
            seen[check["id"]] = name
    from jaanch.register import load_bib, load_register

    known = {row["cid"] for row in load_register()}
    bib = load_bib()
    for name, checklist in checklists.items():
        for check in checklist.get("checks", []):
            for cid in check.get("register", []):
                if cid not in known:
                    problems.append(
                        Problem(f"checklists/{name}.yaml", f"{check.get('id')}: {cid} is not in the register")
                    )
            for source in check.get("sources", []):
                if source.split(":")[0] not in bib:
                    problems.append(
                        Problem(
                            f"checklists/{name}.yaml", f"{check.get('id')}: {source} is not in sources.bib"
                        )
                    )
    if "universal" not in checklists:
        problems.append(Problem("checklists", "there is no universal checklist"))
    return problems


def data_features(model: dict) -> set[str]:
    """How the paper's data were made, as map.json records it: source features, measure sources and forms."""
    features = {feature for source in model.get("data_sources", []) for feature in source.get("features", [])}
    for measure in model.get("measures", []):
        features |= {measure["source"], measure["form"]}
    return features


def routed_modules(model: dict, checklists: dict[str, dict] | None = None) -> list[str]:
    """Modules a paper is routed to: by its designs, or by how its data were made."""
    checklists = checklists or load_checklists()
    designs = {item["design"] for item in model.get("designs", [])}
    features = data_features(model)
    return [
        name
        for name, checklist in checklists.items()
        if designs & set(checklist["designs"]) or features & set(checklist.get("data", []))
    ]


def check_coverage(run_dir: Path) -> tuple[list[str], list[Problem]]:
    """Confirm every check of every routed checklist has a verdict, and every reportable flag a comment.

    A paper is routed to a checklist when map.json names one of the checklist's
    designs, or when its data sources or measures carry one of the checklist's
    data values; jaanch check-map has already validated both.
    """
    checklists = load_checklists()
    problems: list[Problem] = []

    routed = routed_modules(json.loads((run_dir / "map.json").read_text()), checklists)

    expected = {check["id"]: module for module in routed for check in checklists[module]["checks"]}
    audit_path = run_dir / AUDIT_FILE
    rows = read_jsonl(audit_path) if audit_path.exists() else []
    if expected and not audit_path.exists():
        problems.append(Problem(AUDIT_FILE, "missing; jaanch_check_completeness must write it"))

    verdicts: dict[str, dict] = {}
    for number, row in enumerate(rows, start=1):
        where = f"{AUDIT_FILE}:{number}"
        found = _schema_problems(row, "audit_row", where)
        problems += found
        if found:
            continue
        check = row["check"]
        if check not in expected:
            problems.append(Problem(where, f"{check} is not a check of a routed checklist"))
        elif check in verdicts:
            problems.append(Problem(where, f"{check} has more than one verdict"))
        else:
            verdicts[check] = row
    for check in expected:
        if check not in verdicts:
            problems.append(Problem(AUDIT_FILE, f"{check} has no verdict"))

    comments_path = run_dir / COMMENTS_FILE
    comments = read_jsonl(comments_path) if comments_path.exists() else []
    cited = " ".join(comment.get("message", "") + " " + comment.get("title", "") for comment in comments)
    for check, row in verdicts.items():
        if row["status"] == "flag" and row["importance"] in REPORTED_IMPORTANCE and check not in cited:
            problems.append(
                Problem(str(COMMENTS_FILE), f"{check} is flagged {row['importance']} but no comment names it")
            )

    return _summary(routed, checklists, verdicts), problems


def _summary(routed: list[str], checklists: dict[str, dict], verdicts: dict[str, dict]) -> list[str]:
    lines = []
    for module in routed:
        ids = [check["id"] for check in checklists[module]["checks"]]
        rows = [verdicts[i] for i in ids if i in verdicts]
        status = Counter(row["status"] for row in rows)
        importance = Counter(row["importance"] for row in rows if row["status"] == "flag")
        in_scope = status["pass"] + status["flag"]
        flags = ", ".join(f"{importance[level]} {level}" for level in ("major", "minor", "negligible"))
        lines.append(f"{module}: {len(ids)} checks, {in_scope} in scope, {status['flag']} flagged ({flags})")
    return lines
