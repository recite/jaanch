import hashlib

import pytest

PAPER = """# Effects of Information on Turnout

## 3 Results

Table 2 reports the main estimates. The treat-
ment effect is 0.42 and significant at the 5 percent level, which implies
that the reminder raised turnout by a third relative to the control mean
of 1.26.

| | (1) | (2) |
|---|---|---|
| Reminder | 0.42 | 0.31 |
| N | 1,204 | 1,204 |

The ﬁrst column uses no controls.
"""


@pytest.fixture
def paper_path(tmp_path):
    path = tmp_path / "paper.txt"
    path.write_text(PAPER)
    return path


def make_comment(**overrides):
    comment = {
        "id": "consistency_001",
        "goal": "consistency",
        "title": "Effect size described inconsistently",
        "quote": "raised turnout by a third relative to the control mean",
        "location": "Section 3, paragraph 1",
        "message": "0.42 / 1.26 = 0.333, so 'a third' holds for column 1 only.",
        "suggestion": "Say which column the claim refers to.",
        "severity": "minor",
        "kind": "substance/contradiction",
        "fix_effort": "edit_in_place",
    }
    comment.update(overrides)
    return comment


def make_review(paper_path, comments=None, overall_ids=None):
    comments = comments if comments is not None else [make_comment()]
    return {
        "paper": {
            "title": "Effects of Information on Turnout",
            "source_path": str(paper_path),
            "sha256": hashlib.sha256(paper_path.read_bytes()).hexdigest(),
        },
        "host": {"name": "claude_code", "model": "claude-opus-5-5"},
        "overall": [
            {
                "title": "Effect size",
                "message": "The headline magnitude needs a column.",
                "comment_ids": overall_ids if overall_ids is not None else [c["id"] for c in comments],
            }
        ],
        "comments": comments,
    }
