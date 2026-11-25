"""Exact checks: arithmetic on numbers a paper reports, done by code rather than by a model reading.

Each check has two halves. Extraction finds the numbers: statcheck reads
APA-style results from the text itself; means and regression cells are
written by an extractor to <run>/exact/means.jsonl and coefs.jsonl, each
value kept as printed (a string, so 1.40 keeps its two decimals) with the
verbatim quote it came from. Computation then decides consistency:

- p-values from test statistics: R statcheck (validated; Nuijten et al.)
- GRIM, GRIMMER, DEBIT for means and SDs: R scrutiny
- rates by group (match, response or retention rates by arm) and
  assignment counts against the designed shares: here, as chi-square tests
  on reported counts (scipy).
- coefficient, SE, stars, t, p and confidence interval within one table
  cell: here. No maintained package covers regression tables; the math is
  a few lines on scipy, and every bound accounts for rounding, so a cell is
  flagged only when no unrounded values could produce what is printed.
- design analysis (power, Type S and Type M error of a significant estimate
  against a benchmark true effect the paper states, or half the main effect
  for an interaction): R retrodesign (Gelman and Carlin 2014).

Findings go to candidates/exact.jsonl in the comment schema, so the skeptic
and the editor treat them like any other finding.
"""

import json
import os
import re
import shutil
import subprocess
import tempfile
from importlib.resources import files
from pathlib import Path

from scipy import stats

from jaanch.check import Problem, anchor_quote, locate_line, normalize_text, read_jsonl

EXACT = "exact"
MEANS = "means.jsonl"
COEFS = "coefs.jsonl"
SUMS = "sums.jsonl"
RATES = "rates.jsonl"
DESIGN = "design.jsonl"
# A significant estimate is flagged when, against the benchmark effect, the
# design would exaggerate a significant result at least this many times on
# average (power is then about 0.3 or less at alpha .05). From 3 it is major.
EXAGGERATION_FLAG = 2.0
EXAGGERATION_MAJOR = 3.0
# Gelman's benchmark for an interaction: half the size of the main effect.
INTERACTION_SHARE = 0.5
# One test per reported table of rates, so a conventional level without a
# multiplicity correction. Large online experiments use far stricter levels for
# sample ratio mismatch because they test thousands of experiments.
RATE_ALPHA = 0.01
RESULTS = "results.jsonl"
CANDIDATES = Path("candidates") / "exact.jsonl"
R_PACKAGES = ["statcheck", "scrutiny", "retrodesign", "jsonlite"]
NUMBER = re.compile(r"^-?\d*\.?\d+$")
# Rounding bounds are closed intervals: a value exactly at a bound is consistent.
# Without this, 0.02 - 0.03 = 0.010000000000000002 exceeds a 0.01 allowance.
EPS = 1e-9


def decimals(value: str) -> int:
    return len(value.split(".")[1]) if "." in value else 0


def half_unit(value: str) -> float:
    return 0.5 * 10 ** -decimals(value)


def _number(value: str, where: str, field: str) -> float:
    cleaned = value.strip().replace("−", "-").replace(",", "")
    if not NUMBER.match(cleaned):
        raise ValueError(f"{where}: {field} {value!r} is not a number as printed")
    return float(cleaned)


def r_status() -> tuple[bool, str]:
    """Whether Rscript and the packages are available, and why not."""
    if not shutil.which("Rscript"):
        return False, "Rscript is not installed"
    probe = "cat(all(sapply(c(%s), requireNamespace, quietly=TRUE)))" % ",".join(f'"{p}"' for p in R_PACKAGES)
    out = subprocess.run(["Rscript", "-e", probe], capture_output=True, text=True, env=_r_env(), timeout=60)
    if out.stdout.strip() != "TRUE":
        return False, f"R packages missing: install {', '.join(R_PACKAGES)} (CRAN)"
    return True, "ok"


def _r_env() -> dict:
    env = dict(os.environ)
    if os.environ.get("JAANCH_R_LIBS"):
        env["R_LIBS"] = os.environ["JAANCH_R_LIBS"]
    return env


