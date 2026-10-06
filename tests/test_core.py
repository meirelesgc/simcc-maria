from datetime import date

import polars as pl

from langchain_core.messages import AIMessage

from simcc_maria.agent import Answer, Usage, _bind_embeddings, unverified_numbers
from simcc_maria.evaluate import has_groups, has_numbers, norm, says_unavailable
from simcc_maria.ingest import build
from simcc_maria.resolve_lattes import cpf_valid, mask_documents


def scholarship(lattes, title="Projeto A", start="2015-08-01", planned_end="2016-07-31",
                modality="undergraduate_research", inst="UFBA", status="found", **extra):
    row = {
        "lattes_id": lattes, "lattes_status": status, "title": title, "abstract": "Resumo do projeto",
        "keyword_1": "dengue", "keyword_2": None, "keyword_3": None, "keyword_4": None,
        "start_date": date.fromisoformat(start), "end_date": date.fromisoformat(planned_end),
        "planned_end_date": date.fromisoformat(planned_end),
        "institution": "Universidade", "institution_zip": None, "unit": None, "unit_zip": None,
        "department": None, "department_zip": None, "institution_acronym": inst,
        "modality": modality, "modality_label": "Iniciação Científica - Cotas",
        "course": None, "major_area": "Ciências da Saúde", "area": "Medicina",
    }
    row.update(extra)
    return row


def frame(*rows) -> pl.DataFrame:
    return pl.DataFrame(list(rows))


# --- holder records: the data identifies bolsistas, not bolsas ---------------

def test_each_holder_is_a_record_no_grant_grouping():
    records = build(frame(
        scholarship("1111111111111111", start="2015-08-01"),
        scholarship("2222222222222222", start="2016-03-01"),  # same project, another holder
    ))
    assert records.height == 2
    assert "grant_id" not in records.columns and "holder_count" not in records.columns


def test_exact_duplicates_collapse_and_are_counted():
    row = scholarship("1111111111111111")
    records = build(frame(row, row, row))
    assert records.height == 1
    assert records["source_rows"][0] == 3


def test_same_person_with_different_details_stays_as_separate_records():
    records = build(frame(
        scholarship("1111111111111111", department="A"),
        scholarship("1111111111111111", department="B"),
    ))
    assert records.height == 2
    assert records["source_rows"].to_list() == [1, 1]


def test_records_without_lattes_are_kept():
    records = build(frame(
        scholarship(None, status="not_found", department="A"),
        scholarship(None, status="not_found", department="B"),
    ))
    assert records.height == 2
    assert records["lattes_id"].null_count() == 2


def test_record_id_is_stable_and_unique():
    rows = frame(scholarship("1111111111111111"), scholarship("2222222222222222"))
    a, b = build(rows), build(rows)
    assert a["record_id"].to_list() == b["record_id"].to_list()
    assert a["record_id"].n_unique() == 2


def test_keywords_are_collected_without_nulls():
    records = build(frame(scholarship("1111111111111111", keyword_2="aedes", keyword_3="dengue")))
    assert records["keywords"].to_list() == [["aedes", "dengue"]]  # sorted


def test_institution_spellings_and_acronym_aliases_are_canonical():
    from simcc_maria.ingest import canonical_institutions
    df = pl.DataFrame({
        "institution_acronym": ["UESB", "UESB", "UESB", "UFSB", "UFSBA"],
        "institution": ["Universidade Estadual do Sudoeste da Bahia"] * 2
                       + ["Universidade Estadual Sudoeste da Bahia", "UFSB nome", "Universidade Federal do Sul da Bahia"],
    })
    out = canonical_institutions(df)
    assert out.filter(institution_acronym="UESB")["institution"].unique().to_list() == [
        "Universidade Estadual do Sudoeste da Bahia"]
    assert out["institution_acronym"].to_list().count("UFSBA") == 2


# --- agent helpers --------------------------------------------------------------

