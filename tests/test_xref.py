import json

from jaanch import xref
from jaanch.cli import main

PAPER = (
    "Participants were 374 undergraduates from the participant pool.\n"
    "Our general population sample of 374 adults supports generalization.\n"
    "We expected anxiety to increase sacrifice.\n"
)


def run(tmp_path, facts):
    (tmp_path / "paper.txt").write_text(PAPER)
    (tmp_path / "xref").mkdir()
    (tmp_path / "xref" / "facts.jsonl").write_text("".join(json.dumps(f) + "\n" for f in facts))
    return tmp_path


def fact(i, key, value, quote):
    return {"id": i, "key": key, "value": value, "quote": quote, "location": "x"}


FACTS = [
    fact(
        "f1",
        "sample:study1:population",
        "undergraduate participant pool",
        "374 undergraduates from the participant pool",
    ),
    fact(
        "f2", "sample:study1:population", "general population", "Our general population sample of 374 adults"
    ),
    fact("f3", "sample:study1:size", "374", "374 undergraduates"),
    fact("f4", "sample:study1:size", "N = 374", "sample of 374 adults"),
    fact(
        "f5",
        "hypothesis:h1:direction",
        "anxiety increases sacrifice",
        "We expected anxiety to increase sacrifice.",
    ),
]


def test_conflicting_values_are_grouped_and_equal_numbers_are_not(tmp_path):
    summary, problems = xref.run_xref(run(tmp_path, FACTS))
    assert problems == []
    groups = [json.loads(line) for line in (tmp_path / "xref" / "groups.jsonl").read_text().splitlines()]
    assert [g["key"] for g in groups] == ["sample:study1:population"]
    assert summary == {"facts": 5, "keys": 3, "keys_stated_twice_or_more": 2, "conflicts": 1}


def test_bad_keys_and_unquoted_facts_are_refused(tmp_path):
    bad = [
        fact("f1", "Sample size", "374", "374 undergraduates"),
        fact("f2", "sample:s1:size", "374", "not in paper"),
    ]
    _, problems = xref.run_xref(run(tmp_path, bad))
    messages = [p.message for p in problems]
    assert any("must be <kind>:<subject>" in m for m in messages)
    assert "quote is not in paper.txt" in messages


def test_xref_command(tmp_path):
    assert main(["xref", str(run(tmp_path, FACTS))]) == 0


def test_comments_must_name_a_conflict_group(tmp_path):
    run(tmp_path, FACTS)
    (tmp_path / "candidates").mkdir()
    comments = [
        {"message": "[group: sample:study1:population] The methods say a participant pool."},
        {"message": "[group: sample:study1:size] equal values"},
        {"message": "No tag."},
    ]
    (tmp_path / "candidates" / "xref.jsonl").write_text("".join(json.dumps(c) + "\n" for c in comments))
    _, problems = xref.run_xref(tmp_path)
    assert [p.message for p in problems] == [
        "sample:study1:size is not a conflict group",
        "message must start with [group: <key>]",
    ]


def test_long_sections_without_facts_are_reported(tmp_path):
    (tmp_path / "paper.txt").write_text(
        "# Methods\n" + "word " * 200 + "\n# Results\nWe expected anxiety to increase sacrifice.\n"
    )
    (tmp_path / "xref").mkdir()
    facts = [
        fact("f1", "hypothesis:h1:direction", "anxiety up", "We expected anxiety to increase sacrifice.")
    ]
    (tmp_path / "xref" / "facts.jsonl").write_text(json.dumps(facts[0]) + "\n")
    _, problems = xref.run_xref(tmp_path)
    assert [p.where for p in problems] == ["section '# Methods' (lines 1-2)"]