def run_r(payload: dict) -> dict:
    script = files("jaanch").joinpath("r", "exact.R")
    with tempfile.TemporaryDirectory() as tmp:
        source, result = Path(tmp) / "in.json", Path(tmp) / "out.json"
        source.write_text(json.dumps(payload))
        subprocess.run(
            ["Rscript", str(script), str(source), str(result)],
            check=True,
            capture_output=True,
            env=_r_env(),
            timeout=600,
        )
        return json.loads(result.read_text())


MARKUP = [
    (re.compile(r"χ\s*(?:²|<sup>\s*2\s*</sup>|\^2|2)"), "χ2"),  # before tags are stripped
    (re.compile(r"<[^>]+>"), " "),  # HTML that pandoc writes for complex tables and subscripts
    # emphasis around a symbol, with or without its operator: *p*, _t_, **F**, *p=*
    (re.compile(r"(?<![\w*])[*_]{1,2}([A-Za-zχηω]{1,3}\s*[=<>]?)[*_]{1,2}"), r"\1"),
    (re.compile(r"\\([\[\]()*_])"), r"\1"),  # markdown escapes such as \[
    (re.compile(r"[\u00a0\u2009\u202f]"), " "),  # non-breaking and thin spaces
    (re.compile(r"[\u2212\u2013]"), "-"),  # minus sign and en dash used as minus
]


def plain(text: str) -> str:
    """Text as statcheck expects it: no markdown emphasis, HTML tags or typographic symbols.

    statcheck was built for text extracted from PDFs and HTML. A converted
    manuscript writes `*t*(28) = 2.20`, which it does not read.
    """
    for pattern, replacement in MARKUP:
        text = pattern.sub(replacement, text)
    return text


def paragraphs(text: str) -> list[dict]:
    """Blank-line paragraphs with their first line, the unit statcheck reads."""
    found, start, lines = [], 1, []
    for number, line in enumerate(text.splitlines(), start=1):
        if line.strip():
            if not lines:
                start = number
            lines.append(line)
        elif lines:
            found.append({"id": f"L{start}", "text": " ".join(lines)})
            lines = []
    if lines:
        found.append({"id": f"L{start}", "text": " ".join(lines)})
    return found


def _p_two_sided(z: float, df: float | None) -> float:
    if z == float("inf"):
        return 0.0
    return float(2 * (stats.t.sf(z, df) if df else stats.norm.sf(z)))


def _z_two_sided(p: float, df: float | None) -> float:
    """The |statistic| whose two-sided p is p."""
    return float(stats.t.isf(p / 2, df) if df else stats.norm.isf(p / 2))


def _critical(level: float, df: float | None) -> float:
    tail = (1 + level) / 2
    return float(stats.t.ppf(tail, df) if df else stats.norm.ppf(tail))


