"""Record what a submission contains, so routing can decide which checks can run.

A submission may be a manuscript alone, a manuscript with its replication
package, or a repository with no manuscript. Every check names the inputs it
needs; this module finds which of those inputs are present. It only looks at
file names and a little file content, and never runs the submission's code.
"""

import re
import subprocess
from collections import Counter
from pathlib import Path

INPUTS = ["paper_text", "tables", "figures", "bibliography", "code", "data", "registration"]

MANUSCRIPT_SUFFIXES = [".tex", ".md", ".qmd", ".rmd", ".docx", ".pdf", ".txt"]
CODE_SUFFIXES = {
    ".r": "R",
    ".py": "Python",
    ".do": "Stata",
    ".ado": "Stata",
    ".jl": "Julia",
    ".m": "MATLAB",
    ".sas": "SAS",
    ".sps": "SPSS",
    ".ipynb": "Python",
    ".sh": "shell",
}
BUILD_FILES = {"makefile", "snakefile", "justfile", "run_all.r", "master.do", "main.do", "run.sh"}
DATA_SUFFIXES = {
    ".csv",
    ".tsv",
    ".dta",
    ".parquet",
    ".feather",
    ".rds",
    ".rda",
    ".rdata",
    ".sav",
    ".xlsx",
    ".xls",
    ".jsonl",
}
FIGURE_SUFFIXES = {".png", ".jpg", ".jpeg", ".svg", ".eps", ".pdf"}
ENVIRONMENT_FILES = {
    "renv.lock",
    "uv.lock",
    "requirements.txt",
    "pyproject.toml",
    "environment.yml",
    "description",
    "dockerfile",
    "poetry.lock",
}
# Folder names that mark what their files are. A .csv under tabs/ is a table
# the paper prints; the same file under data/ is an input to the analysis.
TABLE_DIRS = {"tab", "tabs", "table", "tables", "output", "outputs", "results"}
FIGURE_DIRS = {"fig", "figs", "figure", "figures", "plots", "img", "images"}
DATA_DIRS = {"data", "raw", "derived", "processed", "inputs"}
MANUSCRIPT_DIRS = {"ms", "paper", "manuscript", "draft", "tex", "latex", "writeup"}
SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", ".tox", "renv", ".ipynb_checkpoints"}
MANUSCRIPT_NAMES = {"main", "paper", "manuscript", "ms", "draft", "article"}
REGISTRATION_NAME = re.compile(r"pre-?reg|pre-?analysis|\bpap\b|registration|aspredicted", re.IGNORECASE)
# Registry identifiers a manuscript cites. Each names a document that can be
# fetched, so a paper that cites one has its registration within reach.
REGISTRY_IDS = {
    "AEA RCT Registry": re.compile(r"AEARCTR-\d{7}"),
    "ClinicalTrials.gov": re.compile(r"\bNCT\d{8}\b"),
    "OSF": re.compile(r"osf\.io/[a-z0-9]{5}\b", re.IGNORECASE),
    "AsPredicted": re.compile(r"aspredicted\.org/[A-Za-z0-9_./-]+"),
    "EGAP/OSF": re.compile(r"\bEGAP\s*(?:ID\s*)?\d{8}\b"),
    "RIDIE": re.compile(r"RIDIE-STUDY-ID-[0-9a-f]+", re.IGNORECASE),
}
TEX_DOCUMENT = re.compile(r"\\documentclass")
TEX_TABULAR = re.compile(r"\\begin\{(?:tabular|longtable|tabularx|threeparttable)")
TEX_GRAPHIC = re.compile(r"\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}")
MIN_PROSE_WORDS = 1500
TABLE_CAPTION = re.compile(r"^\s*Table\s+[A-Z]?\d+[.:]", re.MULTILINE)
REFERENCES_HEADING = re.compile(
    r"^\s*(?:#+\s*|\\section\*?\{|[0-9]+\.?\s+)?(?:References|Bibliography|Works Cited)\}?\s*$",
    re.MULTILINE | re.IGNORECASE,
)


def list_files(root: Path) -> list[Path]:
    """Every file under root, skipping version-control and tool folders.

    This deliberately does not ask git for tracked files: a submission's own
    .git/config can make git run commands (core.fsmonitor), and the
    submission is untrusted. Ignored files are therefore included, which is
    useful when data are present locally but not committed.
    """
    return sorted(
        path
        for path in root.rglob("*")
        if path.is_file()
        and not path.is_symlink()
        and not (set(path.relative_to(root).parts[:-1]) & SKIP_DIRS)
    )


