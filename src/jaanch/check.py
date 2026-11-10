"""Deterministic checks on what the review agents write.

These checks show that the output is well formed and that each quote exists in
the paper. They cannot show that a finding is right; docs/success.md covers
that.
"""

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass
from functools import cache
from importlib.resources import files
from pathlib import Path

from jsonschema import Draft202012Validator
from rapidfuzz import fuzz

# Quotes copied from PDF-derived text lose ligatures, hyphenation and the odd
# character. 90 accepts those losses; a paraphrase scores well below it.
FUZZY_THRESHOLD = 90.0


@dataclass(frozen=True)
class Problem:
    where: str
    message: str

    def __str__(self) -> str:
        return f"{self.where}: {self.message}"


@cache
def load_schema() -> dict:
    return json.loads(files("jaanch").joinpath("review.schema.json").read_text())


@cache
def _validator(definition: str | None) -> Draft202012Validator:
    schema = load_schema()
    if definition is None:
        return Draft202012Validator(schema)
    return Draft202012Validator({"$ref": f"#/$defs/{definition}", "$defs": schema["$defs"]})


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"-\s*\n\s*", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip().casefold()


def anchor_quote(quote: str, paper_normalized: str) -> str | None:
    """Return 'exact' or 'fuzzy' if the quote is in the paper, else None."""
    needle = normalize_text(quote)
    if not needle:
        return None
    if needle in paper_normalized:
        return "exact"
    if fuzz.partial_ratio(needle, paper_normalized) >= FUZZY_THRESHOLD:
        return "fuzzy"
    return None


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _schema_problems(record: dict, definition: str | None, where: str) -> list[Problem]:
    return [
        Problem(where, f"{'/'.join(map(str, error.absolute_path)) or '(root)'}: {error.message}")
        for error in _validator(definition).iter_errors(record)
    ]


def check_comment(comment: dict, paper_normalized: str, where: str) -> list[Problem]:
    problems = _schema_problems(comment, "comment", where)
    quote = comment.get("quote")
    if isinstance(quote, str) and anchor_quote(quote, paper_normalized) is None:
        problems.append(Problem(where, f"quote not found in paper: {quote[:80]!r}"))
    return problems


def check_comments(comments: list[dict], paper_text: str) -> list[Problem]:
    paper_normalized = normalize_text(paper_text)
    problems = []
    seen = set()
    for number, comment in enumerate(comments, start=1):
        where = comment.get("id") or f"record {number}"
        problems += check_comment(comment, paper_normalized, where)
        if comment.get("id") in seen:
            problems.append(Problem(where, "duplicate id"))
        seen.add(comment.get("id"))
    return problems


def check_review(review: dict, paper_path: Path) -> list[Problem]:
    problems = _schema_problems(review, None, "review")
    comments = review.get("comments", [])
    problems += check_comments(comments, paper_path.read_text())

    ids = {comment.get("id") for comment in comments}
    for item in review.get("overall", []):
        for comment_id in item.get("comment_ids", []):
            if comment_id not in ids:
                problems.append(Problem("overall", f"cites unknown comment {comment_id}"))

    recorded = review.get("paper", {}).get("sha256")
    if recorded and recorded != sha256_file(paper_path):
        problems.append(Problem("paper", "sha256 does not match the paper given"))
    return problems


def check_verdict(verdict: dict, where: str) -> list[Problem]:
    return _schema_problems(verdict, "verdict", where)


def check_revision_verdicts(verdicts: list[dict], prior_review: dict) -> list[Problem]:
    prior_ids = {comment["id"] for comment in prior_review.get("comments", [])}
    problems = []
    for number, verdict in enumerate(verdicts, start=1):
        where = verdict.get("source_comment_id") or f"record {number}"
        problems += _schema_problems(verdict, "revision_verdict", where)
        if verdict.get("source_comment_id") not in prior_ids:
            problems.append(Problem(where, "not a comment in the prior review"))
    missing = prior_ids - {verdict.get("source_comment_id") for verdict in verdicts}
    problems += [Problem(comment_id, "prior comment has no verdict") for comment_id in sorted(missing)]
    return problems


def read_jsonl(path: Path) -> list[dict]:
    lines = path.read_text().splitlines()
    return [json.loads(line) for line in lines if line.strip()]
