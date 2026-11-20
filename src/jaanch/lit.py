"""Deterministic steps of a literature map: find works, fetch open full text, and check extracted rows.

A literature map is a folder. Agents screen candidates and extract rows;
this module does the parts that must be exact: which works were found and
how, which identifiers resolve, and whether every extracted value is quoted
from the work it describes.

Sources are OpenAlex (search, references, citing works) and Semantic
Scholar (search, recommendations), through their maintained clients.
Neither request carries the user's email. Set OPENALEX_API_KEY for OpenAlex's
per-key budget; without it requests share a small daily budget per IP.
"""

import json
import os
import re
import subprocess
from functools import cache
from importlib.resources import files
from pathlib import Path

from jsonschema import Draft202012Validator

from jaanch.check import Problem, anchor_quote, normalize_text, read_jsonl

CANDIDATES = "candidates.jsonl"
SCREEN = "screen.jsonl"
ROWS = "rows.jsonl"
FULLTEXT = "fulltext"
OPENALEX_FIELDS = [
    "id",
    "doi",
    "display_name",
    "publication_year",
    "authorships",
    "primary_location",
    "best_oa_location",
    "cited_by_count",
    "abstract_inverted_index",
    "referenced_works",
    "type",
]
BATCH = 50
MAX_PDF_BYTES = 40_000_000


def _openalex():
    from pyalex import Works, config

    config.api_key = os.environ.get("OPENALEX_API_KEY")
    config.email = None
    config.user_agent = "jaanch (literature mapping)"
    config.max_retries = 3
    return Works


def _abstract(index: dict | None) -> str:
    if not index:
        return ""
    words = sorted((position, word) for word, positions in index.items() for position in positions)
    return " ".join(word for _, word in words)


def short_id(openalex_id: str) -> str:
    return openalex_id.rsplit("/", 1)[-1]


def _record(work: dict) -> dict:
    source = (work.get("primary_location") or {}).get("source") or {}
    oa = work.get("best_oa_location") or {}
    return {
        "id": short_id(work["id"]),
        "doi": (work.get("doi") or "").removeprefix("https://doi.org/") or None,
        "title": work.get("display_name") or "",
        "year": work.get("publication_year"),
        "authors": [a["author"]["display_name"] for a in work.get("authorships", [])][:10],
        "venue": source.get("display_name"),
        "type": work.get("type"),
        "cited_by": work.get("cited_by_count"),
        "abstract": _abstract(work.get("abstract_inverted_index")),
        "references": [short_id(ref) for ref in work.get("referenced_works", [])],
        "oa_pdf": oa.get("pdf_url"),
    }


def load_candidates(folder: Path) -> dict[str, dict]:
    path = folder / CANDIDATES
    return {row["id"]: row for row in read_jsonl(path)} if path.exists() else {}


def _save(folder: Path, candidates: dict[str, dict]) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / CANDIDATES).write_text("".join(json.dumps(row) + "\n" for row in candidates.values()))


def add_works(folder: Path, works: list[dict], how) -> int:
    """Merge OpenAlex works into the candidates, recording how each was found. Returns how many are new.

    `how` is a label, or a function from a work to its labels when one
    request serves several seeds.
    """
    candidates = load_candidates(folder)
    new = 0
    for work in works:
        record = _record(work)
        if record["id"] not in candidates:
            record["found_by"] = []
            candidates[record["id"]] = record
            new += 1
        for label in how(record) if callable(how) else [how]:
            if label not in candidates[record["id"]]["found_by"]:
                candidates[record["id"]]["found_by"].append(label)
    _save(folder, candidates)
    return new


def _by_ids(ids: list[str], key: str = "openalex_id") -> list[dict]:
    """Fetch works by OpenAlex id or DOI, BATCH per request."""
    works_api = _openalex()
    found = []
    for start in range(0, len(ids), BATCH):
        chunk = ids[start : start + BATCH]
        query = works_api().filter(**{key: "|".join(chunk)}).select(OPENALEX_FIELDS)
        found += query.get(per_page=BATCH)
    return found


def search(folder: Path, query: str, limit: int = 200) -> tuple[int, int]:
    """OpenAlex relevance search, plus Semantic Scholar search resolved to OpenAlex by DOI."""
    works_api = _openalex()
    openalex = works_api().search(query).select(OPENALEX_FIELDS).get(per_page=min(limit, 200))
    new = add_works(folder, openalex, f"search:openalex:{query}")
    dois = [
        paper["externalIds"]["DOI"]
        for paper in _s2_search(query, limit)
        if paper.get("externalIds", {}).get("DOI")
    ]
    new += add_works(folder, _by_ids(dois, "doi") if dois else [], f"search:s2:{query}")
    return len(openalex), new