def _dirs(path: Path, root: Path) -> set[str]:
    return {part.casefold() for part in path.relative_to(root).parts[:-1]}


def _read(path: Path) -> str:
    try:
        return path.read_text(errors="replace")
    except OSError:
        return ""


def _pdf_text(path: Path) -> str:
    """Plain text for sniffing only (captions, headings, registry ids), not the text reviewers read."""
    try:
        return subprocess.run(
            ["pdftotext", "-layout", str(path), "-"], capture_output=True, text=True, timeout=60
        ).stdout
    except (OSError, subprocess.TimeoutExpired):
        return ""


def _pdf_pages(path: Path) -> int | None:
    try:
        out = subprocess.run(["pdfinfo", str(path)], capture_output=True, text=True, timeout=20).stdout
    except (OSError, subprocess.TimeoutExpired):
        return None
    match = re.search(r"^Pages:\s+(\d+)", out, re.MULTILINE)
    return int(match.group(1)) if match else None


def _manuscript_score(path: Path, root: Path) -> tuple:
    """Sort key: higher is likelier to be the manuscript."""
    return (
        bool(_dirs(path, root) & MANUSCRIPT_DIRS) or path.parent == root,
        path.stem.casefold() in MANUSCRIPT_NAMES,
        path.stat().st_size,
    )


def find_manuscript(
    files: list[Path], root: Path, figures_cited: set[str]
) -> tuple[Path | None, list[Path], str]:
    """The main manuscript, other candidates, and how it was chosen.

    Source beats compiled output: a .tex with \\documentclass is preferred to
    the PDF it builds, because text, tables and macros survive in the source.
    """
    tex = [path for path in files if path.suffix.casefold() == ".tex" and TEX_DOCUMENT.search(_read(path))]
    if tex:
        ranked = sorted(tex, key=lambda path: _manuscript_score(path, root), reverse=True)
        return ranked[0], ranked[1:], "LaTeX file with \\documentclass"
    prose = [
        path
        for path in files
        if path.suffix.casefold() in {".md", ".qmd", ".rmd", ".txt"}
        and path.stem.casefold() not in {"readme", "license", "changelog", "contributing", "agents", "claude"}
        and not (_dirs(path, root) & {"docs", ".github"})
        and len(_read(path).split()) >= MIN_PROSE_WORDS
    ]
    if prose:
        ranked = sorted(prose, key=lambda path: _manuscript_score(path, root), reverse=True)
        return ranked[0], ranked[1:], f"text file of at least {MIN_PROSE_WORDS} words"
    docx = [path for path in files if path.suffix.casefold() == ".docx"]
    if docx:
        ranked = sorted(docx, key=lambda path: _manuscript_score(path, root), reverse=True)
        return ranked[0], ranked[1:], "Word document"
    pdfs = [
        path
        for path in files
        if path.suffix.casefold() == ".pdf"
        and path.stem not in figures_cited
        and not (_dirs(path, root) & FIGURE_DIRS)
        and (_pdf_pages(path) or 0) >= 5
    ]
    if pdfs:
        ranked = sorted(pdfs, key=lambda path: _manuscript_score(path, root), reverse=True)
        return ranked[0], ranked[1:], "PDF of 5 or more pages (no source found)"
    return None, [], "no manuscript found"


