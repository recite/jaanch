import pytest

from jaanch import sources

RECORD = {
    "title": ["Regression Analysis With Linked Data"],
    "author": [{"family": "Lahiri", "given": "P."}, {"family": "Larsen", "given": "Michael D."}],
    "issued": {"date-parts": [[2005, 3]]},
    "container-title": ["Journal of the American Statistical Association"],
    "volume": "100",
    "page": "222-230",
    "type": "journal-article",
}


@pytest.fixture
def bib(tmp_path, monkeypatch):
    path = tmp_path / "sources.bib"
    path.write_text("@article{lahiri2005regression,\n  title = {Other},\n  doi = {10.1/taken}\n}\n")
    monkeypatch.setattr(sources, "crossref", lambda doi: RECORD)
    return path


def test_entry_comes_from_the_record_with_a_fresh_key(bib):
    key = sources.add("10.1198/016214504000001277", "Regression analysis with linked data", bib)
    assert key == "lahiri2005regression2"
    text = bib.read_text()
    assert "author = {Lahiri, P. and Larsen, Michael D.}" in text and "pages = {222--230}" in text


def test_a_doi_that_resolves_to_another_title_is_refused(bib):
    with pytest.raises(ValueError, match="not 'Estimation and Inference'"):
        sources.add("10.1198/016214504000001277", "Estimation and Inference", bib)
    assert "016214504000001277" not in bib.read_text()


def test_a_doi_already_in_the_bib_returns_its_key(bib):
    assert sources.add("10.1/TAKEN", "anything", bib) == "lahiri2005regression"
