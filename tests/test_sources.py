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


PAGE = {
    "title": "[74] In Press at Psychological Science: A New Nudge Supported by Implausible Data",
    "site": "Data Colada",
    "year": 2018,
}


def test_a_page_with_no_doi_is_added_from_its_own_title(bib, monkeypatch):
    monkeypatch.setattr(sources, "page_record", lambda url: PAGE)
    key = sources.add_url(
        "https://datacolada.org/74", "A New Nudge Supported by Implausible Data", "Data Colada", bib
    )
    assert key == "datacolada74"
    assert "author = {Data Colada}" in bib.read_text() and "year = {2018}" in bib.read_text()
    assert sources.add_url("https://datacolada.org/74", "anything", "x", bib) == "datacolada74"


def test_a_page_whose_title_differs_is_refused(bib, monkeypatch):
    monkeypatch.setattr(sources, "page_record", lambda url: PAGE)
    with pytest.raises(ValueError, match="not 'Small Telescopes'"):
        sources.add_url("https://datacolada.org/74", "Small Telescopes", "Data Colada", bib)


def test_page_fields_cannot_close_the_entry_or_start_another(bib, monkeypatch):
    hostile = dict(PAGE, title=PAGE["title"] + "},\n}\n@misc{evil, note = {pwned", site="Data}@Colada\\x")
    monkeypatch.setattr(sources, "page_record", lambda url: hostile)
    sources.add_url(
        "https://datacolada.org/74", "A New Nudge Supported by Implausible Data", "Data Colada", bib
    )
    text = bib.read_text()
    assert "@misc{evil" not in text and text.count("@") == 2
    assert "howpublished = {DataColadax}" in text


def test_crossref_fields_are_cleaned_too(bib, monkeypatch):
    monkeypatch.setattr(
        sources, "crossref", lambda doi: dict(RECORD, title=["Regression Analysis With Linked Data}@x"])
    )
    sources.add("10.1198/016214504000001277", "Regression analysis with linked data", bib)
    assert bib.read_text().count("@") == 2
