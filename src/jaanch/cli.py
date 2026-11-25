"""Command line for the deterministic steps of a jaanch review."""

import argparse
import json
import sys
from importlib.resources import files
from pathlib import Path

from jaanch import controls, exact, lit, register, xref
from jaanch.check import check_comments, check_review, check_revision_verdicts, read_jsonl
from jaanch.checklists import check_coverage, checklist_text, load_checklists
from jaanch.intake import inventory
from jaanch.paper_model import check_map
from jaanch.render import render_review
from jaanch.runs import merge_candidates, merge_verdicts, start_run


def _report(problems: list) -> int:
    for problem in problems:
        print(problem, file=sys.stderr)
    print(f"{len(problems)} problems", file=sys.stderr)
    return 1 if problems else 0


def _start(args: argparse.Namespace) -> int:
    try:
        run_dir = start_run(args.paper, args.reviews_dir, args.name, args.root)
    except ValueError as error:
        print(error, file=sys.stderr)
        return 2
    print(run_dir)
    return 0


def _merge(args: argparse.Namespace) -> int:
    kept, dropped = merge_candidates(args.run_dir)
    out = args.run_dir / "candidates_merged.jsonl"
    out.write_text("".join(json.dumps(comment) + "\n" for comment in kept))
    for line in dropped:
        print(f"dropped {line}", file=sys.stderr)
    print(f"kept {len(kept)}, dropped {len(dropped)} problems -> {out}")
    return 0


def _verdicts(args: argparse.Namespace) -> int:
    verdicts, problems = merge_verdicts(args.run_dir)
    out = args.run_dir / "verdicts.jsonl"
    out.write_text("".join(json.dumps(verdict) + "\n" for verdict in verdicts))
    print(f"{len(verdicts)} verdicts -> {out}")
    return _report(problems)


def _check(args: argparse.Namespace) -> int:
    if args.path.suffix == ".jsonl":
        return _report(check_comments(read_jsonl(args.path), args.paper.read_text()))
    return _report(check_review(json.loads(args.path.read_text()), args.paper))


def _check_revision(args: argparse.Namespace) -> int:
    prior = json.loads(args.prior_review.read_text())
    return _report(check_revision_verdicts(read_jsonl(args.verdicts), prior))


def _instructions(args: argparse.Namespace) -> int:
    path = files("jaanch").joinpath("agents", f"{args.agent}.md")
    if not path.is_file():
        available = sorted(
            item.name.removesuffix(".md") for item in files("jaanch").joinpath("agents").iterdir()
        )
        print(f"unknown agent {args.agent!r}; available: {', '.join(available)}", file=sys.stderr)
        return 2
    sys.stdout.write(path.read_text())
    return 0


def _checklists(args: argparse.Namespace) -> int:
    checklists = load_checklists()
    if args.run_dir:
        from jaanch.checklists import routed_modules

        routed = routed_modules(json.loads((args.run_dir / "map.json").read_text()), checklists)
        checklists = {name: checklists[name] for name in routed}
    for name, checklist in checklists.items():
        print(f"{name} ({len(checklist['checks'])} checks): {checklist['applies_when']}")
    return 0


SCHEMAS = {
    "paper-model": "paper_model.schema.json",
    "review": "review.schema.json",
    "checklist": "checklist.schema.json",
}


def _schema(args: argparse.Namespace) -> int:
    sys.stdout.write(files("jaanch").joinpath(SCHEMAS[args.name]).read_text())
    return 0


def _checklist(args: argparse.Namespace) -> int:
    text = checklist_text(args.module)
    if text is None:
        print(
            f"unknown checklist {args.module!r}; available: {', '.join(load_checklists())}", file=sys.stderr
        )
        return 2
    sys.stdout.write(text)
    return 0


def _check_map(args: argparse.Namespace) -> int:
    summary, problems = check_map(args.run_dir)
    for line in summary:
        print(line)
    return _report(problems)


def _coverage(args: argparse.Namespace) -> int:
    summary, problems = check_coverage(args.run_dir)
    for line in summary:
        print(line)
    return _report(problems)


