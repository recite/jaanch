import json
import shutil

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
    run_dir = start_run(ms / "main.tex", tmp_path / "reviews", name="quota")
    text = (run_dir / "paper.txt").read_text()
    assert "\\begin{tabular}{c} 0.42" in text
    assert "Author. 2020. Title." in text
    assert "private note" not in text
    run = json.loads((run_dir / "run.json").read_text())
    assert run["figures"] == [str((figs / "effect.pdf").resolve())]
    assert run_dir.name == "quota"
