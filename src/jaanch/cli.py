"""Command line for the deterministic steps of a jaanch review."""

import argparse
import json
import sys
from importlib.resources import files
from pathlib import Path

from jaanch.check import check_comments, check_review, check_verdicts, read_jsonl
from jaanch.render import render_review
from jaanch.runs import merge_candidates, start_run


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


def _check(args: argparse.Namespace) -> int:
    if args.path.suffix == ".jsonl":
        return _report(check_comments(read_jsonl(args.path), args.paper.read_text()))
    return _report(check_review(json.loads(args.path.read_text()), args.paper))


def _check_revision(args: argparse.Namespace) -> int:
    prior = json.loads(args.prior_review.read_text())
    return _report(check_verdicts(read_jsonl(args.verdicts), prior))


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


def _render(args: argparse.Namespace) -> int:
    sys.stdout.write(render_review(json.loads(args.review.read_text())))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="jaanch")
    commands = parser.add_subparsers(required=True)

    start = commands.add_parser("start", help="create reviews/<slug>/ for a paper")
    start.add_argument("paper", type=Path)
    start.add_argument("--reviews-dir", type=Path, default=Path("reviews"))
    start.add_argument("--name", help="run folder name; defaults to the file name")
    start.add_argument(
        "--root", type=Path, help="folder the paper may read files from; defaults to its git repo"
    )
    start.set_defaults(handler=_start)

    merge = commands.add_parser("merge", help="merge candidates, dropping invalid or unanchored ones")
    merge.add_argument("run_dir", type=Path)
    merge.set_defaults(handler=_merge)

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

    render = commands.add_parser("render", help="print review.json as markdown")
    render.add_argument("review", type=Path)
    render.set_defaults(handler=_render)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
