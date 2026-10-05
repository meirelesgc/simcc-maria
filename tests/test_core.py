import polars as pl

from simcc_maria.evaluate import groups, names, norm, scalar
from simcc_maria.ingest import UF_SIGLA, read_processed
from simcc_maria.pipeline import Answer, Plano, unverified_numbers


def answer(df: pl.DataFrame, tipo="agregacao") -> Answer:
    return Answer(question="", plano=Plano(tipo=tipo, sql="select 1", premissas="", ressalvas=[]), df=df)


# --- CSV processado -----------------------------------------------------------

def test_csv_preserva_id_lattes_e_tipos():
    df = read_processed()
    assert df.height == 17945
    assert df["id_lattes"].str.len_chars().unique().to_list() == [16]
    assert df["id_lattes"].str.starts_with("0").any()  # zeros à esquerda preservados
    assert df["data_inicio"].dtype == pl.Date
    assert df["uf"].n_unique() == len(UF_SIGLA)
    assert df["categoria_nivel"].null_count() == 1  # o "NA" da origem virou nulo


# --- conferência de números do resumo ----------------------------------------

def test_numeros_conferidos_aceitam_formato_br_e_arredondamento():
    df = pl.DataFrame({"regiao": ["Sudeste"], "bolsas": [9650], "pct": [53.78]})
    assert unverified_numbers("O Sudeste tem 9.650 bolsas (53,8%, cerca de 54%).", df) == []


def test_numeros_inventados_sao_sinalizados():
    df = pl.DataFrame({"bolsas": [9650]})
    assert unverified_numbers("São 9.650 bolsas, 12% a mais que em 2023.", df) == ["12", "2023"]


def test_codigos_nao_sao_tratados_como_numeros():
    assert unverified_numbers("Nível 1A na chamada 18/2024.", pl.DataFrame({"x": [1]})) == []


# --- verificadores da avaliação: precisam reprovar respostas erradas ---------

def test_scalar():
    assert scalar(636)(answer(pl.DataFrame({"n": [636]})))[0]
    assert not scalar(636)(answer(pl.DataFrame({"n": [635]})))[0]


def test_groups_exige_rotulo_e_valor_na_mesma_linha():
    check = groups({("Sudeste",): 10, ("Sul",): 5})
    assert check(answer(pl.DataFrame({"r": ["Sudeste", "Sul"], "n": [10, 5]})))[0]
    assert not check(answer(pl.DataFrame({"r": ["Sudeste", "Sul"], "n": [5, 10]})))[0]


def test_groups_sigla_curta_nao_casa_por_substring():
    check = groups({("PQ",): 3})
    assert not check(answer(pl.DataFrame({"m": ["PQ-Sr"], "n": [3]})))[0]


def test_names_reprova_nome_a_mais():
    check = names({"Helio Chacham"})
    assert check(answer(pl.DataFrame({"nome": ["Hélio Chacham"]}), "listagem"))[0]
    assert not check(answer(pl.DataFrame({"nome": ["Helio Chacham", "Outro"]}), "listagem"))[0]


def test_norm():
    assert norm("  São   Paulo ") == "sao paulo"


# --- máscara de documentos (CPFs de exemplo, não pertencem a ninguém) --------

from simcc_maria.resolve_lattes import cpf_valid, mask_documents  # noqa: E402


def test_cpf_valid():
    assert cpf_valid("52998224725")
    assert not cpf_valid("52998224724")
    assert not cpf_valid("11111111111")


def test_mascara_cpf_rotulado_formatado_e_rg():
    assert mask_documents("Rg. 123456789, CPF. 529.982.247-25") == "[RG removido], CPF. [CPF removido]"
    assert mask_documents("CPF 111.222.333-44") == "CPF [CPF removido]"  # rotulado: mesmo inválido
    assert mask_documents("código 52998224725") == "código [CPF removido]"  # sem rótulo, DV válido


def test_mascara_preserva_codigos_que_nao_sao_cpf():
    for text in ("PROSPERO: CRD42020123456", "CAAE 12345678.9.0000.5526", "123.456.789-00", "RGB 2020"):
        assert mask_documents(text) == text
