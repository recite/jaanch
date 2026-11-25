import json

import pytest

from jaanch import exact
from jaanch.cli import main

STARS = {"*": 0.1, "**": 0.05, "***": 0.01}


def cell(**kw):
    return {"id": "c1", "quote": "x", **kw}


@pytest.mark.parametrize(
    "row, ok",
    [
        (cell(coef="0.50", se="0.20", stars="**", thresholds=STARS), True),  # z = 2.5, p = .012
        (cell(coef="0.50", se="0.30", stars="***", thresholds=STARS), False),  # z = 1.67, p = .096
        (cell(coef="2.00", se="0.50", stars="", thresholds=STARS), False),  # z = 4 but no stars
        (cell(coef="0.10", se="0.05", stars="**", thresholds=STARS), True),  # rounding allows p < .05
        (cell(coef="0.10", se="0.05", stars="***", thresholds=STARS), False),  # no rounding gives p < .01
        (cell(coef="0.50", se="0.20", t="2.5"), True),
        (cell(coef="0.50", se="0.20", t="4.1"), False),
        (cell(coef="0.50", se="0.20", p="0.012"), True),
        (cell(coef="0.50", se="0.20", p="< 0.001"), False),
        (cell(coef="1.00", se="0.25", ci_low="0.51", ci_high="1.49"), True),  # 1.96 x .25 = .49
        (cell(coef="1.00", se="0.25", ci_low="0.80", ci_high="1.20"), False),
        (cell(coef="1.00", se="0.25", ci_low="0.60", ci_high="1.60"), False),  # Wald width, off center
        (cell(coef="-0.04", ci_low="-0.54", ci_high="0.25"), True),  # no SE: interval may be asymmetric
        # Dawes paper 1's planted error (CI widened from [-.03, -.01]): at two decimals no
        # check can see it, and a level printed as "95" must not turn the bound into NaN
        (cell(coef="-.02", se=".01", p=".001"), True),
        (cell(coef="-.02", se=".01", p=".001", ci_low="-.05", ci_high="-.01", ci_level="95"), True),
        (cell(coef="1.00", se="0.25", ci_low="0.80", ci_high="1.20", ci_level="95"), False),
        # the reported p narrows the SE: at three decimals a widened interval shows
        (cell(coef="-.020", se=".006", p=".001", ci_low="-.050", ci_high="-.010"), False),
        (cell(coef="-.020", se=".006", p=".001", ci_low="-.032", ci_high="-.008"), True),
    ],
)
def test_coef_cell_consistency(row, ok):
    assert (exact.check_coef(row) == []) is ok, exact.check_coef(row)


def test_t_distribution_is_used_when_df_is_given():
    # z = 2.0: p = .046 under the normal, .061 under t with 10 df
    row = cell(coef="2.000", se="1.000", stars="**", thresholds=STARS)
    assert exact.check_coef(row) == []
    assert exact.check_coef({**row, "df": "10"}) != []


def test_unprintable_numbers_are_refused():
    with pytest.raises(ValueError, match="is not a number"):
        exact.check_coef(cell(coef="0.5a", se="0.2"))


def test_paragraphs_keep_their_first_line():
    assert exact.paragraphs("a\nb\n\n\nc\n") == [{"id": "L1", "text": "a b"}, {"id": "L5", "text": "c"}]


PAPER = (
    "We found t(28) = 2.20, p = .036 for the first test.\n\n"
    "The second was F(2, 57) = 3.10, p < .01.\n\n"
    "Scores averaged M = 5.27 (SD = 1.10, n = 28). Table 2 reports 0.50 (0.30)***.\n"
)


def make_run(tmp_path, means=(), coefs=()):
    (tmp_path / "paper.txt").write_text(PAPER)
    (tmp_path / "exact").mkdir()
    (tmp_path / "exact" / "means.jsonl").write_text("".join(json.dumps(r) + "\n" for r in means))
    (tmp_path / "exact" / "coefs.jsonl").write_text("".join(json.dumps(r) + "\n" for r in coefs))
    return tmp_path


MEAN = {"id": "m1", "quote": "M = 5.27 (SD = 1.10, n = 28)", "x": "5.27", "sd": "1.10", "n": "28"}
COEF = {
    "id": "t2",
    "quote": "0.50 (0.30)***",
    "coef": "0.50",
    "se": "0.30",
    "stars": "***",
    "thresholds": STARS,
}


