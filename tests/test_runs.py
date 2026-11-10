import json

import pytest
from conftest import make_comment, make_review

from jaanch.cli import main
from jaanch.render import render_review
from jaanch.runs import expand_macros, merge_candidates, slugify, start_run


def write_jsonl(path, records):
    path.write_text("".join(json.dumps(record) + "\n" for record in records))


def test_slugify():
    assert slugify("Golub & Calvó (2026) draft-v3") == "golub_calvo_2026_draft_v3"


def test_start_copies_paper_and_records_hash(paper_path, tmp_path):
    run_dir = start_run(paper_path, tmp_path / "reviews")
    assert (run_dir / "paper.txt").read_text() == paper_path.read_text()
    run = json.loads((run_dir / "run.json").read_text())
    assert len(run["sha256"]) == 64
    assert (run_dir / "candidates").is_dir()


def test_start_refuses_pdf(tmp_path):
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF-1.7")
    with pytest.raises(ValueError, match="not supported"):
        start_run(pdf, tmp_path / "reviews")


def test_merge_keeps_valid_and_drops_unanchored_and_duplicate(paper_path, tmp_path):
    run_dir = start_run(paper_path, tmp_path / "reviews")
    write_jsonl(run_dir / "candidates" / "consistency.jsonl", [make_comment()])
    write_jsonl(
        run_dir / "candidates" / "reasoning_s01.jsonl",
        [
            make_comment(id="reasoning_s01_001", goal="reasoning"),
            make_comment(id="reasoning_s01_002", goal="reasoning", quote="Errors are clustered by state."),
            make_comment(),
        ],
    )
    kept, dropped = merge_candidates(run_dir)
    assert [c["id"] for c in kept] == ["consistency_001", "reasoning_s01_001"]
    assert len(dropped) == 2
    assert any("quote not found" in line for line in dropped)
    assert any("duplicate id" in line for line in dropped)


def test_cli_check_fails_on_bad_review(paper_path, tmp_path):
    review_path = tmp_path / "review.json"
    review_path.write_text(json.dumps(make_review(paper_path, overall_ids=["missing_001"])))
    assert main(["check", str(review_path), "--paper", str(paper_path)]) == 1
    review_path.write_text(json.dumps(make_review(paper_path)))
    assert main(["check", str(review_path), "--paper", str(paper_path)]) == 0


def test_render_puts_critical_first(paper_path):
    comments = [
        make_comment(),
        make_comment(id="reasoning_s01_001", goal="reasoning", severity="critical", title="Wrong estimand"),
    ]
    text = render_review(make_review(paper_path, comments=comments))
    assert text.index("Wrong estimand") < text.index("Effect size described inconsistently")
    assert "> raised turnout by a third" in text


def test_expand_macros_replaces_values_in_body_only():
    text = (
        "\\newcommand{\\poolEstimate}{4.2}\n\\newcommand{\\poolLow}{\\poolEstimate{} minus 1}\n"
        "\\newcommand{\\bold}[1]{\\textbf{#1}}\n\\begin{document}\n"
        "Gain \\poolEstimate{} points, low \\poolLow, not \\poolEstimateX or \\bold{x}.\n"
    )
    expanded = expand_macros(text)
    assert "Gain 4.2 points, low 4.2 minus 1, not \\poolEstimateX or \\bold{x}." in expanded
    assert "\\newcommand{\\poolEstimate}{4.2}" in expanded
