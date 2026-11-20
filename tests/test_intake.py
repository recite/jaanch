import json

from jaanch.cli import main
from jaanch.intake import inventory

PAPER = (
    "\\documentclass{article}\n\\begin{document}\nWe use AEARCTR-0001234.\n"
    "\\input{../tabs/main}\n\\includegraphics{fig1}\n\\end{document}\n"
)


def make(tmp_path, files):
    for name, text in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    return tmp_path


def test_full_replication_package(tmp_path):
    make(
        tmp_path,
        {
            "ms/main.tex": PAPER,
            "ms/refs.bib": "@article{a, title={x}}",
            "tabs/main.tex": "\\begin{tabular}{ll}a & b\\end{tabular}",
            "tabs/est.csv": "a,b\n1,2\n",
            "figs/fig1.png": "png",
            "R/models.R": "lm(y ~ x)",
            "Makefile": "all:",
            "data/derived/main.csv": "y,x\n1,2\n",
            "renv.lock": "{}",
        },
    )
    inv = inventory(tmp_path)
    assert inv["manuscript"]["path"] == "ms/main.tex"
    assert inv["available"] == ["paper_text", "tables", "figures", "bibliography", "code", "data"]
    assert inv["missing"] == ["registration"]
    assert sorted(inv["tables"]["files"]) == ["tabs/est.csv", "tabs/main.tex"]
    assert inv["data"]["files"] == ["data/derived/main.csv"]
    assert inv["code"]["languages"] == {"R": 1}
    assert inv["code"]["build_files"] == ["Makefile"]
    assert inv["registration"]["cited_ids"] == ["AEA RCT Registry: AEARCTR-0001234"]
    assert any("can be fetched" in note for note in inv["notes"])


def test_source_beats_compiled_pdf_and_drafts_are_flagged(tmp_path):
    make(tmp_path, {"ms/main.tex": PAPER, "ms/old_draft.tex": PAPER + "x" * 10})
    (tmp_path / "ms" / "main.pdf").write_bytes(b"%PDF-1.4")
    inv = inventory(tmp_path)
    assert inv["manuscript"]["format"] == "tex"
    assert len(inv["manuscript"]["other_candidates"]) == 1


def test_markdown_paper_alone(tmp_path):
    text = (
        "# A paper\n\n"
        + "word " * 1600
        + "\n\n| a | b |\n|---|---|\n| 1 | 2 |\n\n## References\n\nSmith 2020.\n"
    )
    make(tmp_path, {"paper.md": text, "README.md": "word " * 2000})
    inv = inventory(tmp_path)
    assert inv["manuscript"]["path"] == "paper.md"
    assert inv["available"] == ["paper_text", "tables", "bibliography"]
    assert inv["bibliography"]["reference_list_in_manuscript"]


def test_code_without_data_is_noted(tmp_path):
    make(tmp_path, {"src/fit.py": "print(1)"})
    inv = inventory(tmp_path)
    assert inv["manuscript"]["path"] is None
    assert inv["available"] == ["code"]
    assert "code without data: code can be read but not rerun" in inv["notes"]


def test_registration_document_is_found(tmp_path):
    make(tmp_path, {"paper.md": "word " * 1600, "docs/pre-analysis-plan.md": "We will test H1."})
    assert "registration" in inventory(tmp_path)["available"]


def test_intake_command(tmp_path, capsys):
    make(tmp_path, {"paper.md": "word " * 1600})
    assert main(["intake", str(tmp_path)]) == 0
    assert json.loads(capsys.readouterr().out)["manuscript"]["path"] == "paper.md"
    assert main(["intake", str(tmp_path / "missing")]) == 2


def test_knitted_manuscript_records_its_source_and_figure_data_are_exhibits(tmp_path):
    make(tmp_path, {"ms/paper.tex": PAPER, "ms/paper.Rmd": "`r 1+1`", "ms/figures/kde.csv": "x\n1\n"})
    inv = inventory(tmp_path)
    assert inv["manuscript"]["path"] == "ms/paper.tex"
    assert inv["manuscript"]["generated_from"] == "ms/paper.Rmd"
    assert inv["manuscript"]["other_candidates"] == []
    assert inv["tables"]["files"] == ["ms/figures/kde.csv"]
    assert inv["data"]["files"] == []