def _intake(args: argparse.Namespace) -> int:
    if not args.path.exists():
        print(f"{args.path} does not exist", file=sys.stderr)
        return 2
    text = json.dumps(inventory(args.path), indent=2) + "\n"
    if args.out:
        args.out.write_text(text)
    else:
        sys.stdout.write(text)
    return 0


def _lit(args: argparse.Namespace) -> int:
    folder = args.folder
    if args.lit_command == "search":
        for query in args.query:
            returned, new = lit.search(folder, query, args.limit)
            print(f"{query!r}: {returned} from OpenAlex, {new} new candidates")
    elif args.lit_command == "expand":
        ids = args.ids or [i for i, d in lit.screen_decisions(folder).items() if d["decision"] == "include"]
        counts = lit.expand(folder, ids, backward=not args.forward_only, forward=not args.backward_only)
        print(
            f"from {len(ids)} works: {counts['backward']} new by references, "
            f"{counts['forward']} new by citing works"
        )
    elif args.lit_command == "prefilter":
        excluded = lit.prefilter(folder, args.terms, args.also)
        print(f"{excluded} excluded; {len(lit.unscreened(folder))} left to screen")
    elif args.lit_command == "unscreened":
        out = args.out or folder / "unscreened.jsonl"
        rows = lit.unscreened(folder)
        out.write_text(
            "".join(
                json.dumps({k: r[k] for k in ("id", "title", "year", "venue", "abstract")}) + "\n"
                for r in rows
            )
        )
        print(f"{len(rows)} unscreened -> {out}")
    elif args.lit_command == "merge-screen":
        merged, problems = lit.merge_screen(folder, args.outputs)
        print(f"merged {merged} decisions")
        return _report(problems)
    elif args.lit_command == "add":
        print(f"{lit.add(folder, args.ids, args.how)} new candidates")
    elif args.lit_command == "fetch":
        for work_id, outcome in lit.fetch(folder, tuple(args.decisions)).items():
            print(f"{work_id}: {outcome}")
    elif args.lit_command == "status":
        print(json.dumps(lit.status(folder), indent=2))
    elif args.lit_command == "check":
        return _report(lit.check_rows(folder))
    elif args.lit_command == "recall":
        truth = [line for line in args.truth.read_text().splitlines() if line.strip()]
        print(json.dumps(lit.recall(folder, truth), indent=2))
    return 0


def _exact(args: argparse.Namespace) -> int:
    summary, problems = exact.run_exact(args.run_dir)
    print(json.dumps(summary, indent=2))
    return _report(problems)


def _xref(args: argparse.Namespace) -> int:
    summary, problems = xref.run_xref(args.run_dir)
    print(json.dumps(summary, indent=2))
    return _report(problems)


def _controls(args: argparse.Namespace) -> int:
    if args.action == "make":
        result = controls.make_controls(args.run_dir, args.name, share=args.share, seed=args.seed)
    else:
        result = controls.score_controls(args.run_dir, args.name)
    print(json.dumps(result, indent=2))
    return 0


def _checks(args: argparse.Namespace) -> int:
    rows = register.load_register()
    if args.action == "page":
        from jaanch.checklists import load_checklists

        args.out.write_text(register.render_page(rows, load_checklists()))
        print(f"{len(rows)} checks -> {args.out}")
        return 0
    if args.action == "grid":
        table = register.grid(rows, ours_only=args.ours)
        width = max(len(m) for m in register.MECHANISMS)
        print(f"{'':13}" + "".join(f"{m:>{width + 2}}" for m in register.MECHANISMS) + f"{'total':>8}")
        for pillar, counts in table.items():
            cells = "".join(f"{(counts[m] or '.'):>{width + 2}}" for m in register.MECHANISMS)
            print(f"{pillar:13}{cells}{sum(counts.values()):>8}")
        return 0
    ours = True if args.ours else None
    for row in register.select(rows, args.pillar, args.mechanism, args.design, ours):
        where = ", ".join(row["ours"]) or "external only: " + ", ".join(row["external"][:3])
        print(f"{row['cid']:55} {row['pillar']:12} {row['mechanism']:15} {where}")
    return 0


