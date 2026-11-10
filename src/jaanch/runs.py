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
FIGURE_SUFFIXES = [".pdf", ".png", ".jpg", ".jpeg", ".eps"]
# latexpand --verbose names every file it opens, whatever the directive
# (\\input, \\include, ...), so checking these lines fails closed.
OPENED_FILE = re.compile(r"^\s*Found \w+ for file: (.+)$", re.MULTILINE)
# Limits for papers we did not write: a macro that refers to itself, or a
# chain of macros that doubles at each step, must not exhaust memory.
MAX_MACRO_VALUE = 1_000
MAX_EXPANSION_FACTOR = 2
# A zero-argument \newcommand whose body nests braces at most one level deep.
MACRO_DEFINITION = re.compile(r"\\newcommand\*?\{?\\([A-Za-z]+)\}?\{((?:[^{}#]|\{[^{}#]*\})*)\}")


def slugify(name: str) -> str:
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "_", ascii_name.casefold()).strip("_") or "paper"


def project_root(paper: Path) -> Path:
    """The git repository holding the paper, or else the paper's folder."""
    result = subprocess.run(
        ["git", "-C", str(paper.parent), "rev-parse", "--show-toplevel"], capture_output=True, text=True
    )
    return Path(result.stdout.strip()).resolve() if result.returncode == 0 else paper.parent.resolve()


def check_root(root: Path, paper: Path) -> None:
    """Refuse a root that does not hold the paper, or that would expose a home folder.

    A submitted manuscript's own .git can point git anywhere, so the root
    git reports is checked rather than trusted.
    """
    home = Path.home().resolve()
    if not paper.resolve().is_relative_to(root):
        raise ValueError(f"root {root} does not contain the paper")
    if root == home or home.is_relative_to(root):
        raise ValueError(f"root {root} would expose your home folder; pass a narrower --root")


def flatten_latex(paper: Path, root: Path) -> tuple[str, str]:
    """Inline \\input files, tables and the bibliography with latexpand.

    Without this a reviewer sees `\\input{../tabs/main.tex}` instead of the
    table, and cannot check the text against it. A manuscript under review may
    come from someone else, so every file it pulls in must sit inside `root`;
    otherwise `\\input{~/.ssh/id_rsa}` would put that file in front of agents
    that can reach the web.
    """
    if shutil.which("latexpand") is None:
        return paper.read_text(), "copied; latexpand not found, so \\input files are missing"
    command = ["latexpand", "--empty-comments", "--explain", "--verbose"]
    bbl = paper.with_suffix(".bbl")
    if bbl.exists():
        command += ["--expand-bbl", bbl.name]
    result = subprocess.run(
        command + [paper.name], cwd=paper.parent, capture_output=True, text=True, check=True
    )
    outside = [
        name
        for name in OPENED_FILE.findall(result.stderr)
        if not (paper.parent / name.strip()).resolve().is_relative_to(root)
    ]
    if outside:
        raise ValueError(
            f"the paper reads files outside {root}: {', '.join(outside)}; pass --root to allow them"
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
    macros = {
        name: value
        for name, value in MACRO_DEFINITION.findall(preamble)
        if len(value) <= MAX_MACRO_VALUE and f"\\{name}" not in value
    }
    if not macros:
        return text
    pattern = re.compile(
        r"\\(" + "|".join(sorted(map(re.escape, macros), key=len, reverse=True)) + r")(?![A-Za-z@])(\{\})?"
    )
    # Values can refer to other macros; three passes cover any realistic depth.
    limit = MAX_EXPANSION_FACTOR * len(body)
    for _ in range(3):
        body = pattern.sub(lambda match: macros[match.group(1)], body)
        if len(body) > limit:
            raise ValueError("macro expansion more than doubled the paper; refusing to continue")
    return preamble + body


def find_figures(text: str, base: Path, root: Path) -> list[str]:
    """Absolute paths of figure files inside root, so agents that can view images can look."""
    figures = []
    for name in FIGURE_PATTERN.findall(text):
        stem = Path(name)
        names = (
            [name] if stem.suffix.casefold() in FIGURE_SUFFIXES else [f"{name}{s}" for s in FIGURE_SUFFIXES]
        )
        for candidate_name in names:
            candidate = (base / candidate_name).resolve()
            if candidate.is_file() and candidate.is_relative_to(root):
                figures.append(str(candidate))
                break
    return figures


def start_run(paper: Path, reviews_dir: Path, name: str | None = None, root: Path | None = None) -> Path:
    """Write the paper's full text to reviews/<slug>/paper.txt and record what was reviewed."""
    suffix = paper.suffix.casefold()
    if suffix not in TEXT_SUFFIXES:
        raise ValueError(
            f"{paper.suffix} is not supported yet; give jaanch .md, .tex or .txt "
            "(PDF ingest is an open decision in docs/design.md)"
        )
    root = (root or project_root(paper)).resolve()
    check_root(root, paper)
    if suffix == ".tex":
        text, method = flatten_latex(paper, root)
    else:
        text, method = paper.read_text(), "copied"

    run_dir = reviews_dir / slugify(name or paper.stem)
    (run_dir / "candidates").mkdir(parents=True, exist_ok=True)
    (run_dir / "paper.txt").write_text(text)
    run = {
        "source_path": str(paper.resolve()),
        "sha256": sha256_file(run_dir / "paper.txt"),
        "method": method,
        "figures": find_figures(text, paper.resolve().parent, root),
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
