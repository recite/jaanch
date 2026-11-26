from jaanch import register

ROWS = [
    {
        "cid": "consistency.a",
        "pillar": "record",
        "second_pillar": None,
        "mechanism": "cross_reference",
        "name": "a",
        "definition": "d",
        "min_inputs": ["paper_text"],
        "script_exists": False,
        "ours": ["jaanch"],
        "external": [],
    },
    {
        "cid": "identification.b",
        "pillar": "internal",
        "second_pillar": "external",
        "mechanism": "judgment",
        "name": "b",
        "definition": "d",
        "min_inputs": ["paper_text"],
        "script_exists": False,
        "ours": [],
        "external": ["AMICUS"],
    },
]


def test_grid_counts_second_pillars_and_can_restrict_to_ours():
    table = register.grid(ROWS)
    assert table["record"]["cross_reference"] == 1
    assert table["internal"]["judgment"] == 1 and table["external"]["judgment"] == 1
    assert register.grid(ROWS, ours_only=True)["internal"]["judgment"] == 0


def test_select_and_validate():
    assert [r["cid"] for r in register.select(ROWS, pillar="external")] == ["identification.b"]
    assert [r["cid"] for r in register.select(ROWS, ours=False)] == ["identification.b"]
    assert register.validate_register(ROWS) == []
    assert register.validate_register([dict(ROWS[0], sources=["nobody2099nothing"])])
    bad = dict(ROWS[0], pillar="vibes")
    assert register.validate_register([bad, ROWS[0]])


def test_shipped_register_is_valid():
    assert register.validate_register(register.load_register()) == []


def test_module_items_must_point_at_register_checks():
    import copy

    from jaanch.checklists import load_checklists, validate_checklists

    modules = copy.deepcopy(load_checklists())
    modules["did"]["checks"][0]["register"] = ["identification.no_such_check"]
    assert any("not in the register" in p.message for p in validate_checklists(modules))


def test_page_embeds_every_check(tmp_path):
    from jaanch.cli import main

    out = tmp_path / "atlas.html"
    assert main(["checks", "page", "--out", str(out)]) == 0
    text = out.read_text()
    assert "Methods → implications" in text and "__DATA__" not in text
    import json

    data = json.loads(text.split('<script id="data" type="application/json">')[1].split("</script>")[0])
    assert len(data["rows"]) == len(register.load_register())
    assert {m["title"] for m in data["modules"]} >= {"Randomized experiments", "Universal checks"}


def test_sources_bib_has_unique_keys_and_a_doi_url_or_note():
    import re
    from importlib.resources import files

    text = files("jaanch").joinpath("checks", "sources.bib").read_text()
    entries = re.findall(r"@\w+\{([^,]+),(.*?)\n\}", text, re.S)
    keys = [key for key, _ in entries]
    assert len(entries) >= 40 and len(keys) == len(set(keys))
    locators = ("doi = {10.", "url = {https://", "note = {")
    assert all(any(locator in body for locator in locators) for _, body in entries)


def test_bib_citations_and_unknown_keys_are_caught():
    import copy

    from jaanch.checklists import load_checklists, validate_checklists

    assert register.load_bib()["cronbach1955construct"].startswith("Cronbach and Meehl (1955)")
    modules = copy.deepcopy(load_checklists())
    modules["did"]["checks"][0]["sources"] = ["nobody2099nothing: ch. 1"]
    assert any("not in sources.bib" in p.message for p in validate_checklists(modules))
