import json

from jaanch import controls

PAPER = "a\n"


def setup(tmp_path):
    (tmp_path / "xref").mkdir()
    (tmp_path / "candidates").mkdir()
    facts = [
        {"id": "f1", "key": "sample:s1:size", "value": "374", "quote": "374 students", "location": "Methods"},
        {
            "id": "f2",
            "key": "sample:s1:size",
            "value": "N = 374",
            "quote": "N = 374 in total",
            "location": "Results",
        },
        {"id": "f3", "key": "design:s1:waves", "value": "five", "quote": "five waves", "location": "Methods"},
        {
            "id": "f4",
            "key": "design:s1:waves",
            "value": "four",
            "quote": "four waves",
            "location": "Abstract",
        },
    ]
    (tmp_path / "xref" / "facts.jsonl").write_text("".join(json.dumps(f) + "\n" for f in facts))
    real = [{"id": "xref_001", "quote": "four waves", "message": "[group: design:s1:waves] x"}]
    (tmp_path / "candidates" / "xref.jsonl").write_text("".join(json.dumps(c) + "\n" for c in real))
    return tmp_path


def test_controls_come_only_from_agreeing_mentions_and_are_kept_apart(tmp_path):
    result = controls.make_controls(setup(tmp_path), "xref", share=3)
    assert result["controls"]["same_value"] == 1 and result["available"]["same_value"] == 1
    batch = [json.loads(line) for line in (tmp_path / "verify" / "batch_xref.jsonl").read_text().splitlines()]
    decoy = [c for c in batch if c["id"] != "xref_001" and "sample:s1:size" in c["message"]][0]
    assert decoy["quote"] == "N = 374 in total"
    kinds = json.loads((tmp_path / "verify" / "controls_xref.json").read_text())
    assert kinds[decoy["id"]] == "same_value" and "xref_001" not in kinds


def test_other_subject_pairs_compare_one_aspect_across_subjects():
    facts = [
        {"id": "a", "key": "sample:study1:size", "value": "374", "quote": "q1", "location": "x"},
        {"id": "b", "key": "sample:study2:size", "value": "1,200", "quote": "q2", "location": "y"},
        {"id": "c", "key": "sample:study3:size", "value": "374", "quote": "q3", "location": "z"},
    ]
    pairs = controls._cross_subject_pairs(facts)
    assert [(a["id"], b["id"]) for a, b in pairs] == [("a", "b")]  # one pair per aspect, to spread decoys


def test_scores_separate_controls_from_real_candidates(tmp_path):
    controls.make_controls(setup(tmp_path), "xref", share=3)
    kinds = json.loads((tmp_path / "verify" / "controls_xref.json").read_text())
    verdicts = [{"id": "xref_001", "verdict": "confirmed"}] + [{"id": i, "verdict": "refuted"} for i in kinds]
    (tmp_path / "verify" / "verdicts_xref.jsonl").write_text("".join(json.dumps(v) + "\n" for v in verdicts))
    score = controls.score_controls(tmp_path, "xref")
    assert score["real"] == {"confirmed": 1, "plausible": 0, "refuted": 0}
    assert all(k["refuted"] == k["controls"] for k in score["controls"].values())
