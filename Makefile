SKILLS := $(notdir $(wildcard .agents/skills/*))
AGENTS := $(basename $(notdir $(wildcard agents/roles/*.md)))
PYTHON_SOURCES := src scripts tests eval

.PHONY: sync lint format test agents check-agents ci ci-docker install uninstall

sync:
	uv sync

lint: sync
	uv run black --check $(PYTHON_SOURCES)
	uv run isort --check-only $(PYTHON_SOURCES)
	uv run flake8 $(PYTHON_SOURCES)

format: sync
	uv run black $(PYTHON_SOURCES)
	uv run isort $(PYTHON_SOURCES)

agents: sync
	uv run python scripts/render_agents.py

check-agents: sync
	uv run python scripts/render_agents.py --check

test: sync
	uv run pytest

ci: lint check-agents test

ci-docker:
	docker run --rm -v "$(CURDIR)":/src -w /src python:3.12-slim \
		sh -c "pip install -q uv && apt-get update -qq && apt-get install -y -qq --no-install-recommends make texlive-extra-utils >/dev/null \
		&& UV_PROJECT_ENVIRONMENT=/tmp/venv make ci"

# Links rather than copies, so edits in this repo reach both CLIs at once.
# Codex skills go in ~/.codex/skills, not ~/.agents/skills, which is often
# someone's own skills repository.
install: check-agents
	uv tool install --force --editable .
	mkdir -p $(HOME)/.claude/skills $(HOME)/.claude/agents $(HOME)/.codex/skills $(HOME)/.codex/agents
	for skill in $(SKILLS); do \
		ln -sfn "$(CURDIR)/.agents/skills/$$skill" "$(HOME)/.claude/skills/$$skill"; \
		ln -sfn "$(CURDIR)/.agents/skills/$$skill" "$(HOME)/.codex/skills/$$skill"; \
	done
	for agent in $(AGENTS); do \
		ln -sfn "$(CURDIR)/.claude/agents/$$agent.md" "$(HOME)/.claude/agents/$$agent.md"; \
		ln -sfn "$(CURDIR)/.codex/agents/$$agent.toml" "$(HOME)/.codex/agents/$$agent.toml"; \
	done

uninstall:
	uv tool uninstall jaanch || true
	for skill in $(SKILLS); do rm -f "$(HOME)/.claude/skills/$$skill" "$(HOME)/.codex/skills/$$skill"; done
	for agent in $(AGENTS); do rm -f "$(HOME)/.claude/agents/$$agent.md" "$(HOME)/.codex/agents/$$agent.toml"; done