def _s2_search(query: str, limit: int) -> list[dict]:
    try:
        from semanticscholar import SemanticScholar

        # The client retries throttled requests without limit by default, and
        # unauthenticated requests are throttled often: fail fast instead.
        client = SemanticScholar(api_key=os.environ.get("S2_API_KEY"), timeout=20, retry=False)
        results = client.search_paper(query, fields=["externalIds", "title"], limit=min(limit, 100))
        return [paper.raw_data for paper in results.items]
    except Exception as error:  # an outage in the secondary source must not stop the primary one
        print(f"Semantic Scholar search skipped: {error}")
        return []


def expand(folder: Path, ids: list[str], backward: bool = True, forward: bool = True) -> dict[str, int]:
    """Follow references (backward) and citing works (forward) from the given candidate ids.

    Requests are batched: unknown references of all seeds are fetched BATCH
    at a time, and citing works of BATCH seeds come from one `cites:` query.
    Which seed led to a work is recovered from the work's own reference list.
    A plain filter costs a tenth of a search, so citing works are not
    narrowed by search here; run `prefilter` afterwards instead.
    """
    candidates = load_candidates(folder)
    counts = {"backward": 0, "forward": 0}
    if backward:
        cited_by: dict[str, list[str]] = {}
        for i in ids:
            for ref in candidates.get(i, {}).get("references", []):
                cited_by.setdefault(ref, []).append(f"cited_by:{i}")
        unknown = sorted(set(cited_by) - set(candidates))
        counts["backward"] = add_works(
            folder, _by_ids(unknown) if unknown else [], lambda r: cited_by[r["id"]]
        )
        known = load_candidates(folder)
        for ref, labels in cited_by.items():
            if ref in known:
                known[ref]["found_by"] += [label for label in labels if label not in known[ref]["found_by"]]
        _save(folder, known)
    if forward:
        works_api = _openalex()
        for start in range(0, len(ids), BATCH):
            chunk = ids[start : start + BATCH]
            seeds = set(chunk)
            pages = (
                works_api()
                .filter(cites="|".join(chunk))
                .select(OPENALEX_FIELDS)
                .paginate(method="page", per_page=200, n_max=10_000)
            )
            citing = [work for page in pages for work in page]
            counts["forward"] += add_works(
                folder,
                citing,
                lambda r: [f"cites:{s}" for s in sorted(seeds & set(r["references"]))] or ["cites:?"],
            )
    return counts


def add(folder: Path, identifiers: list[str], how: str) -> int:
    """Add works by DOI or OpenAlex id, e.g. ones found by web search."""
    dois = [
        i.removeprefix("https://doi.org/") for i in identifiers if i.startswith(("10.", "https://doi.org/"))
    ]
    openalex = [short_id(i) for i in identifiers if re.fullmatch(r"(https://openalex\.org/)?W\d+", i)]
    works = (_by_ids(dois, "doi") if dois else []) + (_by_ids(openalex) if openalex else [])
    return add_works(folder, works, how)


TITLE_MATCH = 92
VERSION_TYPES = {"article": 0, "book": 1, "book-chapter": 2, "preprint": 3, "report": 4}


