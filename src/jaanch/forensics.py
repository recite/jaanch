"""Forensic screens on deposited data: patterns that real collection rarely leaves.

Three screens, each a pattern a reviewer should ask the authors to explain,
never a finding of misconduct by itself:

- exact duplicate records, once columns unique to each row (ids,
  timestamps) are set aside;
- near-duplicate records: the share of records that match another record on
  at least 85% of the columns both answered informatively (Kuriakose and
  Robbins 2016, who found more than 5% of such records in many survey
  datasets with known problems). Simmons, Mercer, Schwarzer and Kennedy
  (2016) showed that raw match rates run high in genuine surveys with many
  questions, few answer options and skip patterns, so a value that most
  records share in a column (a skip or inapplicable code) is not counted as
  a match. Calibration on genuine data (ANES 1992 and 2016, GSS 2010 panel,
  an MTurk study): 0.0-1.0% of records flagged, against 5.03% for ANES 1992
  before that exclusion. Copies of 3-10% of ANES 2016 records with 2-20% of
  their columns redrawn were all flagged;
- terminal digits of recorded measurements: the last digit of values with
  three or more significant digits is close to uniform in measured data, and
  people inventing numbers favor some digits (Mosimann, Wiseman and Edelman
  1995). Heaping on 0 and 5 from rounding by respondents fails it too.
  Only values printed with a decimal point in text files are tested: binary
  formats keep floats, not the digits recorded, and integer columns are
  mostly codes. On genuine Stata files the test flagged 11-141 columns of
  codes, strata and weights before this restriction, and none after.

The percent-match statistic exists only as a Stata command and scrutiny's
duplicate functions count values within columns, so the screens are written
here on pandas and scipy. Reading files needs the data extra:
pip install 'jaanch[data]'.
"""

import json
from collections import Counter
from pathlib import Path

from scipy import stats

from jaanch.check import read_jsonl

FOLDER = "forensics"
RESULTS = "results.jsonl"
CANDIDATES = Path("candidates") / "forensics.jsonl"
READABLE = {".csv", ".tsv", ".dta", ".sav", ".parquet", ".xlsx", ".xls"}
MAX_BYTES = 200_000_000
NEAR_MATCH = 0.85
NEAR_SHARE = 0.05
DOMINANT = 0.5
MIN_COLUMNS = 10
MAX_ROWS_NEAR = 20_000
DIGIT_MIN_VALUES = 200
DIGIT_ALPHA = 0.001
# Cells compared at once in the near-duplicate scan, to bound memory (about 3 bytes a cell).
BLOCK_CELLS = 30_000_000


def read_table(path: Path):
    """The file as a DataFrame; text formats are read as strings so recorded digits survive."""
    import pandas as pd

    suffix = path.suffix.casefold()
    if suffix in (".csv", ".tsv"):
        return pd.read_csv(path, sep="\t" if suffix == ".tsv" else ",", dtype=str, keep_default_na=False)
    if suffix == ".dta":
        return pd.read_stata(path, convert_categoricals=False)
    if suffix == ".sav":
        return pd.read_spss(path, convert_categoricals=False)
    if suffix == ".parquet":
        return pd.read_parquet(path)
    return pd.read_excel(path)


def _substantive(frame):
    """Columns that are not unique to every row and not entirely empty."""
    n = len(frame)
    keep = []
    for column in frame.columns:
        values = frame[column].replace("", None)
        distinct = values.nunique(dropna=True)
        if 0 < distinct < n:
            keep.append(column)
    return frame[keep]


def exact_duplicates(frame) -> int:
    """Records identical to another on every substantive column."""
    body = _substantive(frame)
    if body.shape[1] < MIN_COLUMNS:
        return 0
    return int(body.duplicated(keep=False).sum())


