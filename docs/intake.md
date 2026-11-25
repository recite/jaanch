# Intake and routing

A submission can be a manuscript alone, a manuscript with its replication
package, or a repository with no manuscript. Which checks can run depends only
on what is there. Whose paper it is does not change the checks.

## Inputs

Every check names the minimum inputs it needs, from this list:

| input | found as |
|---|---|
| `paper_text` | a `.tex` with `\documentclass` (preferred over its PDF), else a `.md/.qmd/.Rmd/.txt` of 1,500+ words, else `.docx`, else a PDF of 5+ pages |
| `tables` | `.tex` files with a tabular environment; `.csv/.tsv` under `tab*/`, `output*/`, `results/`; tables inside the manuscript |
| `figures` | image files under `fig*/`, `plots/`, `img*/`, or cited by `\includegraphics` |
| `bibliography` | `.bib/.bbl`, or a References section in the manuscript |
| `code` | `.R .py .do .jl .m .sas .sps .ipynb .sh`, plus build files (`Makefile`, `master.do`, ...) |
| `data` | `.csv .dta .parquet .rds .sav .xlsx ...` outside table folders, and anything under `data/` |
| `registration` | a pre-registration or analysis-plan document; a registry id cited in the paper is recorded and can be fetched |

`jaanch intake <path>` writes `inventory.json` with what it found, how it
chose the manuscript, other candidates, and notes such as "code without
data: code can be read but not rerun". It reads file names and a little file
content, and never runs the submission's code.

## Routing

A check runs when its inputs are all present and, for a module-specific
check, when the paper model routes the paper to that module. A module is
routed by a design the paper's own analysis uses (`designs`), or by how its
data were made: a data source's `features` (`linked`, `model_predicted`,
`survey_weights`, `interviewer_administered`) or a measure's form and source
(a multi-item scale, an index, a self-report, human coding). Otherwise it is
recorded as untestable, with the input that would unlock it, never silently
skipped.

## Progressive disclosure

Agents load only what their job needs:

| level | what | loaded |
|---|---|---|
| 0 | the router: intake, route, run, verify, report | always |
| 1 | `inventory.json` and the routing result | always, after intake |
| 2 | the procedure for one kind of check | only for kinds the inputs allow |
| 3 | method modules: what a design commits a paper to | only for designs the paper uses |
| 4 | sources and rationale for a check | only when confirming a candidate, or when asked |
