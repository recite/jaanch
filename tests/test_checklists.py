import copy
import json

import pytest

from jaanch.checklists import check_coverage, load_checklists, validate_checklists
from jaanch.cli import main

PAPER = "We estimate a difference-in-differences model of county turnout.\nThe sample has 3,100 counties.\n"
DESIGN = {
    "design": "did",
    "role": "main",
    "reason": "main estimate",
    "quote": "difference-in-differences model",
}
DID_IDS = [check["id"] for check in load_checklists()["did"]["checks"]]


def write_run(tmp_path, designs, rows, comments=()):
    (tmp_path / "paper.txt").write_text(PAPER)
    (tmp_path / "map.json").write_text(json.dumps({"designs": designs}))
    (tmp_path / "checklists.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows))
    (tmp_path / "candidates").mkdir(exist_ok=True)
    (tmp_path / "candidates" / "completeness.jsonl").write_text(
        "".join(json.dumps(comment) + "\n" for comment in comments)
    )
    return tmp_path


UNIVERSAL_IDS = [check["id"] for check in load_checklists()["universal"]["checks"]]


def passing_rows():
    return [
        {"check": check, "status": "pass", "note": "stated in Section 2"} for check in DID_IDS + UNIVERSAL_IDS
    ]


def messages(problems):
    return [problem.message for problem in problems]


def test_shipped_checklists_are_valid():
    assert validate_checklists(load_checklists()) == []


def test_validation_catches_duplicate_ids_and_wrong_prefixes():
    checklists = copy.deepcopy(load_checklists())
    checklists["did"]["checks"].append(dict(checklists["did"]["checks"][0]))
    checklists["proof"]["checks"][0]["id"] = "DID-DERIV-09"
    found = messages(validate_checklists(checklists))
    assert any("is also in did" in message for message in found)
    assert any("does not start with PRF-" in message for message in found)


def test_complete_audit_passes_and_is_summarized(tmp_path):
    rows = passing_rows()
    rows = rows[: len(DID_IDS)]
    rows[0] = {"check": DID_IDS[0], "status": "flag", "importance": "major", "note": "no PT statement"}
    rows[1] = {"check": DID_IDS[1], "status": "flag", "importance": "negligible", "note": "side analysis"}
    rows[2] = {"check": DID_IDS[2], "status": "not_applicable", "note": "one treatment date"}
    comment = {"title": "No parallel trends", "message": f"Checklist {DID_IDS[0]}: missing."}
    universal = [
        {"check": c["id"], "status": "not_applicable", "note": "x"}
        for c in load_checklists()["universal"]["checks"]
    ]
    summary, problems = check_coverage(write_run(tmp_path, [DESIGN], rows + universal, [comment]))
    assert problems == []
    assert summary[0] == "did: 5 checks, 4 in scope, 2 flagged (1 major, 0 minor, 1 negligible)"
    assert summary[1].startswith("universal: 9 checks, 0 in scope")


@pytest.mark.parametrize(
    "edit, expected",
    [
        (lambda rows: rows.pop(), "has no verdict"),
        (
            lambda rows: rows.append({"check": "EXP-IDENT-01", "status": "pass", "note": "x"}),
            "not a check of",
        ),
        (lambda rows: rows.append(dict(rows[0])), "more than one verdict"),
        (lambda rows: rows[0].update(status="flag"), "importance"),
        (lambda rows: rows[0].update(importance="minor"), "should not be valid"),
        (lambda rows: rows[0].update(status="flag", importance="minor"), "but no comment names it"),
    ],
)
def test_audit_problems_are_reported(tmp_path, edit, expected):
    rows = passing_rows()
    edit(rows)
    _, problems = check_coverage(write_run(tmp_path, [DESIGN], rows))
    assert any(expected in message for message in messages(problems)), messages(problems)


def test_only_checklists_for_the_papers_designs_are_routed(tmp_path):
    proof = {"design": "proof", "role": "main", "reason": "theorem", "quote": "x" * 8}
    rows = [{"check": c["id"], "status": "pass", "note": "x"} for c in load_checklists()["proof"]["checks"]]
    summary, problems = check_coverage(write_run(tmp_path, [proof], rows))
    assert problems == []
    assert [line.split(":")[0] for line in summary] == ["proof"]


def test_unrouted_paper_needs_no_audit(tmp_path):
    write_run(tmp_path, [], [])
    (tmp_path / "checklists.jsonl").unlink()
    assert check_coverage(tmp_path) == ([], [])


def test_checklist_commands(tmp_path, capsys):
    assert main(["checklists"]) == 0
    assert "universal (" in capsys.readouterr().out
    assert main(["checklist", "did"]) == 0
    assert "DID-IDENT-01" in capsys.readouterr().out
    assert main(["checklist", "nonexistent"]) == 2
    assert main(["coverage", str(write_run(tmp_path, [DESIGN], passing_rows()[1:]))]) == 1


def test_checklists_command_with_a_run_lists_only_routed_checklists(tmp_path, capsys):
    run_dir = write_run(tmp_path, [DESIGN], [])
    assert main(["checklists", str(run_dir)]) == 0
    listed = [line.split(" ")[0] for line in capsys.readouterr().out.splitlines()]
    assert listed == ["did", "universal"]


def test_schema_command_prints_the_paper_model_schema(capsys):
    assert main(["schema", "paper-model"]) == 0
    assert "estimand" in capsys.readouterr().out
