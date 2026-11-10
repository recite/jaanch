import json
import shutil
from pathlib import Path

import pytest

from jaanch.runs import start_run

pytestmark = pytest.mark.skipif(shutil.which("latexpand") is None, reason="latexpand is part of TeX Live")


def test_latex_is_flattened_with_tables_bibliography_and_figures(tmp_path):
    ms = tmp_path / "ms"
    tabs = tmp_path / "tabs"
    figs = tmp_path / "figs"
    for folder in (ms, tabs, figs):
        folder.mkdir()
    (tabs / "main.tex").write_text("\\begin{tabular}{c} 0.42 \\end{tabular}\n")
    (figs / "effect.pdf").write_bytes(b"%PDF-1.7")
    (ms / "main.bbl").write_text(
        "\\begin{thebibliography}{1}\\bibitem{a} Author. 2020. Title.\\end{thebibliography}\n"
    )
    (ms / "main.tex").write_text(
        "\\documentclass{article}\\begin{document}\n"
        "The effect is 0.42. % private note\n"
        "\\input{../tabs/main.tex}\n"
        "\\includegraphics[width=\\textwidth]{../figs/effect}\n"
        "\\bibliography{refs}\n\\end{document}\n"
    )
    run_dir = start_run(ms / "main.tex", tmp_path / "reviews", name="quota", root=tmp_path)
    text = (run_dir / "paper.txt").read_text()
    assert "\\begin{tabular}{c} 0.42" in text
    assert "Author. 2020. Title." in text
    assert "private note" not in text
    run = json.loads((run_dir / "run.json").read_text())
    assert run["figures"] == [str((figs / "effect.pdf").resolve())]
    assert run_dir.name == "quota"


@pytest.mark.parametrize("directive", ["input", "include"])
def test_latex_file_outside_root_is_refused(tmp_path, directive):
    secret = tmp_path / "secret.tex"
    secret.write_text("do not share")
    project = tmp_path / "project"
    project.mkdir()
    (project / "main.tex").write_text(
        f"\\documentclass{{article}}\\begin{{document}}\n\\{directive}{{{secret.with_suffix('')}}}\n"
        "\\end{document}\n"
    )
    with pytest.raises(ValueError, match="outside"):
        start_run(project / "main.tex", tmp_path / "reviews", root=project)


def test_root_must_contain_paper_and_not_expose_home(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    (project / "main.tex").write_text("\\documentclass{article}\\begin{document}x\\end{document}\n")
    with pytest.raises(ValueError, match="does not contain"):
        start_run(project / "main.tex", tmp_path / "reviews", root=tmp_path / "elsewhere")
    with pytest.raises(ValueError, match="home"):
        start_run(project / "main.tex", tmp_path / "reviews", root=Path("/"))


def test_figures_outside_root_are_not_listed(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    (tmp_path / "outside.pdf").write_bytes(b"%PDF-1.7")
    (project / "main.tex").write_text(
        "\\documentclass{article}\\begin{document}\n\\includegraphics{../outside}\n\\end{document}\n"
    )
    run_dir = start_run(project / "main.tex", tmp_path / "reviews", root=project)
    assert json.loads((run_dir / "run.json").read_text())["figures"] == []