def check_coef(row: dict) -> list[str]:
    """Problems with one regression cell; empty when some unrounded values fit everything printed."""
    where = row["id"]
    b, hb = _number(row["coef"], where, "coef"), half_unit(row["coef"])
    df = float(row["df"]) if row.get("df") else None
    problems = []
    # Without an SE nothing can be checked: an interval alone may be
    # asymmetric (profile, bootstrap, Bayesian, Fisher-z), so its midpoint
    # need not equal the estimate. On the Dawes papers the midpoint-only test
    # flagged clean originals as often as planted errors.
    if not row.get("se"):
        return problems
    s, hs = _number(row["se"], where, "se"), half_unit(row["se"])
    low_s = s - hs
    z_min = max(abs(b) - hb, 0) / (s + hs)
    z_max = float("inf") if low_s <= 0 else (abs(b) + hb) / low_s
    p_low, p_high = _p_two_sided(z_max, df), _p_two_sided(z_min, df)
    se_low, se_high = s - hs, s + hs

    if "stars" in row and row.get("thresholds"):
        thresholds = sorted(row["thresholds"].items(), key=lambda item: -item[1])
        symbols = [symbol for symbol, _ in thresholds]
        stars = row["stars"].strip()
        if stars and stars not in symbols:
            problems.append(f"stars {stars!r} are not in the table's legend {row['thresholds']}")
        else:
            index = symbols.index(stars) if stars else -1
            upper = thresholds[index][1] if stars else 1.0
            lower = thresholds[index + 1][1] if index + 1 < len(thresholds) else 0.0
            if not stars:
                lower = thresholds[0][1]
            if p_high < lower - EPS or p_low >= upper + EPS:
                claimed = f"p < {upper}" if stars else f"p >= {lower}"
                if stars and lower > 0:
                    claimed = f"{lower} <= p < {upper}"
                problems.append(
                    f"stars {stars or '(none)'} claim {claimed}, but coef {row['coef']} and SE {row['se']} "
                    f"give p between {p_low:.4f} and {p_high:.4f} allowing for rounding"
                    + ("" if df else " (normal approximation; no df given)")
                )

    if row.get("t"):
        t, ht = abs(_number(row["t"], where, "t")), half_unit(row["t"])
        if t + ht < z_min - EPS or t - ht > z_max + EPS:
            problems.append(f"t = {row['t']} but coef/SE is between {z_min:.3f} and {z_max:.3f}")
    if row.get("p"):
        p_text = row["p"].lstrip("<=> ")
        p, hp = _number(p_text, where, "p"), half_unit(p_text)
        bound = row["p"].lstrip()[:1]
        if bound == "<" and p_low >= p:
            problems.append(f"p {row['p']} but coef/SE give p of at least {p_low:.4f}")
        elif bound not in "<>" and (p + hp < p_low - EPS or p - hp > p_high + EPS):
            problems.append(f"p = {row['p']} but coef/SE give p between {p_low:.4f} and {p_high:.4f}")
        # The reported p also limits the SE: |b| / SE must give a p that rounds to it.
        # Every number constrains the same unknowns, so they are tested together.
        if bound != ">":
            z_from_p_low = _z_two_sided(p + hp if bound != "<" else p, df)
            se_high = min(se_high, (abs(b) + hb) / z_from_p_low) if z_from_p_low > 0 else se_high
            if bound != "<" and p - hp > 0:
                se_low = max(se_low, (abs(b) - hb) / _z_two_sided(p - hp, df))

    if row.get("ci_low") and row.get("ci_high"):
        lo, hi = _number(row["ci_low"], where, "ci_low"), _number(row["ci_high"], where, "ci_high")
        hl, hh = half_unit(row["ci_low"]), half_unit(row["ci_high"])
        level = float(row.get("ci_level") or 0.95)
        if level > 1:
            level /= 100  # printed as "95"
        if not 0 < level < 1:
            raise ValueError(f"{where}: ci_level {row.get('ci_level')!r} is not a coverage level")
        crit = _critical(level, df)
        half_low, half_high = (hi - lo - hl - hh) / 2, (hi - lo + hl + hh) / 2
        if half_high < crit * se_low - EPS or half_low > crit * se_high + EPS:
            narrowed = (se_low, se_high) != (s - hs, s + hs)
            problems.append(
                f"the {level:.0%} interval's half-width ({(hi - lo) / 2:.4f}) does not match "
                f"{crit:.2f} x SE {row['se']}"
                + (f" (SE between {se_low:.4g} and {se_high:.4g} given the reported p)" if narrowed else "")
            )
        elif abs(b - (lo + hi) / 2) > hb + (hl + hh) / 2 + EPS:
            # The width matches estimate +/- z x SE, so this is a Wald interval,
            # which is symmetric by construction: an off-center estimate is an error.
            problems.append(
                f"the interval [{row['ci_low']}, {row['ci_high']}] has the width of estimate +/- "
                f"{crit:.2f} x SE but is centered on {(lo + hi) / 2:.4g}, not on {row['coef']}"
            )
    return problems