def test_extracted_numbers_must_appear_in_their_quote(tmp_path, monkeypatch):
    monkeypatch.setattr(exact, "r_status", lambda: (False, "test"))
    _, problems = exact.run_exact(
        make_run(tmp_path, means=[{**MEAN, "x": "5.72"}], coefs=[{**COEF, "quote": "nope"}])
    )
    messages = [p.message for p in problems]
    assert "x '5.72' does not appear in its quote" in messages
    assert "quote is not in paper.txt" in messages


def test_table_cells_are_checked_without_r(tmp_path, monkeypatch):
    monkeypatch.setattr(exact, "r_status", lambda: (False, "Rscript is not installed"))
    summary, problems = exact.run_exact(make_run(tmp_path, coefs=[COEF]))
    assert problems == []
    assert summary["r"] == "Rscript is not installed" and summary["inconsistent"] == 1
    comment = json.loads((tmp_path / "candidates" / "exact.jsonl").read_text())
    assert comment["quote"] == "0.50 (0.30)***" and comment["goal"] == "consistency"
    assert comment["location"] == "line 5"


needs_r = pytest.mark.skipif(
    not exact.r_status()[0], reason="needs R with statcheck, scrutiny and retrodesign"
)


@needs_r
def test_statcheck_and_grim_through_r(tmp_path):
    summary, problems = exact.run_exact(make_run(tmp_path, means=[MEAN], coefs=[COEF]))
    assert problems == []
    assert summary["statcheck"] == 2 and summary["means"] == 2
    comments = [
        json.loads(line) for line in (tmp_path / "candidates" / "exact.jsonl").read_text().splitlines()
    ]
    titles = sorted(c["title"] for c in comments)
    assert titles == [
        "GRIM inconsistency",
        "GRIMMER inconsistency",
        "Reported p does not match its test statistic",
        "Table cell t2 does not add up",
    ]
    assert (
        main(["check", str(tmp_path / "candidates" / "exact.jsonl"), "--paper", str(tmp_path / "paper.txt")])
        == 0
    )


def test_plain_strips_markdown_html_and_typography():
    text = "*r*(48) = .08, *p* = .021; *t*<sub>1</sub> and \\[-.09, .26\\] with χ² and −0.5"
    assert exact.plain(text) == "r(48) = .08, p = .021; t 1  and [-.09, .26] with χ2 and -0.5"


def test_plain_handles_emphasis_over_operators_and_html_superscripts():
    assert exact.plain("χ<sup>2</sup>(3)=8.74, *p=*.033") == "χ2(3)=8.74, p=.033"
    assert exact.plain("*t*(32)=2.23, *p=*.033") == "t(32)=2.23, p=.033"


@pytest.mark.parametrize(
    "row, ok",
    [
        ({"id": "s", "parts": ["15", "12"], "total": "27"}, True),
        ({"id": "s", "parts": ["15", "12"], "total": "33"}, False),
        ({"id": "s", "parts": ["48.5", "30.3", "18.2"], "percent": True}, False),  # 97.0
        ({"id": "s", "parts": ["33.3", "33.3", "33.3"], "percent": True}, True),  # rounding
    ],
)
def test_sums(row, ok):
    assert (exact.check_sum(row) == []) is ok


RATE_ROW = {
    "id": "r1",
    "quote": "matched 4,112 of 5,000 treated and 3,870 of 5,000 control",
    "what": "match rate",
    "groups": [
        {"name": "treated", "k": "4,112", "n": "5,000"},
        {"name": "control", "k": "3,870", "n": "5,000"},
    ],
}


def test_differential_match_rate_is_flagged_and_similar_rates_are_not():
    from jaanch.exact import check_rates

    (found,) = check_rates(RATE_ROW)
    assert "match rate differs" in found and "82.2%" in found and "77.4%" in found
    similar = dict(
        RATE_ROW, groups=[{"name": "t", "k": "4112", "n": "5000"}, {"name": "c", "k": "4090", "n": "5000"}]
    )
    assert check_rates(similar) == []


def test_small_groups_use_fishers_exact_test():
    from jaanch.exact import check_rates

    row = dict(RATE_ROW, groups=[{"name": "t", "k": "6", "n": "6"}, {"name": "c", "k": "0", "n": "6"}])
    (found,) = check_rates(row)
    assert "Fisher's exact" in found


