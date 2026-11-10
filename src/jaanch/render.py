"""Render review.json as the markdown a reader sees."""

SEVERITY_ORDER = ["critical", "major", "minor", "suggestion"]


def _blockquote(text: str) -> str:
    return "\n".join(f"> {line}" for line in text.splitlines())


def render_review(review: dict) -> str:
    paper = review["paper"]
    host = review["host"]
    comments = review["comments"]
    lines = [
        f"# Review: {paper['title']}",
        "",
        f"{len(comments)} comments · reviewed by jaanch on {host['name']} ({host['model']})",
        f"Source: `{paper['source_path']}` · sha256 `{paper['sha256'][:12]}`",
        "",
        "## Overall feedback",
        "",
    ]
    for number, item in enumerate(review["overall"], start=1):
        cited = ", ".join(item["comment_ids"])
        lines += [f"{number}. **{item['title']}** {item['message']}" + (f" ({cited})" if cited else ""), ""]

    by_severity = sorted(comments, key=lambda comment: SEVERITY_ORDER.index(comment["severity"]))
    lines += ["## Comments", ""]
    for comment in by_severity:
        lines += [
            f"### {comment['id']} · {comment['severity']} · {comment['title']}",
            "",
            f"*{comment['location']}* · {comment['kind']} · fix: {comment['fix_effort']}",
            "",
            _blockquote(comment["quote"]),
            "",
            comment["message"],
            "",
        ]
        if comment["suggestion"]:
            lines += [f"**Suggested fix.** {comment['suggestion']}", ""]
        if "verification" in comment:
            verification = comment["verification"]
            lines += [f"**Verification ({verification['status']}).** {verification['note']}", ""]
    return "\n".join(lines).rstrip() + "\n"