def check_sum(row: dict) -> list[str]:
    """Parts that must add up to a stated total (100 for percentages), allowing each for its rounding."""
    where = row["id"]
    parts = [_number(value, where, "part") for value in row["parts"]]
    slack = sum(half_unit(value) for value in row["parts"])
    if row.get("percent"):
        total, slack_total = 100.0, 0.0
    else:
        total, slack_total = _number(row["total"], where, "total"), half_unit(row["total"])
    gap = abs(sum(parts) - total)
    if gap > slack + slack_total + EPS:
        what = "percentages" if row.get("percent") else "parts"
        return [f"the {what} {', '.join(row['parts'])} sum to {sum(parts):g}, not {row.get('total', '100')}"]
    return []


def _count(value: str, where: str, field: str) -> int:
    number = _number(value.replace(",", ""), where, field)
    if number != int(number) or number < 0:
        raise ValueError(f"{where}: {field} {value!r} is not a count")
    return int(number)


def check_rates(row: dict) -> list[str]:
    """Rates that should not differ across groups, or assignment counts that should match designed shares.

    groups: [{"name", "k", "n"}] tests whether the share k/n is the same in
    every group (chi-square test of homogeneity; Fisher's exact test for two
    groups with an expected cell below 5). groups: [{"name", "n", "share"}]
    tests the counts n against the designed shares (chi-square goodness of fit).
    """
    where, groups = row["id"], row["groups"]
    if len(groups) < 2:
        raise ValueError(f"{where}: needs at least two groups")
    if all("share" in g for g in groups):
        observed = [_count(g["n"], where, "n") for g in groups]
        shares = [float(g["share"]) for g in groups]
        expected = [sum(observed) * s / sum(shares) for s in shares]
        p = stats.chisquare(observed, expected).pvalue
        if p < RATE_ALPHA:
            got = ", ".join(
                f"{g['name']} {o} (expected {e:.0f})" for g, o, e in zip(groups, observed, expected)
            )
            return [
                f"assignment counts {got} are unlikely under the designed shares (chi-square p = {p:.2g})"
            ]
        return []
    table = []
    for g in groups:
        k, n = _count(g["k"], where, "k"), _count(g["n"], where, "n")
        if k > n:
            raise ValueError(f"{where}: {g['name']} has k {k} greater than n {n}")
        table.append([k, n - k])
    if len(table) == 2 and min(stats.contingency.expected_freq(table).flatten()) < 5:
        p = stats.fisher_exact(table).pvalue
        test = "Fisher's exact"
    else:
        p = stats.chi2_contingency(table, correction=False).pvalue
        test = "chi-square"
    if p < RATE_ALPHA:
        what = row.get("what", "rate")
        got = ", ".join(f"{g['name']} {k / (k + m):.1%} ({k}/{k + m})" for g, (k, m) in zip(groups, table))
        return [f"The {what} differs across groups: {got} ({test} p = {p:.2g})"]
    return []


def design_request(row: dict) -> dict:
    """The true effect A, standard error s and df that a design.jsonl row asks retrodesign about.

    kind "benchmark": the estimate and SE, against a true effect the paper
    itself states (a power analysis assumption, a cited or meta-analytic
    estimate). kind "interaction": the interaction's estimate and SE, against
    half the main effect it modifies.
    """
    where = row["id"]
    estimate, se = _number(row["estimate"], where, "estimate"), _number(row["se"], where, "se")
    if se <= 0:
        raise ValueError(f"{where}: se must be positive")
    if row.get("kind", "benchmark") == "interaction":
        true = INTERACTION_SHARE * abs(_number(row["main_estimate"], where, "main_estimate"))
    else:
        true = abs(_number(row["benchmark"], where, "benchmark"))
    if true == 0:
        raise ValueError(f"{where}: the benchmark effect is zero")
    df = _number(str(row["df"]), where, "df") if row.get("df") else None
    return {"id": where, "A": true, "s": se, "alpha": 0.05, "df": df, "estimate": estimate}