def test_bind_embeddings_keeps_casts():
    sql = "SELECT x::text FROM f(ARRAY['a'], :theme) WHERE y <=> :theme2 > 0"
    out = _bind_embeddings(sql, ["theme", "theme2"])
    assert out == "SELECT x::text FROM f(ARRAY['a'], $1::vector) WHERE y <=> $2::vector > 0"


def test_numbers_are_checked_against_all_steps():
    dfs = [pl.DataFrame({"records": [126]}), pl.DataFrame({"works": [9650], "pct": [53.78]})]
    assert unverified_numbers("Foram 126 registros e 9.650 obras (53,8%).", dfs) == []
    assert unverified_numbers("Foram 127 registros.", dfs) == ["127"]


def test_ranks_and_list_markers_are_not_checked():
    dfs = [pl.DataFrame({"inst": ["UFBA", "UESC"], "people": [2332, 415]})]
    text = "| Posição | Sigla | Bolsistas |\n|---:|---|---:|\n| 1 | UFBA | 2.332 |\n| 2 | UESC | 415 |\n\n1. UFBA lidera"
    assert unverified_numbers(text, dfs) == []
    assert unverified_numbers("| 1 | UFBA | 999 |", dfs) == ["999"]


def test_codes_are_not_numbers():
    assert unverified_numbers("Nível 1A, chamada 18/2024.", [pl.DataFrame({"x": [1]})]) == []


# --- evaluation checks must fail on wrong answers ------------------------------------

def ans(text: str) -> Answer:
    return Answer(question="", text=text)


def test_cost_separates_cached_input_and_adds_embeddings(monkeypatch):
    monkeypatch.setenv("LLM_PRICE_INPUT", "5")
    monkeypatch.setenv("LLM_PRICE_CACHED_INPUT", "0.5")
    monkeypatch.setenv("LLM_PRICE_OUTPUT", "30")
    monkeypatch.setenv("EMBEDDING_PRICE", "0.02")
    from simcc_maria.config import get_settings
    get_settings.cache_clear()
    try:
        u = Usage(tokens_embed=1_000_000)
        u.add(AIMessage("", usage_metadata={"input_tokens": 1_000_000, "output_tokens": 100_000, "total_tokens": 1_100_000,
                                            "input_token_details": {"cache_read": 400_000}}))
        assert u.tokens_cached == 400_000
        assert abs(u.cost_usd - (0.6 * 5 + 0.4 * 0.5 + 0.1 * 30 + 0.02)) < 1e-9
    finally:
        get_settings.cache_clear()


def test_has_numbers():
    assert has_numbers(544)(ans("São 544 bolsas com mais de um bolsista."))[0]
    assert not has_numbers(544)(ans("São 545 bolsas."))[0]
    assert has_numbers(42622)(ans("Total: 42.622 bolsas."))[0]


def test_has_groups_needs_label_and_value_on_the_same_line():
    check = has_groups({("UFBA",): 10, ("UEFS",): 5})
    assert check(ans("| UFBA | 10 |\n| UEFS | 5 |"))[0]
    assert not check(ans("| UFBA | 5 |\n| UEFS | 10 |"))[0]


def test_says_unavailable():
    assert says_unavailable()(ans("A base não contém valores em reais."))[0]
    assert not says_unavailable()(ans("O valor foi R$ 10."))[0]


def test_norm():
    assert norm("  São   Paulo ") == "sao paulo"


# --- document masking (example CPFs, they belong to no one) --------------------

def test_cpf_valid():
    assert cpf_valid("52998224725")
    assert not cpf_valid("52998224724")
    assert not cpf_valid("11111111111")


def test_masks_labeled_formatted_cpf_and_rg():
    assert mask_documents("Rg. 123456789, CPF. 529.982.247-25") == "[RG removido], CPF. [CPF removido]"
    assert mask_documents("CPF 111.222.333-44") == "CPF [CPF removido]"
    assert mask_documents("código 52998224725") == "código [CPF removido]"


def test_masking_keeps_codes_that_are_not_cpf():
    for text in ("PROSPERO: CRD42020123456", "CAAE 12345678.9.0000.5526", "123.456.789-00", "RGB 2020"):
        assert mask_documents(text) == text