def near_duplicate_share(frame) -> tuple[float, int] | None:
    """Share and count of records matching some other record on at least NEAR_MATCH of columns."""
    import numpy as np
    import pandas as pd

    body = _substantive(frame)
    n, k = body.shape
    if k < MIN_COLUMNS or n < 2 or n > MAX_ROWS_NEAR:
        return None
    codes = np.empty((n, k), dtype=np.int64)
    for j, column in enumerate(body.columns):
        codes[:, j], _ = pd.factorize(body[column].replace("", None))
    # A value most records share (a skip or inapplicable code, a common
    # answer) makes records match without saying anything about copying.
    for j in range(k):
        values, counts = np.unique(codes[:, j][codes[:, j] >= 0], return_counts=True)
        if len(counts) and counts.max() > DOMINANT * n:
            codes[codes[:, j] == values[counts.argmax()], j] = -1
    valid = codes >= 0
    best = np.zeros(n)
    chunk = max(1, BLOCK_CELLS // (n * k))
    for start in range(0, n, chunk):
        block = slice(start, min(start + chunk, n))
        both = valid[block, None, :] & valid[None, :, :]
        same = (codes[block, None, :] == codes[None, :, :]) & both
        # The share of the columns both records answered informatively; a pair
        # with too few such columns cannot be judged and counts as no match.
        shared = both.sum(axis=2)
        share = np.where(shared >= MIN_COLUMNS, same.sum(axis=2) / np.maximum(shared, 1), 0.0)
        for offset in range(share.shape[0]):
            share[offset, start + offset] = 0
        best[block] = share.max(axis=1)
    flagged = int((best >= NEAR_MATCH).sum())
    return flagged / n, flagged


def terminal_digits(frame) -> list[dict]:
    """Columns of recorded measurements whose last digits are far from uniform."""
    import pandas as pd

    found = []
    for column in frame.columns:
        # Only digits as printed: binary formats store floats, whose shortest
        # repr is not what was recorded, and codes and ids are not measurements.
        if not pd.api.types.is_string_dtype(frame[column]):
            continue
        values = [str(v).strip() for v in frame[column] if str(v).strip() not in ("", "nan", "None")]
        if sum("." in v for v in values) < 0.9 * len(values):
            continue
        digits = [v.lstrip("-").replace(".", "") for v in values]
        usable = [d for d in digits if d.isdigit() and len(d.lstrip("0")) >= 3]
        if len(usable) < DIGIT_MIN_VALUES or len(usable) < 0.9 * len(values) or len(set(values)) < 50:
            continue
        counts = Counter(d[-1] for d in usable)
        observed = [counts.get(str(i), 0) for i in range(10)]
        p = stats.chisquare(observed).pvalue
        if p < DIGIT_ALPHA:
            found.append({"column": str(column), "n": len(usable), "counts": observed, "p": p})
    return found


def screen(frame) -> dict:
    near = near_duplicate_share(frame)
    return {
        "rows": len(frame),
        "columns": frame.shape[1],
        "exact_duplicates": exact_duplicates(frame),
        "near_duplicates": None if near is None else {"share": near[0], "count": near[1]},
        "terminal_digits": terminal_digits(frame),
    }


def _comment(number: int, title: str, quote: str, location: str, message: str, severity: str) -> dict:
    return {
        "id": f"forensics_{number:03d}",
        "goal": "consistency",
        "title": title,
        "quote": quote,
        "location": location,
        "message": message,
        "suggestion": "Explain how these records arose (collection, merging, data entry), and show the "
        "results with them handled.",
        "severity": severity,
        "kind": "evidence/data",
        "fix_effort": "rework",
    }


def findings(name: str, result: dict) -> list[tuple[str, str, str]]:
    """(title, message, severity) for what a screen found in one file."""
    out = []
    if result["exact_duplicates"]:
        out.append(
            (
                "Duplicate records in the deposited data",
                f"{name} has {result['exact_duplicates']} of {result['rows']} records identical to another "
                "record on every column that is not unique to each row.",
                "major",
            )
        )
    near = result["near_duplicates"]
    if near and near["share"] > NEAR_SHARE:
        out.append(
            (
                "Near-duplicate records in the deposited data",
                f"In {name}, {near['count']} of {result['rows']} records ({near['share']:.1%}) match another "
                f"record on at least {NEAR_MATCH:.0%} of their columns; above {NEAR_SHARE:.0%} is unusual in "
                "genuine survey data (Kuriakose and Robbins 2016).",
                "major",
            )
        )
    for hit in result["terminal_digits"]:
        out.append(
            (
                "Last digits of recorded values are not uniform",
                f"In {name}, column {hit['column']}: the last digits of {hit['n']} values occur "
                f"{hit['counts']} times for 0-9 (chi-square p = {hit['p']:.2g}). Measured values with three "
                "or more significant digits end in each digit about equally often; values rounded by "
                "respondents or invented ones do not.",
                "minor",
            )
        )
    return out


def run_forensics(run_dir: Path) -> dict:
    """Screen every readable deposited data file. Comments quote the paper's description of the data."""
    inventory = json.loads((run_dir / "inventory.json").read_text())
    root = Path(inventory["root"])
    model = json.loads((run_dir / "map.json").read_text()) if (run_dir / "map.json").exists() else {}
    sources = model.get("data_sources", [])
    folder = run_dir / FOLDER
    folder.mkdir(exist_ok=True)
    results, comments, skipped = [], [], []
    for name in inventory["data"]["files"]:
        path = root / name
        if path.suffix.casefold() not in READABLE:
            continue
        if path.stat().st_size > MAX_BYTES:
            skipped.append(f"{name}: larger than {MAX_BYTES // 1_000_000} MB")
            continue
        try:
            frame = read_table(path)
        except ImportError as error:
            raise SystemExit(f"reading data needs the data extra (pip install 'jaanch[data]'): {error}")
        except Exception as error:  # noqa: BLE001 - a deposit can hold any malformed file
            skipped.append(f"{name}: {error}")
            continue
        result = {"file": name, **screen(frame)}
        results.append(result)
        source = next((s for s in sources if name in s.get("files", [])), sources[0] if sources else None)
        for title, message, severity in findings(name, result):
            if source:
                location = f"data source {source['name']}"
                comments.append(
                    _comment(len(comments) + 1, title, source["quote"], location, message, severity)
                )
    (folder / RESULTS).write_text("".join(json.dumps(r) + "\n" for r in results))
    (run_dir / CANDIDATES).parent.mkdir(exist_ok=True)
    (run_dir / CANDIDATES).write_text("".join(json.dumps(c) + "\n" for c in comments))
    unquoted = sum(len(findings(r["file"], r)) for r in results) - len(comments)
    return {"files": len(results), "skipped": skipped, "comments": len(comments), "unquoted": unquoted}


def load_results(run_dir: Path) -> list[dict]:
    return read_jsonl(run_dir / FOLDER / RESULTS)