def design_finding(row: dict, request: dict, hit: dict) -> tuple[str, str] | None:
    """Message and severity when a significant estimate comes from a design that would exaggerate it."""
    estimate, se, df = request["estimate"], request["s"], request["df"]
    if abs(estimate / se) < _critical(0.95, df) or hit["type_m"] < EXAGGERATION_FLAG:
        return None
    if row.get("kind") == "interaction":
        against = f"an interaction half the main effect ({request['A']:g})"
    else:
        against = f"the {row.get('benchmark_source', 'benchmark')} effect of {row['benchmark']}"
    message = (
        f"Against {against}, a design with standard error {row['se']} has power {hit['power']:.2f}. "
        f"A significant estimate from it overstates the true effect {hit['type_m']:.1f}-fold on average "
        f"and has the wrong sign with probability {hit['type_s']:.2f}. The reported {row['estimate']} is "
        f"{abs(estimate) / request['A']:.1f} times that effect."
    )
    return message, "major" if hit["type_m"] >= EXAGGERATION_MAJOR else "minor"


def _extraction_problems(rows: list[dict], fields: list[str], paper: str, name: str) -> list[Problem]:
    """Every extracted number must sit in its quote, and the quote in the paper."""
    problems = []
    for row in rows:
        where = f"exact/{name} {row.get('id')}"
        quote = row.get("quote", "")
        if not anchor_quote(quote, paper):
            problems.append(Problem(where, "quote is not in paper.txt"))
            continue
        for field in fields:
            value = row.get(field)
            if value and str(value).lstrip("<=> ").replace("−", "-") not in quote.replace("−", "-"):
                problems.append(Problem(where, f"{field} {value!r} does not appear in its quote"))
    return problems


DIFFERENCE_TITLES = ("Rates differ by group", "Assignment counts depart from the design")
DESIGN_TITLE = "Significant estimate from an underpowered design"


def _comment(number: int, title: str, row: dict, message: str, severity: str) -> dict:
    if title == DESIGN_TITLE:
        return {
            "id": f"exact_{number:03d}",
            "goal": "reasoning",
            "title": title,
            "quote": row["quote"],
            "location": row.get("location") or row.get("_line") or "paper.txt",
            "message": message,
            "suggestion": "Report a design analysis against a plausible effect, describe the estimate "
            "as likely inflated, and do not build further claims on its size.",
            "severity": severity,
            "kind": "substance/methodology",
            "fix_effort": "rework",
        }
    if title in DIFFERENCE_TITLES:
        return {
            "id": f"exact_{number:03d}",
            "goal": "completeness",
            "title": title,
            "quote": row["quote"],
            "location": row.get("location") or row.get("_line") or "paper.txt",
            "message": message
            + ". A difference this large acts like differential attrition or measurement: the comparison "
            "is between groups that no longer match the ones assigned.",
            "suggestion": "Report the difference, test whether it changes the main estimate "
            "(bounds, reweighting), and explain its source.",
            "severity": severity,
            "kind": "substance/methodology",
            "fix_effort": "new_work",
        }
    return {
        "id": f"exact_{number:03d}",
        "goal": "consistency",
        "title": title,
        "quote": row["quote"],
        "location": row.get("location") or row.get("_line") or "paper.txt",
        "message": message,
        "suggestion": "Recheck the reported values against the analysis output and correct the wrong one.",
        "severity": severity,
        "kind": "substance/factual_error",
        "fix_effort": "edit_in_place",
    }


