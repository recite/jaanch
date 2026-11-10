"""Set up a review run folder and merge what the finder agents wrote."""

import json
import re
import shutil
import subprocess
import unicodedata
from pathlib import Path

from jaanch.check import check_comment, normalize_text, read_jsonl, sha256_file

TEXT_SUFFIXES = {".md", ".markdown", ".tex", ".txt"}
FIGURE_PATTERN = re.compile(r"\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}")
FIGURE_SUFFIXES = ["", ".pdf", ".png", ".jpg", ".jpeg", ".eps"]
# A zero-argument \newcommand whose body nests braces at most one level deep.
MACRO_DEFINITION = re.compile(r"\\newcommand\*?\{?\\([A-Za-z]+)\}?\{((?:[^{}#]|\{[^{}#]*\})*)\}")


def slugify(name: str) -> str:
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "_", ascii_name.casefold()).strip("_") or "paper"


def flatten_latex(paper: Path) -> tuple[str, str]:
    """Inline \\input files, tables and the bibliography with latexpand.

    Without this a reviewer sees `\\input{../tabs/main.tex}` instead of the
    table, and cannot check the text against it.
    """
    if shutil.which("latexpand") is None:
        return paper.read_text(), "copied; latexpand not found, so \\input files are missing"
    command = ["latexpand", "--empty-comments"]
    bbl = paper.with_suffix(".bbl")
    if bbl.exists():
        command += ["--expand-bbl", bbl.name]
    result = subprocess.run(
        command + [paper.name], cwd=paper.parent, capture_output=True, text=True, check=True
    )
    method = "flattened with latexpand" + (" including the bibliography" if bbl.exists() else "")
    return expand_macros(result.stdout), method + "; zero-argument macros expanded"


def expand_macros(text: str) -> str:
    """Replace zero-argument macros in the document body with their values.

    Papers that generate their numbers write them as macros (`\\poolEstimate{}`),
    so a reviewer would see names instead of numbers, and quotes would too.
    de-macro (TeX Live) expands only macros defined in *-private.sty files, so
    it does not help here. The definitions stay in the preamble.
    """
    start = text.find("\\begin{document}")
    if start == -1:
        return text
    preamble, body = text[:start], text[start:]
    macros = dict(MACRO_DEFINITION.findall(preamble))
    if not macros:
        return text
    pattern = re.compile(
        r"\\(" + "|".join(sorted(map(re.escape, macros), key=len, reverse=True)) + r")(?![A-Za-z@])(\{\})?"
    )
    # Values can refer to other macros; three passes cover any realistic depth.
    for _ in range(3):
        body = pattern.sub(lambda match: macros[match.group(1)], body)
    return preamble + body


def find_figures(text: str, base: Path) -> list[str]:
    """Absolute paths of figure files, so agents that can view images can look."""
    figures = []
    for name in FIGURE_PATTERN.findall(text):
        for suffix in FIGURE_SUFFIXES:
            candidate = (base / f"{name}{suffix}").resolve()
            if candidate.is_file():
                figures.append(str(candidate))
                break
    return figures


def start_run(paper: Path, reviews_dir: Path, name: str | None = None) -> Path:
    """Write the paper's full text to reviews/<slug>/paper.txt and record what was reviewed."""
    suffix = paper.suffix.casefold()
    if suffix not in TEXT_SUFFIXES:
        raise ValueError(
            f"{paper.suffix} is not supported yet; give jaanch .md, .tex or .txt "
            "(PDF ingest is an open decision in docs/design.md)"
        )
    if suffix == ".tex":
        text, method = flatten_latex(paper)
    else:
        text, method = paper.read_text(), "copied"

    run_dir = reviews_dir / slugify(name or paper.stem)
    (run_dir / "candidates").mkdir(parents=True, exist_ok=True)
    (run_dir / "paper.txt").write_text(text)
    run = {
        "source_path": str(paper.resolve()),
        "sha256": sha256_file(run_dir / "paper.txt"),
        "method": method,
        "figures": find_figures(text, paper.resolve().parent),
    }
    (run_dir / "run.json").write_text(json.dumps(run, indent=2) + "\n")
    return run_dir


def merge_candidates(run_dir: Path) -> tuple[list[dict], list[str]]:
    """Merge candidates/*.jsonl, keeping comments that validate and anchor."""
    paper_normalized = normalize_text((run_dir / "paper.txt").read_text())
    kept, dropped = [], []
    seen = set()
    for path in sorted((run_dir / "candidates").glob("*.jsonl")):
        for comment in read_jsonl(path):
            where = f"{path.name}:{comment.get('id', '?')}"
            problems = [str(problem) for problem in check_comment(comment, paper_normalized, where)]
            if comment.get("id") in seen:
                problems.append(f"{where}: duplicate id")
            if problems:
                dropped += problems
                continue
            seen.add(comment["id"])
            kept.append(comment)
    return kept, dropped
