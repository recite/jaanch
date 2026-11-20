import json

from jaanch import lit
from jaanch.cli import main


def work(n, refs=(), doi=None, abstract="Text reminders raised turnout by 4.1 points among 6,000 voters."):
    return {
        "id": f"https://openalex.org/W{n}",
        "doi": f"https://doi.org/{doi}" if doi else None,
        "display_name": f"Paper {n}",
        "publication_year": 2020,
        "authorships": [{"author": {"display_name": "A. Author"}}],
        "abstract_inverted_index": {word: [i] for i, word in enumerate(abstract.split())},
        "referenced_works": [f"https://openalex.org/W{r}" for r in refs],
        "best_oa_location": None,
        "cited_by_count": 3,
    }


ROW = {
    "id": "W1",
    "citation": "Author (2020)",
    "question": "Do reminders raise turnout?",
    "designs": [{"design": "experiment", "quote": "Text reminders raised turnout"}],
    "data": {"source": "voter file", "quote": "among 6,000 voters."},
    "sample": {"n": "6,000", "unit": "voter", "quote": "among 6,000 voters."},
    "x": {"variable": "text reminder", "measured_how": "assignment", "quote": "Text reminders raised"},
    "y": {"variable": "turnout", "measured_how": "not stated", "quote": "raised turnout by 4.1"},
    "results": [
        {
            "estimate": "4.1",
            "uncertainty": "not stated",
            "units": "points",
            "quote": "4.1 points",
            "location": "abstract",
        }
    ],
}


def setup(tmp_path, rows=(ROW,), decision="include"):
    lit.add_works(tmp_path, [work(1, refs=[2, 3], doi="10.1/a"), work(2)], "search:openalex:reminders")
    (tmp_path / lit.SCREEN).write_text(
        json.dumps({"id": "W1", "decision": decision, "reason": "turnout RCT"}) + "\n"
    )
    (tmp_path / lit.ROWS).write_text("".join(json.dumps(row) + "\n" for row in rows))
    return tmp_path


def test_found_by_accumulates_without_duplicates(tmp_path):
    assert lit.add_works(tmp_path, [work(1)], "search:a") == 1
    assert lit.add_works(tmp_path, [work(1), work(2)], "search:b") == 1
    candidates = lit.load_candidates(tmp_path)
    assert candidates["W1"]["found_by"] == ["search:a", "search:b"]
    assert candidates["W1"]["abstract"].startswith("Text reminders raised turnout")


def test_backward_expansion_fetches_only_unknown_references(tmp_path, monkeypatch):
    setup(tmp_path)
    asked = []
    monkeypatch.setattr(lit, "_by_ids", lambda ids, key="openalex_id": asked.append(ids) or [work(3)])
    counts = lit.expand(tmp_path, ["W1"], forward=False)
    assert asked == [["W3"]]
    assert lit.load_candidates(tmp_path)["W3"]["found_by"] == ["cited_by:W1"]
    assert counts["backward"] == 1
    assert lit.load_candidates(tmp_path)["W2"]["found_by"] == ["search:openalex:reminders", "cited_by:W1"]


def test_valid_row_passes(tmp_path):
    assert lit.check_rows(setup(tmp_path)) == []


def test_row_problems_are_reported(tmp_path):
    bad = json.loads(json.dumps(ROW))
    bad["results"][0]["quote"] = "a 9.9 point effect"
    bad["designs"][0]["design"] = "regression"
    problems = [p.message for p in lit.check_rows(setup(tmp_path, rows=[bad]))]
    assert any("does not match" in m for m in problems)
    bad["designs"][0]["design"] = "experiment"
    problems = [p.message for p in lit.check_rows(setup(tmp_path, rows=[bad]))]
    assert problems == ["W1/results[0]: quote is not in the work's text"]


def test_row_for_an_excluded_work_is_a_problem(tmp_path):
    problems = [p.message for p in lit.check_rows(setup(tmp_path, decision="exclude"))]
    assert problems == ["W1 was not included at screening"]


def test_recall_resolves_dois_and_lists_misses(tmp_path):
    setup(tmp_path)
    result = lit.recall(tmp_path, ["10.1/A", "W2", "W99"])
    assert result["found"] == 2 and result["included"] == 1 and result["missed"] == ["W99"]


def test_status_and_check_commands(tmp_path, capsys):
    setup(tmp_path)
    assert main(["lit", "status", str(tmp_path)]) == 0
    status = json.loads(capsys.readouterr().out)
    assert status["candidates"] == 2 and status["included"] == 1 and status["rows"] == 1
    assert main(["lit", "check", str(tmp_path)]) == 0


