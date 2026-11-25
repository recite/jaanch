import json

import numpy as np
import pandas as pd
import pytest

from jaanch import forensics


def survey(n=400, k=15, seed=0):
    rng = np.random.default_rng(seed)
    frame = pd.DataFrame({f"q{j}": rng.integers(1, 8, n).astype(str) for j in range(k)})
    frame.insert(0, "id", [str(i) for i in range(n)])
    frame["income"] = [f"{v:.2f}" for v in rng.lognormal(10, 0.6, n)]
    return frame


def test_genuine_looking_data_raise_nothing():
    result = forensics.screen(survey())
    assert result["exact_duplicates"] == 0
    assert result["near_duplicates"]["share"] < forensics.NEAR_SHARE
    assert result["terminal_digits"] == []
    assert forensics.findings("s.csv", result) == []


def test_copied_records_are_found_though_their_ids_differ():
    frame = survey()
    copies = frame.iloc[:10].copy()
    copies["id"] = [str(1000 + i) for i in range(10)]
    result = forensics.screen(pd.concat([frame, copies], ignore_index=True))
    assert result["exact_duplicates"] == 20


def test_records_copied_and_lightly_edited_are_near_duplicates():
    frame = survey()
    edited = frame.iloc[:40].copy()
    edited["id"] = [str(2000 + i) for i in range(40)]
    edited["q0"] = "9"
    edited["q1"] = "9"
    result = forensics.screen(pd.concat([frame, edited], ignore_index=True))
    assert result["exact_duplicates"] == 0
    assert result["near_duplicates"]["count"] == 80
    (finding,) = forensics.findings("s.csv", result)
    assert finding[0] == "Near-duplicate records in the deposited data"


def test_invented_last_digits_fail_and_heaping_does_too():
    rng = np.random.default_rng(1)
    frame = survey()
    frame["income"] = [
        f"{v / 10:.1f}" for v in rng.integers(100, 999, 400) // 10 * 10 + rng.choice([3, 7], 400)
    ]
    (hit,) = forensics.screen(frame)["terminal_digits"]
    assert hit["column"] == "income" and hit["p"] < forensics.DIGIT_ALPHA


def test_codes_and_integers_are_not_digit_tested():
    rng = np.random.default_rng(2)
    frame = survey()
    frame["county"] = [f"{v:05d}" for v in rng.choice([6037, 6059, 6073], 400)]
    assert forensics.screen(frame)["terminal_digits"] == []


def test_run_quotes_the_papers_description_of_the_data(tmp_path):
    frame = survey()
    copies = frame.iloc[:10].copy()
    copies["id"] = [str(1000 + i) for i in range(10)]
    (tmp_path / "data").mkdir()
    pd.concat([frame, copies]).to_csv(tmp_path / "data" / "s.csv", index=False)
    run = tmp_path / "run"
    run.mkdir()
    (run / "inventory.json").write_text(
        json.dumps({"root": str(tmp_path), "data": {"files": ["data/s.csv"]}})
    )
    source = {
        "name": "panel",
        "kind": "survey",
        "quote": "We surveyed 400 respondents",
        "files": ["data/s.csv"],
    }
    (run / "map.json").write_text(json.dumps({"data_sources": [source]}))
    summary = forensics.run_forensics(run)
    assert summary == {"files": 1, "skipped": [], "comments": 1, "unquoted": 0}
    (comment,) = map(json.loads, (run / "candidates" / "forensics.jsonl").read_text().splitlines())
    assert comment["quote"] == "We surveyed 400 respondents" and "20 of 410" in comment["message"]


@pytest.mark.parametrize("suffix", [".dta", ".parquet"])
def test_binary_formats_are_read(tmp_path, suffix):
    frame = survey(n=50).astype({"q0": int})
    path = tmp_path / f"s{suffix}"
    frame.to_stata(path, write_index=False) if suffix == ".dta" else frame.to_parquet(path)
    assert len(forensics.read_table(path)) == 50
