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