def test_prefilter_excludes_only_unscreened_works_without_any_term(tmp_path):
    lit.add_works(tmp_path, [work(1), work(2, abstract="A study of soil erosion in Kenya.")], "search:x")
    assert lit.prefilter(tmp_path, ["turnout", "vot"]) == 1
    decisions = lit.screen_decisions(tmp_path)
    assert list(decisions) == ["W2"] and decisions["W2"]["reason"].startswith("prefilter")
    assert [row["id"] for row in lit.unscreened(tmp_path)] == ["W1"]


def test_merge_screen_validates_decisions(tmp_path):
    lit.add_works(tmp_path, [work(1), work(2)], "search:x")
    out = tmp_path / "out.jsonl"
    out.write_text(
        json.dumps({"id": "W1", "decision": "include", "reason": "RCT"})
        + "\n"
        + json.dumps({"id": "W9", "decision": "include", "reason": "x"})
        + "\n"
        + json.dumps({"id": "W2", "decision": "maybe", "reason": "x"})
        + "\n"
    )
    merged, problems = lit.merge_screen(tmp_path, [out])
    messages = [p.message for p in problems]
    assert merged == 1
    assert "W9 is not a candidate" in messages
    assert any("is not one of" in m for m in messages)
    assert "1 candidates still unscreened" in messages


def test_versions_group_a_paper_and_its_working_paper(tmp_path):
    article = work(1)
    article["display_name"] = "Timing Is Everything? Primacy and Recency Effects"
    article["type"] = "article"
    preprint = work(2)
    preprint["display_name"] = "Timing is everything: primacy and recency effects"
    preprint["type"] = "preprint"
    other = work(3)
    other["display_name"] = "Party at the Mailbox"
    lit.add_works(tmp_path, [article, preprint, other], "search:x")
    assert lit.versions(tmp_path) == {"W1": ["W1", "W2"], "W3": ["W3"]}


def test_merge_screen_command_takes_folder_first(tmp_path, capsys):
    lit.add_works(tmp_path, [work(1)], "search:x")
    out = tmp_path / "out.jsonl"
    out.write_text(json.dumps({"id": "W1", "decision": "include", "reason": "RCT"}) + "\n")
    assert main(["lit", "merge-screen", str(tmp_path), str(out)]) == 0
    assert lit.screen_decisions(tmp_path)["W1"]["decision"] == "include"


def test_forward_expansion_attributes_each_citer_to_the_seeds_it_cites(tmp_path, monkeypatch):
    lit.add_works(tmp_path, [work(1), work(2)], "search:x")
    queries = []

    class Query:
        def filter(self, **kwargs):
            queries.append(kwargs)
            return self

        def select(self, fields):
            return self

        def paginate(self, **kwargs):
            return iter([[work(5, refs=[1]), work(6, refs=[1, 2])]])

    monkeypatch.setattr(lit, "_openalex", lambda: Query)
    counts = lit.expand(tmp_path, ["W1", "W2"], backward=False)
    candidates = lit.load_candidates(tmp_path)
    assert queries == [{"cites": "W1|W2"}]
    assert counts["forward"] == 2
    assert candidates["W5"]["found_by"] == ["cites:W1"]
    assert candidates["W6"]["found_by"] == ["cites:W1", "cites:W2"]


def test_prefilter_second_set_is_waived_for_short_abstracts(tmp_path):
    long_observational = "Turnout rose " + " ".join(f"word{n}" for n in range(60))
    soil = "Soil erosion " + " ".join(f"term{n}" for n in range(60))
    works = [work(1, abstract=long_observational), work(2, abstract="Voter turnout."), work(3, abstract=soil)]
    lit.add_works(tmp_path, works, "s")
    assert lit.prefilter(tmp_path, ["turnout"], also=["experiment", "random"]) == 2
    assert sorted(lit.screen_decisions(tmp_path)) == ["W1", "W3"]


import pytest  # noqa: E402


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/x.pdf",
        "http://10.0.0.5/x.pdf",
        "http://169.254.169.254/latest",
        "http://192.168.1.1/x.pdf",
        "http://localhost/x.pdf",
    ],
)
def test_non_public_addresses_are_refused_before_connecting(url):
    from requests_hardened.ip_filter import InvalidIPAddress

    with pytest.raises(InvalidIPAddress):
        lit.get_public(url)


@pytest.mark.parametrize("url", ["file:///etc/passwd", "ftp://8.8.8.8/x.pdf"])
def test_non_http_schemes_are_refused(url):
    with pytest.raises(ValueError, match="only http and https"):
        lit.get_public(url)