def test_assignment_counts_against_designed_shares():
    from jaanch.exact import check_rates

    row = {
        "id": "a",
        "quote": "",
        "groups": [{"name": "t", "n": "1,083", "share": 0.5}, {"name": "c", "n": "917", "share": 0.5}],
    }
    (found,) = check_rates(row)
    assert "expected 1000" in found
    balanced = dict(
        row, groups=[{"name": "t", "n": "1010", "share": 0.5}, {"name": "c", "n": "990", "share": 0.5}]
    )
    assert check_rates(balanced) == []


def test_impossible_counts_are_refused():
    from jaanch.exact import check_rates

    with pytest.raises(ValueError, match="greater than n"):
        check_rates(
            dict(RATE_ROW, groups=[{"name": "t", "k": "6", "n": "5"}, {"name": "c", "k": "1", "n": "5"}])
        )


@needs_r
def test_design_analysis_reproduces_gelman_and_carlin():
    # Their beauty-and-sex-ratio example: power 0.05, Type S 0.46, exaggeration 77.
    (hit,) = exact.run_r(
        {
            "statcheck": [],
            "grim": [],
            "grimmer": [],
            "debit": [],
            "design": [{"id": "gc", "A": 0.1, "s": 3.3, "alpha": 0.05}],
        }
    )["design"]
    assert round(hit["power"], 2) == 0.05 and round(hit["type_s"], 2) == 0.46 and round(hit["type_m"]) == 77


DESIGN_PAPER = """# Nudges
The reminder raised giving by 0.50 (SE = 0.20).
Our power analysis assumed an effect of 0.10.
The interaction with prior giving was 0.50 (SE = 0.20), and the main effect 0.40.
A large trial found 0.45 (SE = 0.05), against a benchmark of 0.40 from the pilot.
"""


@needs_r
def test_underpowered_significant_estimates_are_flagged_and_powered_ones_are_not(tmp_path):
    (tmp_path / "paper.txt").write_text(DESIGN_PAPER)
    (tmp_path / "exact").mkdir()
    rows = [
        {
            "id": "main",
            "quote": "raised giving by 0.50 (SE = 0.20)",
            "estimate": "0.50",
            "se": "0.20",
            "benchmark": "0.10",
            "benchmark_quote": "assumed an effect of 0.10",
            "benchmark_source": "power analysis",
        },
        {
            "id": "inter",
            "kind": "interaction",
            "quote": "The interaction with prior giving was 0.50 (SE = 0.20), and the main effect 0.40",
            "estimate": "0.50",
            "se": "0.20",
            "main_estimate": "0.40",
        },
        {
            "id": "big",
            "quote": "found 0.45 (SE = 0.05)",
            "estimate": "0.45",
            "se": "0.05",
            "benchmark": "0.40",
            "benchmark_quote": "a benchmark of 0.40 from the pilot",
            "benchmark_source": "pilot",
        },
    ]
    (tmp_path / "exact" / "design.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    summary, problems = exact.run_exact(tmp_path)
    assert problems == [] and summary["design"] == 3
    comments = {
        c["quote"]: c
        for c in map(json.loads, (tmp_path / "candidates" / "exact.jsonl").read_text().splitlines())
    }
    main = comments[rows[0]["quote"]]
    assert main["severity"] == "major" and "4.8-fold" in main["message"] and "5.0 times" in main["message"]
    assert comments[rows[1]["quote"]]["severity"] == "minor"
    assert rows[2]["quote"] not in comments


def test_design_benchmark_must_come_from_the_paper(tmp_path, monkeypatch):
    monkeypatch.setattr(exact, "r_status", lambda: (False, "test"))
    (tmp_path / "paper.txt").write_text(DESIGN_PAPER)
    (tmp_path / "exact").mkdir()
    row = {
        "id": "main",
        "quote": "raised giving by 0.50 (SE = 0.20)",
        "estimate": "0.50",
        "se": "0.20",
        "benchmark": "0.10",
        "benchmark_quote": "a plausible effect is 0.10",
    }
    (tmp_path / "exact" / "design.jsonl").write_text(json.dumps(row) + "\n")
    _, problems = exact.run_exact(tmp_path)
    assert [p.message for p in problems] == ["needs a benchmark and a benchmark_quote from the paper"]