def run_exact(run_dir: Path) -> tuple[dict, list[Problem]]:
    """Run every exact check the run has inputs for. Returns a summary and problems with the inputs."""
    text = (run_dir / "paper.txt").read_text()
    paper = normalize_text(text)
    folder = run_dir / EXACT
    folder.mkdir(exist_ok=True)
    means = read_jsonl(folder / MEANS) if (folder / MEANS).exists() else []
    coefs = read_jsonl(folder / COEFS) if (folder / COEFS).exists() else []
    sums = read_jsonl(folder / SUMS) if (folder / SUMS).exists() else []
    rates = read_jsonl(folder / RATES) if (folder / RATES).exists() else []
    design = read_jsonl(folder / DESIGN) if (folder / DESIGN).exists() else []
    problems = _extraction_problems(means, ["x", "sd", "n"], paper, MEANS)
    problems += _extraction_problems(coefs, ["coef", "se", "t", "p", "ci_low", "ci_high"], paper, COEFS)
    problems += [
        Problem(f"exact/{COEFS} {row.get('id')}", "needs coef and se: an interval alone cannot be checked")
        for row in coefs
        if not row.get("coef") or not row.get("se")
    ]
    for row in sums:
        where = f"exact/{SUMS} {row.get('id')}"
        if not anchor_quote(row.get("quote", ""), paper):
            problems.append(Problem(where, "quote is not in paper.txt"))
        elif not row.get("parts") or not (row.get("total") or row.get("percent")):
            problems.append(Problem(where, "needs parts, and a total or percent: true"))
        else:
            missing = [
                v
                for v in row["parts"] + ([row["total"]] if row.get("total") else [])
                if v not in row["quote"]
            ]
            if missing:
                problems.append(Problem(where, f"{', '.join(missing)} do not appear in its quote"))
    for row in rates:
        where = f"exact/{RATES} {row.get('id')}"
        if not anchor_quote(row.get("quote", ""), paper):
            problems.append(Problem(where, "quote is not in paper.txt"))
            continue
        numbers = [g.get(f) for g in row.get("groups", []) for f in ("k", "n") if g.get(f)]
        missing = [v for v in numbers if v not in row["quote"]]
        if missing:
            problems.append(Problem(where, f"{', '.join(missing)} do not appear in its quote"))
    problems += _extraction_problems(design, ["estimate", "se", "main_estimate"], paper, DESIGN)
    for row in design:
        if row.get("kind") != "interaction":
            where = f"exact/{DESIGN} {row.get('id')}"
            quote = row.get("benchmark_quote", "")
            if not row.get("benchmark") or not anchor_quote(quote, paper):
                problems.append(Problem(where, "needs a benchmark and a benchmark_quote from the paper"))
            elif row["benchmark"].lstrip("-−") not in quote:
                problems.append(
                    Problem(where, f"benchmark {row['benchmark']!r} does not appear in its quote")
                )
    bad = {p.where.split()[-1] for p in problems}
    results, comments = [], []

    for row in coefs:
        if row["id"] in bad:
            continue
        try:
            found = check_coef(row)
        except ValueError as error:
            problems.append(Problem(f"exact/{COEFS} {row['id']}", str(error)))
            continue
        results.append({"check": "coef_cell", "id": row["id"], "consistent": not found, "detail": found})
        if found:
            comments.append(
                (f"Table cell {row.get('location', row['id'])} does not add up", row, "; ".join(found))
            )

    for row in sums:
        if row["id"] in bad:
            continue
        try:
            found = check_sum(row)
        except ValueError as error:
            problems.append(Problem(f"exact/{SUMS} {row['id']}", str(error)))
            continue
        results.append({"check": "sum", "id": row["id"], "consistent": not found, "detail": found})
        if found:
            comments.append(("Counts do not add up", row, "; ".join(found)))

    for row in rates:
        if row["id"] in bad:
            continue
        try:
            found = check_rates(row)
        except (ValueError, KeyError) as error:
            problems.append(Problem(f"exact/{RATES} {row['id']}", str(error)))
            continue
        results.append({"check": "rates", "id": row["id"], "consistent": not found, "detail": found})
        if found:
            title = (
                "Assignment counts depart from the design"
                if found[0].startswith("Assignment")
                else "Rates differ by group"
            )
            comments.append((title, row, "; ".join(found)))

    severities: dict[int, str] = {}
    ok, why = r_status()
    summary = {"r": why, "coef_cells": len([r for r in results if r["check"] == "coef_cell"])}
    if ok:
        payload = {"statcheck": paragraphs(plain(text)), "grim": [], "grimmer": [], "debit": [], "design": []}
        design_rows = {}
        for row in design:
            if row["id"] in bad:
                continue
            try:
                request = design_request(row)
            except (ValueError, KeyError) as error:
                problems.append(Problem(f"exact/{DESIGN} {row['id']}", str(error)))
                continue
            design_rows[row["id"]] = (row, request)
            payload["design"].append({k: v for k, v in request.items() if k != "estimate" and v is not None})
        by_id = {}
        for row in means:
            if row["id"] in bad or row.get("data", "integer") == "continuous":
                continue
            try:
                x, n = _number(row["x"], row["id"], "x"), int(_number(row["n"], row["id"], "n"))
                base = {"id": row["id"], "x": x, "n": n, "digits_x": decimals(row["x"])}
                if row.get("data") == "binary":
                    if row.get("sd"):
                        sd = _number(row["sd"], row["id"], "sd")
                        payload["debit"].append({**base, "sd": sd, "digits_sd": decimals(row["sd"])})
                else:
                    items = int(row.get("items", 1))
                    payload["grim"].append({**base, "items_averaged": items})
                    if row.get("sd"):
                        sd = _number(row["sd"], row["id"], "sd")
                        payload["grimmer"].append(
                            {**base, "sd": sd, "digits_sd": decimals(row["sd"]), "items_averaged": items}
                        )
            except ValueError as error:
                problems.append(Problem(f"exact/{MEANS} {row['id']}", str(error)))
                continue
            by_id[row["id"]] = row
        out = run_r(payload)
        summary["versions"] = out.get("versions")
        statcheck_version = (summary["versions"] or {}).get("statcheck")
        for hit in out.get("statcheck") or []:
            consistent = not hit["error"]
            results.append(
                {"check": "statcheck", "id": hit["source"], "consistent": consistent, "detail": hit}
            )
            if not consistent:
                row = {"quote": hit["raw"], "location": f"paragraph at line {hit['source'][1:]}"}
                decision = (
                    " It changes whether the result is significant at .05." if hit["decision_error"] else ""
                )
                message = (
                    f"{hit['raw']}: the test statistic and degrees of freedom give "
                    f"p = {hit['computed_p']:.4f}, not the reported p.{decision} "
                    f"Computed by statcheck {statcheck_version}."
                )
                comments.append(("Reported p does not match its test statistic", row, message))
        for check in ("grim", "grimmer", "debit"):
            for hit in out.get(check) or []:
                row = by_id[hit["id"]]
                results.append(
                    {"check": check, "id": hit["id"], "consistent": hit.get("consistency"), "detail": hit}
                )
                if hit.get("consistency") is False:
                    what = {
                        "grim": f"a mean of {row['x']} is impossible for n = {row['n']} integer scores",
                        "grimmer": f"mean {row['x']} with SD {row['sd']} is impossible for n = {row['n']} "
                        f"integer scores ({hit.get('reason', '')})",
                        "debit": f"mean {row['x']} with SD {row['sd']} is impossible "
                        f"for n = {row['n']} 0/1 values",
                    }[check]
                    message = f"{check.upper()}: {what}, at the reported decimals. Computed by scrutiny."
                    comments.append((f"{check.upper()} inconsistency", row, message))
        for hit in out.get("design") or []:
            row, request = design_rows[hit["id"]]
            found = design_finding(row, request, hit) if "type_m" in hit else None
            results.append({"check": "design", "id": hit["id"], "consistent": found is None, "detail": hit})
            if found:
                comments.append((DESIGN_TITLE, row, found[0]))
                severities[len(comments)] = found[1]
        summary["design"] = len(out.get("design") or [])
        summary["statcheck"] = len(out.get("statcheck") or [])
        summary["means"] = sum(len(out.get(c) or []) for c in ("grim", "grimmer", "debit"))

    (folder / RESULTS).write_text("".join(json.dumps(r) + "\n" for r in results))
    serious = ("does not match its test statistic", "inconsistency", "Rates differ", "Assignment counts")
    for _, row, _ in comments:
        line = locate_line(row["quote"], text)
        row["_line"] = f"line {line}" if line else ""
    rendered = [
        _comment(
            i,
            title,
            row,
            message,
            severities.get(i) or ("major" if any(s in title for s in serious) else "minor"),
        )
        for i, (title, row, message) in enumerate(comments, start=1)
    ]
    (run_dir / CANDIDATES).parent.mkdir(exist_ok=True)
    (run_dir / CANDIDATES).write_text("".join(json.dumps(c) + "\n" for c in rendered))
    summary["inconsistent"] = len(rendered)
    return summary, problems
