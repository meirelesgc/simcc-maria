from datetime import date

import polars as pl

from simcc_maria.agent import Answer, _bind_embeddings, unverified_numbers
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
        "title_norm": title.lower(), "abstract_norm": "resumo do projeto",
    }
    row.update(extra)
    return row


def frame(*rows) -> pl.DataFrame:
    return pl.DataFrame(list(rows))


# --- grant model: a grant can have more than one holder ----------------------

def test_replacement_within_cycle_is_one_grant_with_two_holders():
    grants, holders = build(frame(
        scholarship("1111111111111111", start="2015-08-01"),
        scholarship("2222222222222222", start="2016-03-01"),  # replaced student, same cycle
    ))
    assert grants.height == 1
    assert grants["holder_count"][0] == 2
    assert holders.height == 2
    assert grants["start_date"][0] == date(2015, 8, 1)


def test_new_cycle_is_a_new_grant():
    grants, _ = build(frame(
        scholarship("1111111111111111", planned_end="2016-07-31"),
        scholarship("1111111111111111", start="2016-08-01", planned_end="2017-07-31"),
    ))
    assert grants.height == 2
    assert grants["holder_count"].to_list() == [1, 1]


def test_exact_duplicates_collapse_and_are_counted():
    row = scholarship("1111111111111111")
    grants, holders = build(frame(row, row, row))
    assert grants.height == 1 and holders.height == 1
    assert holders["source_rows"][0] == 3


def test_holders_without_lattes_are_counted_individually():
    grants, holders = build(frame(
        scholarship(None, status="not_found", department="A"),
        scholarship(None, status="not_found", department="B"),
    ))
    assert grants["holder_count"][0] == 2
    assert holders["lattes_id"].null_count() == 2


def test_different_modality_or_institution_are_different_grants():
    grants, _ = build(frame(
        scholarship("1111111111111111"),
        scholarship("2222222222222222", modality="masters"),
        scholarship("3333333333333333", inst="UEFS"),
    ))
    assert grants.height == 3


def test_grant_id_is_stable():
    a, _ = build(frame(scholarship("1111111111111111")))
    b, _ = build(frame(scholarship("2222222222222222")))
    assert a["grant_id"][0] == b["grant_id"][0]  # same project/cycle → same grant


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
    dfs = [pl.DataFrame({"grants": [126]}), pl.DataFrame({"works": [9650], "pct": [53.78]})]
    assert unverified_numbers("Foram 126 bolsas e 9.650 obras (53,8%).", dfs) == []
    assert unverified_numbers("Foram 127 bolsas.", dfs) == ["127"]


def test_ranks_and_list_markers_are_not_checked():
    dfs = [pl.DataFrame({"inst": ["UFBA", "UESC"], "grants": [2332, 415]})]
    text = "| Posição | Sigla | Bolsas |\n|---:|---|---:|\n| 1 | UFBA | 2.332 |\n| 2 | UESC | 415 |\n\n1. UFBA lidera"
    assert unverified_numbers(text, dfs) == []
    assert unverified_numbers("| 1 | UFBA | 999 |", dfs) == ["999"]


def test_codes_are_not_numbers():
    assert unverified_numbers("Nível 1A, chamada 18/2024.", [pl.DataFrame({"x": [1]})]) == []


# --- evaluation checks must fail on wrong answers ------------------------------------

def ans(text: str) -> Answer:
    return Answer(question="", text=text)


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
