import re
import subprocess
import sys
import tomllib
from pathlib import Path

import yaml

from jaanch.cli import main

ROOT = Path(__file__).resolve().parent.parent
ROLES = sorted(path.stem for path in (ROOT / "agents" / "roles").glob("*.md"))
FINDERS = ["jaanch_check_consistency", "jaanch_check_prior_art", "jaanch_check_reasoning"]


def test_rendered_agents_are_current():
    result = subprocess.run(
        [sys.executable, "scripts/render_agents.py", "--check"], cwd=ROOT, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr


def test_codex_agents_have_required_fields():
    for name in ROLES:
        agent = tomllib.loads((ROOT / ".codex" / "agents" / f"{name}.toml").read_text())
        assert agent["name"] == name
        assert agent["description"]
        assert agent["developer_instructions"]


def test_claude_agents_have_frontmatter():
    for name in ROLES:
        _, frontmatter, body = (ROOT / ".claude" / "agents" / f"{name}.md").read_text().split("---\n", 2)
        meta = yaml.safe_load(frontmatter)
        assert meta["name"] == name
        assert meta["description"]
        assert body.strip()


def test_finders_carry_comment_rules_and_others_do_not():
    for name in ROLES:
        text = (ROOT / ".codex" / "agents" / f"{name}.toml").read_text()
        has_rules = "## How to write comments" in text
        assert has_rules == (name.startswith("jaanch_check_") and name != "jaanch_check_revision"), name


def test_skills_name_only_agents_that_exist():
    for skill in (ROOT / ".agents" / "skills").glob("*/SKILL.md"):
        mentioned = set(re.findall(r"jaanch_[a-z_]+[a-z]", skill.read_text()))
        assert mentioned and mentioned <= set(ROLES), (skill, mentioned - set(ROLES))


def test_instructions_command_prints_packaged_role(capsys):
    assert main(["instructions", "jaanch_verify_finding"]) == 0
    assert "You are the skeptic." in capsys.readouterr().out
    assert main(["instructions", "jaanch_nonexistent"]) == 2


def test_claude_skills_link_to_shared_skills():
    for skill in (ROOT / ".agents" / "skills").iterdir():
        link = ROOT / ".claude" / "skills" / skill.name
        assert link.is_symlink() and link.resolve() == skill.resolve()