def inventory(target: Path, manuscript: Path | None = None) -> dict:
    """Describe what a file or folder contains, in terms of the inputs checks need.

    A lone file is a submission of one manuscript. A folder is searched, and
    `manuscript`, when given, overrides which of its files is the manuscript.
    """
    target = target.resolve()
    if target.is_file():
        root, files, given = target.parent, [target], target
    else:
        root, files = target, list_files(target)
        given = manuscript.resolve() if manuscript else None

    tex_text = "\n".join(_read(path) for path in files if path.suffix.casefold() == ".tex")
    figures_cited = {Path(name).stem for name in TEX_GRAPHIC.findall(tex_text)}

    if given is not None:
        manuscript, others, how = given, [], "the file given"
    else:
        manuscript, others, how = find_manuscript(files, root, figures_cited)
    # A knitted .tex or .pdf is what readers see, with inline code replaced by
    # its numbers, so it stays the text; the .Rmd/.qmd it came from is recorded.
    source = None
    if manuscript is not None and manuscript.suffix.casefold() in {".tex", ".pdf", ".md"}:
        siblings = [
            path
            for path in files
            if path.parent == manuscript.parent
            and path.stem == manuscript.stem
            and path.suffix.casefold() in {".rmd", ".qmd"}
        ]
        if siblings:
            source = siblings[0]
            others = [path for path in others if path != source]
    is_pdf = manuscript is not None and manuscript.suffix.casefold() == ".pdf"
    manuscript_text = (_pdf_text(manuscript) if is_pdf else _read(manuscript)) if manuscript else ""

    def rel(path: Path) -> str:
        return str(path.relative_to(root))

    tables, figures, code, data, bibliography, environment, registration_docs, build = ([] for _ in range(8))
    languages: Counter = Counter()
    for path in files:
        if path in (manuscript, source, *others):
            continue
        suffix, name, dirs = path.suffix.casefold(), path.name.casefold(), _dirs(path, root)
        if REGISTRATION_NAME.search(path.stem) and suffix in {".pdf", ".md", ".docx", ".txt", ".tex"}:
            registration_docs.append(rel(path))
        elif suffix in {".bib", ".bbl"}:
            bibliography.append(rel(path))
        elif name in ENVIRONMENT_FILES:
            environment.append(rel(path))
        elif name in BUILD_FILES:
            build.append(rel(path))
        elif suffix in CODE_SUFFIXES:
            code.append(rel(path))
            languages[CODE_SUFFIXES[suffix]] += 1
        elif suffix == ".tex" and TEX_TABULAR.search(_read(path)):
            tables.append(rel(path))
        elif suffix in {".csv", ".tsv"} and dirs & (TABLE_DIRS | FIGURE_DIRS):
            tables.append(rel(path))
        elif suffix in FIGURE_SUFFIXES and (dirs & FIGURE_DIRS or path.stem in figures_cited):
            figures.append(rel(path))
        elif suffix in DATA_SUFFIXES or (dirs & DATA_DIRS and suffix in {".json", ".txt", ".zip", ".gz"}):
            data.append(rel(path))

    registry_ids = sorted(
        {
            f"{registry}: {match}"
            for registry, pattern in REGISTRY_IDS.items()
            for match in pattern.findall(tex_text + manuscript_text)
        }
    )
    inline_tables = bool(
        TEX_TABULAR.search(manuscript_text)
        or re.search(r"^\|.+\|\s*$", manuscript_text, re.M)
        or (is_pdf and TABLE_CAPTION.search(manuscript_text))
    )
    inline_references = bool(REFERENCES_HEADING.search(manuscript_text))

    available = {
        "paper_text": manuscript is not None,
        "tables": bool(tables) or inline_tables,
        "figures": bool(figures),
        "bibliography": bool(bibliography) or inline_references,
        "code": bool(code),
        "data": bool(data),
        "registration": bool(registration_docs),
    }
    notes = []
    if manuscript is not None and manuscript.suffix.casefold() == ".pdf":
        notes.append("manuscript is a PDF; text extraction is lossy for tables and equations")
        notes.append("figures inside a PDF are not extracted; figure checks need the image files")
    if others:
        notes.append(f"{len(others)} other manuscript candidates; check the choice")
    if registry_ids and not registration_docs:
        notes.append(
            "the paper cites a registry id but no registration document is present; it can be fetched"
        )
    if code and not data:
        notes.append("code without data: code can be read but not rerun")
    if data and not code:
        notes.append("data without code: data can be checked but reported numbers cannot be regenerated")

    return {
        "root": str(root),
        "manuscript": {
            "path": rel(manuscript) if manuscript else None,
            "format": manuscript.suffix.casefold().lstrip(".") if manuscript else None,
            "chosen_by": how,
            "generated_from": rel(source) if source else None,
            "other_candidates": [rel(path) for path in others],
        },
        "available": [name for name in INPUTS if available[name]],
        "missing": [name for name in INPUTS if not available[name]],
        "tables": {"files": tables, "inline_in_manuscript": inline_tables},
        "figures": figures,
        "bibliography": {"files": bibliography, "reference_list_in_manuscript": inline_references},
        "code": {"files": code, "languages": dict(languages.most_common()), "build_files": build},
        "data": {
            "files": data,
            "formats": dict(Counter(Path(name).suffix.casefold() for name in data).most_common()),
            "bytes": sum((root / name).stat().st_size for name in data),
        },
        "registration": {"documents": registration_docs, "cited_ids": registry_ids},
        "environment": environment,
        "notes": notes,
    }
