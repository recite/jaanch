"""Grow checks/sources.bib from Crossref records, never from memory.

Every decision rule and register check cites works by key in sources.bib, so
a wrong entry propagates into every page that shows the source. An entry is
added only from the Crossref record for its DOI, and only when that record's
title matches the title the caller expects, which catches a DOI that resolves
to some other paper.
"""

import re
import unicodedata
from importlib.resources import files
from pathlib import Path

from rapidfuzz import fuzz

USER_AGENT = "jaanch (sources bibliography)"
STOPWORDS = {
    "a",
    "an",
    "the",
    "on",
    "of",
    "and",
    "in",
    "for",
    "to",
    "is",
    "what",
    "why",
    "how",
    "does",
    "do",
    "with",
}
KINDS = {"book": "book", "monograph": "book", "edited-book": "book", "posted-content": "misc"}
TITLE_MATCH = 80


def bib_path() -> Path:
    return Path(str(files("jaanch").joinpath("checks", "sources.bib")))


def _ascii(text: str) -> str:
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()


def crossref(doi: str) -> dict:
    import requests

    response = requests.get(
        f"https://api.crossref.org/works/{doi}", headers={"User-Agent": USER_AGENT}, timeout=30
    )
    if response.status_code == 404:
        raise LookupError(f"{doi}: Crossref has no record")
    response.raise_for_status()
    return response.json()["message"]


def _title(record: dict) -> str:
    return " ".join(re.sub(r"<[^>]+>", "", (record.get("title") or [""])[0]).split())


def _year(record: dict) -> int | None:
    return (record.get("issued", {}).get("date-parts") or [[None]])[0][0]


def make_key(record: dict, taken: set[str]) -> str:
    people = record.get("author") or record.get("editor") or [{"family": "anon"}]
    family = re.sub(r"[^a-z]", "", _ascii(people[0].get("family", "anon")))
    words = [w for w in re.findall(r"[a-z]+", _ascii(_title(record))) if w not in STOPWORDS]
    base = f"{family}{_year(record) or ''}{words[0] if words else ''}"
    key, n = base, 2
    while key in taken:
        key, n = f"{base}{n}", n + 1
    return key


def entry(record: dict, key: str, doi: str) -> str:
    kind = KINDS.get(record.get("type") or "", "article")
    people = record.get("author") or record.get("editor") or []
    venue = (record.get("container-title") or [record.get("publisher", "")])[0]
    fields = {
        "author": " and ".join(f"{p.get('family', '')}, {p.get('given', '')}".strip(", ") for p in people),
        "title": _title(record),
        "year": _year(record),
        ("journal" if kind == "article" else "publisher"): venue,
        "volume": record.get("volume"),
        "number": record.get("issue"),
        "pages": (record.get("page") or "").replace("-", "--"),
        "doi": doi,
    }
    body = ",\n".join(f"  {name} = {{{value}}}" for name, value in fields.items() if value)
    return f"@{kind}{{{key},\n{body}\n}}\n"


def add(doi: str, expected_title: str, path: Path | None = None) -> str:
    """Append the Crossref entry for doi to sources.bib and return its key.

    Refuses a DOI already in the bib, and a record whose title does not match
    expected_title (token-set similarity below TITLE_MATCH).
    """
    path = path or bib_path()
    text = path.read_text()
    known = dict(re.findall(r"@\w+\{([^,]+),[^@]*?doi = \{([^}]+)\}", text))
    existing = {d.lower(): k for k, d in known.items()}
    if doi.lower() in existing:
        return existing[doi.lower()]
    record = crossref(doi)
    title = _title(record)
    score = fuzz.token_set_ratio(_ascii(expected_title), _ascii(title))
    if score < TITLE_MATCH:
        raise ValueError(f"{doi} is {title!r}, not {expected_title!r} (match {score:.0f})")
    taken = set(re.findall(r"@\w+\{([^,]+),", text))
    key = make_key(record, taken)
    path.write_text(text.rstrip("\n") + "\n\n" + entry(record, key, doi))
    return key
