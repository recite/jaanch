import copy
import json

import pytest

from jaanch.cli import main
from jaanch.paper_model import check_map
from jaanch.runs import start_run

PAPER = """# Text Reminders and Turnout
We randomly assigned 6,000 voters to a text reminder or no message.
Reminders increased turnout by 4.1 percentage points.
Table 1: Effect of reminders on turnout
The control mean was 21.6 percent.
"""

ESTIMAND = {
    "statement": "ITT effect of a text reminder on turnout among registered voters",
    "unit": "registered voter",
    "population": "registered voters in one municipal election",
    "treatment_or_exposure": "one text reminder",
    "outcome": "turnout",
    "comparison": "no message",
}
MODEL = {
    "title": "Text Reminders and Turnout",
    "field": "political science",
    "question": "Do text reminders raise turnout?",
    "summary": "A field experiment. Reminders raise turnout.",
    "sections": [{"id": "s01", "heading": "all", "start_line": 1, "end_line": 5}],
    "claims": [
        {
            "id": "c1",
            "claim": "Reminders raise turnout by 4.1 points",
            "quote": "Reminders increased turnout by 4.1 percentage points.",
            "location": "line 3",
            "type": "causal",
            "mechanism": None,
            "extrapolation": None,
            "estimand": ESTIMAND,
            "magnitude": {"raw": "4.1 percentage points", "baseline": "control mean 21.6 percent"},
            "evidence": ["Table 1"],
        }
    ],
    "designs": [
        {
            "design": "experiment",
            "role": "main",
            "claims": ["c1"],
            "reason": "random assignment",
            "quote": "We randomly assigned 6,000 voters",
        }
    ],
    "data_sources": [{"name": "voter file", "kind": "administrative", "quote": "6,000 voters", "n": "6,000"}],
    "measures": [
        {
            "id": "m1",
            "construct": "turnout",
            "role": "outcome",
            "operationalization": "voted in the municipal election, from the voter file",
            "form": "single_item",
            "source": "administrative",
            "items": "vote history flag",
            "validity_evidence": "not stated",
            "reliability": "not stated",
            "data_source": "voter file",
            "claims": ["c1"],
            "quote": "Reminders increased turnout",
        },
        {
            "id": "m2",
            "construct": "text reminder",
            "role": "treatment",
            "operationalization": "one text message before the election",
            "form": "manipulation",
            "source": "researcher_assigned",
            "items": "not stated",
            "validity_evidence": "not stated",
            "reliability": "not stated",
            "claims": ["c1"],
            "quote": "a text reminder or no message",
        },
    ],
    "numbers": [{"value": "4.1", "quote": "4.1 percentage points", "location": "line 3"}],
    "tables": [{"id": "Table 1", "caption": "Effect of reminders on turnout", "line": 4}],
    "figures": [],
    "references": [],
}


def run(tmp_path, model):
    (tmp_path / "paper.txt").write_text(PAPER)
    (tmp_path / "map.json").write_text(json.dumps(model))
    return tmp_path


def messages(problems):
    return [problem.message for problem in problems]


def test_valid_model_passes_and_is_summarized(tmp_path):
    summary, problems = check_map(run(tmp_path, MODEL))
    assert problems == []
    assert summary == [
        "1 claims (causal); designs: experiment/main; 1 data sources; 2 measures; "
        "1 numbers; 1 tables; 0 figures",
        "paper does not state the items for m2 (text reminder)",
    ]


def edit(change):
    model = copy.deepcopy(MODEL)
    change(model)
    return model


@pytest.mark.parametrize(
    "change, expected",
    [
        (
            lambda m: m["claims"][0].update(quote="a sentence the paper never wrote"),
            "quote is not in paper.txt",
        ),
        (lambda m: m["sections"][0].update(end_line=4), "cover lines 1-4, but paper.txt has 5"),
        (lambda m: m["sections"][0].update(start_line=2), "starts at line 2, expected 1"),
        (lambda m: m["claims"][0].update(evidence=["Table 9"]), "names an exhibit not in tables or figures"),
        (lambda m: m["designs"][0].update(claims=["c7"]), "claim c7 does not exist"),
        (lambda m: m["designs"][0].update(design="regression"), "does not match"),
        (lambda m: m["claims"][0].update(type="mechanism"), "is not one of"),
        (lambda m: m["claims"][0]["estimand"].pop("outcome"), "'outcome' is a required property"),
        (lambda m: m["measures"].pop(0), "its outcome has no measure with role outcome"),
        (
            lambda m: m["measures"].pop(1),
            "its treatment_or_exposure has no measure with role treatment or exposure",
        ),
        (lambda m: m["measures"][0].update(claims=["c9"]), "claim c9 does not exist"),
        (lambda m: m["measures"][0].update(data_source="census"), "'census' is not in data_sources"),
        (lambda m: m["measures"][0].update(source="vibes"), "is not one of"),
    ],
)
def test_map_problems_are_reported(tmp_path, change, expected):
    _, problems = check_map(run(tmp_path, edit(change)))
    assert any(expected in message for message in messages(problems)), messages(problems)


def test_unstated_estimand_and_unlinked_causal_claim_are_findings_not_errors(tmp_path):
    def change(model):
        model["claims"][0]["estimand"]["population"] = "not stated"
        model["designs"][0]["claims"] = []

    summary, problems = check_map(run(tmp_path, edit(change)))
    assert problems == []
    assert "paper does not state the population for c1" in summary
    assert "c1 is causal but no identification design is linked to it" in summary


def test_check_map_command(tmp_path):
    assert main(["check-map", str(run(tmp_path, MODEL))]) == 0
    assert main(["check-map", str(run(tmp_path, edit(lambda m: m["sections"][0].update(end_line=3))))]) == 1


def test_start_on_a_folder_finds_the_manuscript_and_writes_the_inventory(tmp_path):
    project = tmp_path / "project"
    (project / "ms").mkdir(parents=True)
    (project / "R").mkdir()
    (project / "ms" / "main.tex").write_text("\\documentclass{article}\\begin{document}x\\end{document}\n")
    (project / "R" / "fit.R").write_text("lm(y ~ x)")
    run_dir = start_run(project, tmp_path / "reviews")
    inv = json.loads((run_dir / "inventory.json").read_text())
    assert inv["manuscript"]["path"] == "ms/main.tex"
    assert "code" in inv["available"]
    assert (run_dir / "paper.txt").exists()


def test_start_refuses_a_folder_without_a_manuscript(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    (project / "fit.py").write_text("print(1)")
    with pytest.raises(ValueError, match="no manuscript found"):
        start_run(project, tmp_path / "reviews")


def test_start_on_a_file_inventories_only_that_file(tmp_path):
    project = tmp_path / "project"
    (project / "R").mkdir(parents=True)
    (project / ".git").mkdir()
    (project / "R" / "fit.R").write_text("lm(y ~ x)")
    (project / "paper.md").write_text("A paper.")
    run_dir = start_run(project / "paper.md", tmp_path / "reviews")
    inv = json.loads((run_dir / "inventory.json").read_text())
    assert inv["available"] == ["paper_text"]


def test_scale_without_validity_or_reliability_is_a_finding(tmp_path):
    def change(model):
        model["measures"][0].update(form="multi_item_scale", items="not stated")

    summary, problems = check_map(run(tmp_path, edit(change)))
    assert problems == []
    assert "paper does not state the items, validity evidence, reliability for m1 (turnout)" in summary
