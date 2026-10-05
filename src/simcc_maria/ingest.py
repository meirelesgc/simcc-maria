"""Converte a planilha bruta do CNPq (data/raw) em um CSV limpo (data/processed).

Uso: poetry run ingest [entrada.xlsx] [saida.csv]
"""

import sys
import warnings
from pathlib import Path

import polars as pl

from simcc_maria.config import get_settings

COLUMNS = {
    "# Id Lattes": "id_lattes",
    "# Nome Beneficiário": "nome_beneficiario",
    "# Nome País": "pais",
    "# Nome Região": "regiao",
    "# Nome UF": "uf_nome",
    "# Nome Cidade": "cidade",
    "# Linha Fomento": "linha_fomento",
    "# Nome Grande Área": "grande_area",
    "# Nome Área": "area",
    "# Nome Sub-área": "subarea",
    "# Cod Modalidade": "modalidade_cod",
    "# Nome Modalidade": "modalidade",
    "# Título Chamada": "chamada",
    "# Cod Categoria Nível": "categoria_nivel",
    "# Nome Programa Fomento": "programa_fomento",
    "# Nome Instituto": "instituicao",
    "# Data Início Processo": "data_inicio",
    "# Data Término Processo": "data_termino",
    "# Data Extração BD PICC": "data_extracao",
    "QUANTAUXILIO": "qtd_auxilio",
    "QUANTBOLSA": "qtd_bolsa",
}

# A planilha traz o nome do estado sem acento; a sigla facilita filtros e joins.
UF_SIGLA = {
    "Acre": "AC", "Alagoas": "AL", "Amapa": "AP", "Amazonas": "AM",
    "Bahia": "BA", "Ceara": "CE", "Distrito Federal": "DF",
    "Espirito Santo": "ES", "Goias": "GO", "Maranhao": "MA",
    "Mato Grosso": "MT", "Mato Grosso do Sul": "MS", "Minas Gerais": "MG",
    "Para": "PA", "Paraiba": "PB", "Parana": "PR", "Pernambuco": "PE",
    "Piaui": "PI", "Rio Grande do Norte": "RN", "Rio Grande do Sul": "RS",
    "Rio de Janeiro": "RJ", "Rondonia": "RO", "Roraima": "RR",
    "Santa Catarina": "SC", "Sao Paulo": "SP", "Sergipe": "SE",
    "Tocantins": "TO",
}

# Ordem final das colunas no CSV: a sigla `uf` entra antes de `uf_nome`
ORDER = list(COLUMNS.values())
ORDER.insert(ORDER.index("uf_nome"), "uf")

TYPES = {
    "data_inicio": pl.Date,
    "data_termino": pl.Date,
    "data_extracao": pl.Date,
    "qtd_auxilio": pl.Int32,
    "qtd_bolsa": pl.Int32,
}
SCHEMA = {c: TYPES.get(c, pl.String) for c in ORDER}


def load_raw(path: Path) -> pl.DataFrame:
    # infer_schema_length=0 lê tudo como texto: preserva os zeros do Id Lattes
    with warnings.catch_warnings():
        # aviso interno do polars ao ler via fastexcel; não afeta o resultado
        warnings.filterwarnings("ignore", message="from_arrow", category=FutureWarning)
        df = pl.read_excel(path, infer_schema_length=0)
    df = df.rename(COLUMNS).select(COLUMNS.values())

    # A origem marca o único nível ausente com o texto literal "NA"
    df = df.with_columns(pl.all().str.strip_chars().replace("NA", None)).with_columns(
        pl.col("data_inicio", "data_termino", "data_extracao").str.to_date("%d/%m/%Y"),
        pl.col("qtd_auxilio", "qtd_bolsa").cast(pl.Int32),
        pl.col("uf_nome").replace_strict(UF_SIGLA, default=None).alias("uf"),
    )

    missing = df.filter(pl.col("uf").is_null())["uf_nome"].unique().to_list()
    if missing:
        raise ValueError(f"UF sem sigla mapeada: {missing}")

    return df.select(ORDER)


def read_processed(path: Path | None = None) -> pl.DataFrame:
    return pl.read_csv(path or get_settings().processed_csv, schema=SCHEMA)


def main() -> None:
    settings = get_settings()
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else settings.raw_xlsx
    dst = Path(sys.argv[2]) if len(sys.argv) > 2 else settings.processed_csv
    df = load_raw(src)
    dst.parent.mkdir(parents=True, exist_ok=True)
    df.write_csv(dst)
    print(f"{df.height} linhas -> {dst}")


if __name__ == "__main__":
    main()
