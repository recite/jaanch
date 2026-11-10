from conftest import PAPER, make_comment, make_review

from jaanch.check import anchor_quote, check_comments, check_review, check_revision_verdicts, normalize_text

PAPER_NORMALIZED = normalize_text(PAPER)


def test_exact_quote_anchors():
    assert anchor_quote("Table 2 reports the main estimates.", PAPER_NORMALIZED) == "exact"


def test_quote_across_hyphenated_line_break_anchors():
    # The paper reads "treat-\nment"; a model copying it writes "treatment".
    assert anchor_quote("The treatment effect is 0.42", PAPER_NORMALIZED) == "exact"


def test_ligature_and_case_differences_anchor():
    assert anchor_quote("the first column uses no controls", PAPER_NORMALIZED) == "exact"


def test_small_copying_error_anchors_fuzzily():
    quote = "which implies that the reminder raised turnout by one third relative to the control mean"
    assert anchor_quote(quote, PAPER_NORMALIZED) == "fuzzy"


def test_paraphrase_does_not_anchor():
    quote = "the estimated reminder effect equals 0.42, significant at five percent"
    assert anchor_quote(quote, PAPER_NORMALIZED) is None


def test_invented_quote_does_not_anchor():
    assert anchor_quote("We cluster standard errors at the village level.", PAPER_NORMALIZED) is None


def test_valid_comment_has_no_problems():
    assert check_comments([make_comment()], PAPER) == []


def test_unanchored_comment_is_reported():
    problems = check_comments([make_comment(quote="Standard errors are clustered by state.")], PAPER)
    assert any("quote not found" in p.message for p in problems)


def test_vocabulary_is_enforced():
    problems = check_comments([make_comment(severity="severe", kind="substance/typo")], PAPER)
    assert len(problems) == 2


def test_duplicate_ids_are_reported():
    problems = check_comments([make_comment(), make_comment()], PAPER)
    assert [p.message for p in problems] == ["duplicate id"]


def test_valid_review_has_no_problems(paper_path):
    assert check_review(make_review(paper_path), paper_path) == []


def test_overall_citing_unknown_comment_is_reported(paper_path):
    review = make_review(paper_path, overall_ids=["reasoning_s01_009"])
    problems = check_review(review, paper_path)
    assert [p.message for p in problems] == ["cites unknown comment reasoning_s01_009"]


def test_review_of_a_changed_paper_is_reported(paper_path):
    review = make_review(paper_path)
    paper_path.write_text(PAPER + "\nA new paragraph.\n")
    problems = check_review(review, paper_path)
    assert [p.message for p in problems] == ["sha256 does not match the paper given"]


def test_review_without_overall_feedback_is_reported(paper_path):
    review = make_review(paper_path)
    review["overall"] = []
    assert check_review(review, paper_path)


def test_verdicts_must_cover_every_prior_comment(paper_path):
    prior = make_review(paper_path, comments=[make_comment(), make_comment(id="reasoning_s01_001")])
    verdicts = [
        {"source_comment_id": "consistency_001", "status": "fully_addressed", "note": "Now says column 1."},
        {"source_comment_id": "writing_007", "status": "not_addressed", "note": "Unchanged."},
    ]
    messages = sorted(p.message for p in check_revision_verdicts(verdicts, prior))
    assert messages == ["not a comment in the prior review", "prior comment has no verdict"]
