import importlib.util
from pathlib import Path

from conftest import make_comment, make_review

SPEC = importlib.util.spec_from_file_location(
    "export_review", Path(__file__).resolve().parent.parent / "eval" / "dawes" / "export_review.py"
)
export_review = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(export_review)


def test_export_puts_problem_first_and_keeps_quote(paper_path):
    review = make_review(paper_path, comments=[make_comment()])
    exported = export_review.export_review(review, paper_id=3, provider="jaanch")
    finding = exported["issues"][0]
    assert exported["paper_id"] == 3
    assert finding["description"].startswith("Effect size described inconsistently. 0.42 / 1.26")
    assert finding["quote"] == "raised turnout by a third relative to the control mean"
    assert set(finding) == {"category", "subcategory", "description", "quote", "location", "severity"}