def _title_key(title: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", normalize_text(title)).strip()


def versions(folder: Path) -> dict[str, list[str]]:
    """Group candidates that are versions of one work: a journal article, its working paper, a data deposit.

    OpenAlex keeps these as separate records. Two records are one work when
    their titles match at TITLE_MATCH or above, they share a first-author
    surname, and their years are within two. The representative is the
    published version where there is one, else the most cited.
    """
    from rapidfuzz import fuzz

    rows = list(load_candidates(folder).values())
    surname = {r["id"]: (r["authors"][0].split()[-1].casefold() if r["authors"] else "") for r in rows}
    keys = {r["id"]: _title_key(r["title"]) for r in rows}
    parent = {r["id"]: r["id"] for r in rows}

    def find(i: str) -> str:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    by_surname: dict[str, list[dict]] = {}
    for r in rows:
        by_surname.setdefault(surname[r["id"]], []).append(r)
    for group in by_surname.values():
        for a_index, a in enumerate(group):
            for b in group[a_index + 1 :]:
                close_years = abs((a["year"] or 0) - (b["year"] or 0)) <= 2
                if close_years and keys[a["id"]] and fuzz.ratio(keys[a["id"]], keys[b["id"]]) >= TITLE_MATCH:
                    parent[find(a["id"])] = find(b["id"])
    clusters: dict[str, list[dict]] = {}
    for r in rows:
        clusters.setdefault(find(r["id"]), []).append(r)
    result = {}
    for members in clusters.values():
        best = min(members, key=lambda r: (VERSION_TYPES.get(r["type"], 9), -(r["cited_by"] or 0)))
        result[best["id"]] = sorted(r["id"] for r in members)
    return result


def screen_decisions(folder: Path) -> dict[str, dict]:
    path = folder / SCREEN
    return {row["id"]: row for row in read_jsonl(path)} if path.exists() else {}


SHORT_ABSTRACT = 200


def prefilter(folder: Path, terms: list[str], also: list[str] | None = None) -> int:
    """Exclude unscreened candidates that lack the terms, recording why.

    A candidate must contain one of `terms` and, when `also` is given, one of
    `also` too. A candidate whose abstract is shorter than SHORT_ABSTRACT
    characters needs only `terms`: a title alone rarely names a design. The
    remaining candidates go to a model screener with the written criteria;
    check the rule's cost against an answer key before using it.
    """
    candidates, decisions = load_candidates(folder), screen_decisions(folder)

    def pattern(words: list[str]) -> re.Pattern:
        return re.compile("|".join(re.escape(word) for word in words), re.IGNORECASE)

    first, second = pattern(terms), pattern(also) if also else None
    excluded = 0
    for work_id, row in candidates.items():
        text = f"{row['title']} {row['abstract']}"
        passes = bool(first.search(text)) and (
            second is None or bool(second.search(text)) or len(row["abstract"]) < SHORT_ABSTRACT
        )
        if work_id in decisions or passes:
            continue
        rule = f"one of {terms}" + (f" and one of {also}" if also else "")
        decisions[work_id] = {"id": work_id, "decision": "exclude", "reason": f"prefilter: lacks {rule}"}
        excluded += 1
    (folder / SCREEN).write_text("".join(json.dumps(row) + "\n" for row in decisions.values()))
    return excluded


DECISIONS = {"include", "exclude", "unsure"}


def merge_screen(folder: Path, outputs: list[Path]) -> tuple[int, list[Problem]]:
    """Merge screeners' decisions into screen.jsonl, refusing ids that are not candidates or bad decisions."""
    candidates, decisions = load_candidates(folder), screen_decisions(folder)
    problems, merged = [], 0
    for path in outputs:
        for number, row in enumerate(read_jsonl(path), start=1):
            where = f"{path.name}:{number}"
            if row.get("id") not in candidates:
                problems.append(Problem(where, f"{row.get('id')} is not a candidate"))
            elif row.get("decision") not in DECISIONS:
                problems.append(
                    Problem(where, f"decision {row.get('decision')!r} is not one of {sorted(DECISIONS)}")
                )
            elif not row.get("reason"):
                problems.append(Problem(where, "no reason"))
            else:
                decisions[row["id"]] = {"id": row["id"], "decision": row["decision"], "reason": row["reason"]}
                merged += 1
    (folder / SCREEN).write_text("".join(json.dumps(row) + "\n" for row in decisions.values()))
    left = set(candidates) - set(decisions)
    if left:
        problems.append(Problem(SCREEN, f"{len(left)} candidates still unscreened"))
    return merged, problems


def unscreened(folder: Path) -> list[dict]:
    decisions = screen_decisions(folder)
    return [row for work_id, row in load_candidates(folder).items() if work_id not in decisions]


def fetch(folder: Path, decisions_wanted: tuple[str, ...] = ("include",)) -> dict[str, str]:
    """Download open PDFs of works with the given screening decisions and extract text. Returns id -> outcome.

    Fetching "unsure" works lets a screener decide from the full text when
    the abstract is empty.
    """
    import requests

    candidates, decisions = load_candidates(folder), screen_decisions(folder)
    (folder / FULLTEXT).mkdir(exist_ok=True)
    outcomes = {}
    for work_id, decision in decisions.items():
        if decision["decision"] not in decisions_wanted:
            continue
        text_path = folder / FULLTEXT / f"{work_id}.txt"
        if text_path.exists():
            outcomes[work_id] = "already fetched"
            continue
        url = candidates.get(work_id, {}).get("oa_pdf")
        if not url:
            outcomes[work_id] = "no open-access PDF; add the text by hand"
            continue
        pdf_path = folder / FULLTEXT / f"{work_id}.pdf"
        try:
            response = requests.get(
                url, timeout=60, headers={"User-Agent": "jaanch (literature mapping)"}, stream=True
            )
            response.raise_for_status()
            size = 0
            with pdf_path.open("wb") as out:
                for chunk in response.iter_content(65536):
                    size += len(chunk)
                    if size > MAX_PDF_BYTES:
                        raise ValueError("PDF over 40 MB")
                    out.write(chunk)
            if not pdf_path.read_bytes()[:5].startswith(b"%PDF"):
                raise ValueError("not a PDF (likely a publisher page)")
            subprocess.run(
                ["pdftotext", "-layout", str(pdf_path), str(text_path)],
                check=True,
                timeout=120,
                stderr=subprocess.DEVNULL,
            )
            outcomes[work_id] = "fetched"
        except Exception as error:  # record and continue: one bad host must not stop the rest
            pdf_path.unlink(missing_ok=True)
            outcomes[work_id] = f"failed: {error}"
    return outcomes


def status(folder: Path) -> dict:
    """Counts at each stage, for the flow diagram."""
    candidates, decisions = load_candidates(folder), screen_decisions(folder)
    rows = read_jsonl(folder / ROWS) if (folder / ROWS).exists() else []
    included = [i for i, d in decisions.items() if d["decision"] == "include"]
    fulltext = [i for i in included if (folder / FULLTEXT / f"{i}.txt").exists()]
    groups = versions(folder)
    included_works = sum(any(m in included for m in members) for members in groups.values())
    return {
        "candidates": len(candidates),
        "works": len(groups),
        "included_works": included_works,
        "screened": len(decisions),
        "unscreened": len(set(candidates) - set(decisions)),
        "included": len(included),
        "excluded": sum(d["decision"] == "exclude" for d in decisions.values()),
        "unsure": sum(d["decision"] == "unsure" for d in decisions.values()),
        "with_fulltext": len(fulltext),
        "rows": len(rows),
    }


@cache
def _row_validator() -> Draft202012Validator:
    paper_model = json.loads(files("jaanch").joinpath("paper_model.schema.json").read_text())
    row = json.loads(files("jaanch").joinpath("lit_row.schema.json").read_text())
    row["$defs"] = {**paper_model["$defs"], **row.get("$defs", {})}
    return Draft202012Validator(row)


def _quotes(value, path="") -> list[tuple[str, str]]:
    if isinstance(value, dict):
        found = [(path, value["quote"])] if isinstance(value.get("quote"), str) else []
        return found + [
            q for key, item in value.items() if key != "quote" for q in _quotes(item, f"{path}/{key}")
        ]
    if isinstance(value, list):
        return [q for index, item in enumerate(value) for q in _quotes(item, f"{path}[{index}]")]
    return []


def check_rows(folder: Path) -> list[Problem]:
    """Every row validates, describes an included candidate, and quotes only text found in that work."""
    candidates, decisions = load_candidates(folder), screen_decisions(folder)
    problems = []
    for number, row in enumerate(read_jsonl(folder / ROWS), start=1):
        where = f"{ROWS}:{number}"
        errors = list(_row_validator().iter_errors(row))
        problems += [Problem(where, f"{'/'.join(map(str, e.path)) or '(root)'}: {e.message}") for e in errors]
        if errors:
            continue
        if row["id"] not in candidates:
            problems.append(Problem(where, f"{row['id']} is not a candidate"))
            continue
        if decisions.get(row["id"], {}).get("decision") != "include":
            problems.append(Problem(where, f"{row['id']} was not included at screening"))
        text_path = folder / FULLTEXT / f"{row['id']}.txt"
        source = (
            text_path.read_text(errors="replace") if text_path.exists() else candidates[row["id"]]["abstract"]
        )
        normalized = normalize_text(source)
        for field, quote in _quotes(row):
            if not anchor_quote(quote, normalized):
                problems.append(Problem(where, f"{row['id']}{field}: quote is not in the work's text"))
    return problems


def recall(folder: Path, truth: list[str]) -> dict:
    """Share of an answer key (OpenAlex ids or DOIs) found as candidates and included at screening."""
    candidates, decisions = load_candidates(folder), screen_decisions(folder)
    by_doi = {row["doi"].casefold(): i for i, row in candidates.items() if row.get("doi")}
    resolved = []
    for item in truth:
        item = item.strip()
        if re.fullmatch(r"W\d+", short_id(item)):
            resolved.append(short_id(item))
        else:
            resolved.append(by_doi.get(item.removeprefix("https://doi.org/").casefold(), item))
    groups = versions(folder)
    sibling = {member: members for members in groups.values() for member in members}
    found = [i for i in resolved if i in candidates]
    included = [
        i
        for i in found
        if any(decisions.get(v, {}).get("decision") == "include" for v in sibling.get(i, [i]))
    ]
    return {
        "answer_key": len(resolved),
        "found": len(found),
        "included": len(included),
        "recall_found": round(len(found) / len(resolved), 3) if resolved else None,
        "recall_included": round(len(included) / len(resolved), 3) if resolved else None,
        "missed": sorted(set(resolved) - set(found)),
    }