def _sources(args: argparse.Namespace) -> int:
    from jaanch import sources

    try:
        key = sources.add(args.doi, args.title)
    except (LookupError, ValueError) as error:
        print(error, file=sys.stderr)
        return 1
    print(key)
    return 0


def _forensics(args: argparse.Namespace) -> int:
    from jaanch.forensics import run_forensics

    summary = run_forensics(args.run_dir)
    print(json.dumps(summary, indent=2))
    return 0


def _render(args: argparse.Namespace) -> int:
    sys.stdout.write(render_review(json.loads(args.review.read_text())))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="jaanch")
    commands = parser.add_subparsers(required=True)

    start = commands.add_parser(
        "start", help="create reviews/<slug>/ for a manuscript or a submission folder"
    )
    start.add_argument(
        "paper", type=Path, help="a manuscript, or a folder holding one with its code and data"
    )
    start.add_argument("--reviews-dir", type=Path, default=Path("reviews"))
    start.add_argument("--name", help="run folder name; defaults to the file name")
    start.add_argument(
        "--root", type=Path, help="folder the paper may read files from; defaults to its git repo"
    )
    start.set_defaults(handler=_start)

    merge = commands.add_parser("merge", help="merge candidates, dropping invalid or unanchored ones")
    merge.add_argument("run_dir", type=Path)
    merge.set_defaults(handler=_merge)

    verdicts = commands.add_parser("verdicts", help="merge and validate the skeptics' verdicts")
    verdicts.add_argument("run_dir", type=Path)
    verdicts.set_defaults(handler=_verdicts)

    check = commands.add_parser("check", help="validate review.json or a comments .jsonl")
    check.add_argument("path", type=Path)
    check.add_argument("--paper", type=Path, required=True)
    check.set_defaults(handler=_check)

    revision = commands.add_parser("check-revision", help="validate revision-check verdicts")
    revision.add_argument("verdicts", type=Path)
    revision.add_argument("--prior-review", type=Path, required=True)
    revision.set_defaults(handler=_check_revision)

    instructions = commands.add_parser("instructions", help="print a subagent's instructions")
    instructions.add_argument("agent")
    instructions.set_defaults(handler=_instructions)

    intake = commands.add_parser(
        "intake", help="list what a file or folder contains, as the inputs checks need"
    )
    intake.add_argument("path", type=Path)
    intake.add_argument("--out", type=Path, help="write inventory.json here instead of printing it")
    intake.set_defaults(handler=_intake)

    schema = commands.add_parser("schema", help="print a JSON schema")
    schema.add_argument("name", choices=sorted(SCHEMAS))
    schema.set_defaults(handler=_schema)

    listing = commands.add_parser(
        "checklists", help="list the design checklists, or with a run folder only those its designs route to"
    )
    listing.add_argument("run_dir", type=Path, nargs="?")
    listing.set_defaults(handler=_checklists)

    checklist = commands.add_parser("checklist", help="print one design checklist")
    checklist.add_argument("module")
    checklist.set_defaults(handler=_checklist)

    check_map_cmd = commands.add_parser(
        "check-map", help="validate map.json, the paper model, against the paper"
    )
    check_map_cmd.add_argument("run_dir", type=Path)
    check_map_cmd.set_defaults(handler=_check_map)

    coverage = commands.add_parser(
        "coverage", help="check that every routed checklist item has a verdict and every flag a comment"
    )
    coverage.add_argument("run_dir", type=Path)
    coverage.set_defaults(handler=_coverage)

    exact_cmd = commands.add_parser(
        "exact", help="recompute reported statistics: statcheck, GRIM/GRIMMER/DEBIT, table cells"
    )
    exact_cmd.add_argument("run_dir", type=Path)
    exact_cmd.set_defaults(handler=_exact)

    xref_cmd = commands.add_parser("xref", help="group extracted facts by key and list keys stated two ways")
    xref_cmd.add_argument("run_dir", type=Path)
    xref_cmd.set_defaults(handler=_xref)

    checks_cmd = commands.add_parser(
        "checks", help="the check register: list checks, or a pillar x mechanism grid"
    )
    checks_cmd.add_argument("action", choices=["list", "grid", "page"])
    checks_cmd.add_argument(
        "--out", type=Path, default=Path("atlas.html"), help="where page writes the atlas"
    )
    checks_cmd.add_argument("--pillar", choices=register.PILLARS + register.OTHER)
    checks_cmd.add_argument("--mechanism", choices=register.MECHANISMS)
    checks_cmd.add_argument("--design")
    checks_cmd.add_argument("--ours", action="store_true", help="only checks our tools implement")
    checks_cmd.set_defaults(handler=_checks)

    sources_cmd = commands.add_parser(
        "sources", help="add a work to checks/sources.bib from its Crossref record"
    )
    sources_cmd.add_argument("action", choices=["add"])
    sources_cmd.add_argument("doi")
    sources_cmd.add_argument("title", help="the title you expect; a DOI that resolves elsewhere is refused")
    sources_cmd.set_defaults(handler=_sources)

    forensics_cmd = commands.add_parser(
        "forensics", help="screen deposited data for duplicate records and non-uniform last digits"
    )
    forensics_cmd.add_argument("run_dir", type=Path)
    forensics_cmd.set_defaults(handler=_forensics)

    controls_cmd = commands.add_parser(
        "controls", help="mix known-wrong comments into a skeptic batch, and score them"
    )
    controls_cmd.add_argument("action", choices=["make", "score"])
    controls_cmd.add_argument("run_dir", type=Path)
    controls_cmd.add_argument("--name", default="xref", help="candidates/<name>.jsonl")
    controls_cmd.add_argument("--share", type=float, default=0.5, help="controls per real candidate")
    controls_cmd.add_argument("--seed", type=int, default=0)
    controls_cmd.set_defaults(handler=_controls)

    lit_parser = commands.add_parser("lit", help="deterministic steps of a literature map")
    lit_commands = lit_parser.add_subparsers(dest="lit_command", required=True)

    def lit_sub(name: str, help: str) -> argparse.ArgumentParser:
        sub = lit_commands.add_parser(name, help=help)
        sub.add_argument("folder", type=Path, help="the literature map folder")
        return sub

    search_cmd = lit_sub("search", help="add OpenAlex and Semantic Scholar search results")
    search_cmd.add_argument("--query", action="append", required=True)
    search_cmd.add_argument("--limit", type=int, default=200)
    expand_cmd = lit_sub("expand", help="add references and citing works of given or included works")
    expand_cmd.add_argument("--ids", nargs="*", help="OpenAlex ids; defaults to every included work")
    expand_cmd.add_argument("--backward-only", action="store_true")
    expand_cmd.add_argument("--forward-only", action="store_true")
    prefilter_cmd = lit_sub("prefilter", help="exclude candidates that mention none of the terms")
    prefilter_cmd.add_argument("--terms", nargs="+", required=True)
    prefilter_cmd.add_argument("--also", nargs="+", help="a second set, one of which must also appear")
    unscreened_cmd = lit_sub("unscreened", help="write candidates still to screen, for a screener")
    unscreened_cmd.add_argument("--out", type=Path)
    merge_cmd = lit_sub("merge-screen", help="merge screeners' decision files into screen.jsonl")
    merge_cmd.add_argument("outputs", nargs="+", type=Path)
    add_cmd = lit_sub("add", help="add works by DOI or OpenAlex id, e.g. from web search")
    add_cmd.add_argument("ids", nargs="+")
    add_cmd.add_argument("--how", default="added")
    fetch_cmd = lit_sub("fetch", help="download open PDFs of screened works and extract text")
    fetch_cmd.add_argument("--decisions", nargs="+", default=["include"], choices=["include", "unsure"])
    lit_sub("status", help="counts at each stage")
    lit_sub("check", help="validate rows.jsonl against the schema and the works' text")
    recall_cmd = lit_sub("recall", help="score candidates and inclusions against an answer key")
    recall_cmd.add_argument(
        "--truth", type=Path, required=True, help="file of OpenAlex ids or DOIs, one per line"
    )
    lit_parser.set_defaults(handler=_lit)

    render = commands.add_parser("render", help="print review.json as markdown")
    render.add_argument("review", type=Path)
    render.set_defaults(handler=_render)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
