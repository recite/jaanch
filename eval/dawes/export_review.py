"""Write a jaanch review.json in the Dawes benchmark's review format.

The benchmark (github.com/Dawes-Institute/ai-peer-review-benchmark) scores
`benchmark/results/<provider>/paper_<n>_review.json`. Its judge reads only the
first 600 characters of each description, so the problem goes first.
"""

import argparse
import json
from pathlib import Path


def to_finding(comment: dict) -> dict:
    return {
        "category": comment["goal"],
        "subcategory": comment["kind"],
        "description": f"{comment['title']}. {comment['message']}",
        "quote": comment["quote"],
        "location": comment["location"],
        "severity": comment["severity"],
    }


def export_review(review: dict, paper_id: int, provider: str) -> dict:
    return {
        "paper_id": paper_id,
        "provider_name": provider,
        "issues": [to_finding(comment) for comment in review["comments"]],
        "raw_response": None,
        "model_id": review["host"]["model"],
        "token_usage": None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Export a jaanch review for the Dawes benchmark.")
    parser.add_argument("review", type=Path, help="jaanch review.json")
    parser.add_argument("--paper-id", type=int, required=True)
    parser.add_argument("--provider", default="jaanch")
    parser.add_argument("--results-dir", type=Path, required=True, help="the benchmark's benchmark/results")
    args = parser.parse_args()

    out = args.results_dir / args.provider / f"paper_{args.paper_id}_review.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    exported = export_review(json.loads(args.review.read_text()), args.paper_id, args.provider)
    out.write_text(json.dumps(exported, indent=2) + "\n")
    print(f"{len(exported['issues'])} findings -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
