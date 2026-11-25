"""Grow checks/sources.bib from Crossref records or the page itself, never from memory.

Every decision rule and register check cites works by key in sources.bib, so
a wrong entry propagates into every page that shows the source. An entry is
added only from the Crossref record for its DOI, and only when that record's
title matches the title the caller expects, which catches a DOI that resolves
to some other paper. A work with no DOI (a blog post) is added from its page:
the page's own title must match, and its publication date gives the year.
"""

import html
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


# Characters that end a BibTeX field or start an entry or a command. Field
# values come from Crossref or a fetched page, so a value holding them could
# close its entry and append another; they are removed, not escaped.
BIBTEX_SPECIAL = re.compile(r"[{}@\\]")


def _clean(value) -> str:
    return " ".join(BIBTEX_SPECIAL.sub("", str(value)).split())


def _render(kind: str, key: str, fields: dict) -> str:
    """One entry, refusing anything that would not read back as exactly that entry."""
    if not re.fullmatch(r"[a-z0-9]+", key):
        raise ValueError(f"key {key!r} must be lowercase letters and digits")
    clean = {name: _clean(value) for name, value in fields.items() if value}
    body = ",\n".join(f"  {name} = {{{value}}}" for name, value in clean.items())
    text = f"@{kind}{{{key},\n{body}\n}}\n"
    parsed = re.findall(r"@(\w+)\{([^,]+),\n(.*?)\n\}\n", text, re.S)
    if (
        len(parsed) != 1
        or parsed[0][1] != key
        or dict(re.findall(r"  (\w+) = \{(.*?)\}", parsed[0][2])) != clean
    ):
        raise ValueError(f"entry for {key} does not read back as one entry")
    return text


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
    return _render(kind, key, fields)


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


META = re.compile(r'<meta[^>]+(?:property|name)="([^"]+)"[^>]+content="([^"]*)"', re.I)


def page_record(url: str) -> dict:
    """Title, site name and year a page states about itself."""
    from jaanch.lit import get_public

    response = get_public(url)
    response.raise_for_status()
    text = response.raw.read(2_000_000, decode_content=True).decode("utf-8", "replace")
    response.close()
    meta = {name.lower(): html.unescape(value) for name, value in META.findall(text)}
    title = meta.get("og:title") or html.unescape(
        re.search(r"<title>(.*?)</title>", text, re.S | re.I).group(1)
    )
    published = meta.get("article:published_time", "")
    return {
        "title": " ".join(title.split()),
        "site": meta.get("og:site_name", ""),
        "year": int(published[:4]) if published[:4].isdigit() else None,
    }


def url_key(url: str) -> str:
    """datacolada.org/74 -> datacolada74."""
    from urllib.parse import urlparse

    parts = urlparse(url)
    host = parts.netloc.lower().removeprefix("www.").split(".")[0]
    tail = re.sub(r"[^a-z0-9]", "", parts.path.lower().rstrip("/").split("/")[-1])
    return re.sub(r"[^a-z0-9]", "", host) + tail


def add_url(url: str, expected_title: str, author: str, path: Path | None = None) -> str:
    """Append a @misc entry for a page with no DOI and return its key (or the key it already has)."""
    path = path or bib_path()
    text = path.read_text()
    existing = dict((u, k) for k, u in re.findall(r"@\w+\{([^,]+),[^@]*?url = \{([^}]+)\}", text))
    if url in existing:
        return existing[url]
    record = page_record(url)
    score = fuzz.token_set_ratio(_ascii(expected_title), _ascii(record["title"]))
    if score < TITLE_MATCH:
        raise ValueError(f"{url} is {record['title']!r}, not {expected_title!r} (match {score:.0f})")
    key = url_key(url)
    if re.search(rf"@\w+\{{{re.escape(key)},", text):
        raise ValueError(f"key {key} is taken by another entry")
    fields = {
        "author": author,
        "title": record["title"],
        "year": record["year"],
        "howpublished": record["site"],
        "url": url,
    }
    path.write_text(text.rstrip("\n") + "\n\n" + _render("misc", key, fields))
    return key
