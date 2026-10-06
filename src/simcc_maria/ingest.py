"""Builds the holder records from the raw scholarship sheet.

Input:  data/raw/scholarships.parquet         one row per source record
Output: data/processed/holder_records.parquet one row per distinct record

Each row describes a SCHOLARSHIP HOLDER (bolsista): a person, a project,
a modality, an institution and a period. The sheet does NOT identify grants
(bolsas): it is not possible to tell which records belong to the same grant,
so no grant entity is derived. Count people (distinct lattes_id) or records.

Exact duplicate rows (every column equal) are collapsed into one record;
`source_rows` keeps how many source rows it represents.

Usage: poetry run ingest
"""

import hashlib

import polars as pl

from simcc_maria.config import get_settings

# Column names of the original spreadsheet (pt-BR) -> repository standard
SOURCE_COLUMNS = {
    "Titulo do Projeto": "title",
    "Resumo do Projeto": "abstract",
    "pal_chave1": "keyword_1",
    "pal_chave2": "keyword_2",
    "pal_chave3": "keyword_3",
    "pal_chave4": "keyword_4",
    "Data Inicial": "start_date",
    "Data Final": "end_date",
    "Data Final_1": "planned_end_date",
    "Instituição": "institution",
    "Cep Instituição": "institution_zip",
    "Unidade": "unit",
    "Cep Unidade": "unit_zip",
    "Departamento": "department",
    "Cep Departamento": "department_zip",
    "Sigla Instituição": "institution_acronym",
    "Modalidade": "modality",
    "Nome Curso": "course",
    "Grande Área": "major_area",
    "Área": "area",
    "Subárea": "subarea",
}

MODALITY = {
    "Iniciação Científica - Cotas": "undergraduate_research",
    "Mestrado - Cotas": "masters",
    "Mestrado Profissional - Cotas": "professional_masters",
    "Doutorado - Cotas": "doctorate",
}

# The same institution appears under more than one acronym in the source
ACRONYM_ALIASES = {"UFSB": "UFSBA"}

KEYWORDS = ["keyword_1", "keyword_2", "keyword_3", "keyword_4"]


def _blank_to_null(col: str) -> pl.Expr:
    c = pl.col(col).str.strip_chars()
    return pl.when(c == "").then(None).otherwise(c).alias(col)


def canonical_institutions(df: pl.DataFrame) -> pl.DataFrame:
    """One acronym per institution and one name per acronym (the most frequent
    spelling, e.g. 'Universidade Estadual Sudoeste da Bahia' -> '... do Sudoeste ...')."""
    df = df.with_columns(pl.col("institution_acronym").replace(ACRONYM_ALIASES))
    names = (
        df.group_by("institution_acronym", "institution").len()
        .sort(["institution_acronym", "len", "institution"], descending=[False, True, False])
        .group_by("institution_acronym", maintain_order=True).first()
        .select("institution_acronym", pl.col("institution").alias("canonical"))
    )
    return (
        df.join(names, on="institution_acronym", how="left", nulls_equal=True)
        .with_columns(pl.coalesce("canonical", "institution").alias("institution"))
        .drop("canonical")
    )


def load_scholarships(path=None) -> pl.DataFrame:
    df = pl.read_parquet(path or get_settings().raw_scholarships)
    text_cols = [c for c, t in df.schema.items() if t == pl.String and c not in ("lattes_id", "lattes_status")]
    df = canonical_institutions(df.with_columns(*[_blank_to_null(c) for c in text_cols]))
    return (
        df
        .with_columns(
            pl.col("start_date", "end_date", "planned_end_date").str.to_date("%d/%m/%Y"),
            pl.col("modality").alias("modality_label"),
            pl.col("modality").replace_strict(MODALITY),
        )
        .drop("subarea")  # always empty in the source
    )


def _record_id(row: dict) -> str:
    raw = "\x1f".join("" if v is None else str(v) for v in row.values())
    return hashlib.sha1(raw.encode()).hexdigest()[:16]


def build(df: pl.DataFrame) -> pl.DataFrame:
    """One row per distinct holder record; exact duplicates collapsed into source_rows."""
    df = df.group_by(df.columns, maintain_order=True).len("source_rows")
    return (
        df.with_columns(
            pl.struct(pl.exclude("source_rows")).map_elements(_record_id, return_dtype=pl.String).alias("record_id"),
            # sorted: the embedded text (and its cache key) does not depend on column order
            pl.concat_list(KEYWORDS).list.drop_nulls().list.unique().list.sort().alias("keywords"),
        )
        .select(
            "record_id", "lattes_id", "lattes_status", "title", "abstract", "keywords",
            "modality", "modality_label", "institution_acronym", "institution", "unit", "department",
            "course", "major_area", "area", "start_date", "end_date", "planned_end_date", "source_rows",
        )
        .sort("start_date", "record_id")
    )


def read_records() -> pl.DataFrame:
    return pl.read_parquet(get_settings().processed_dir / "holder_records.parquet")


def main() -> None:
    settings = get_settings()
    records = build(load_scholarships())
    settings.processed_dir.mkdir(parents=True, exist_ok=True)
    for old in ("grants.parquet", "grant_holders.parquet"):  # previous (grant-based) model
        (settings.processed_dir / old).unlink(missing_ok=True)
    records.write_parquet(settings.processed_dir / "holder_records.parquet")
    people = records["lattes_id"].drop_nulls().n_unique() + records["lattes_id"].null_count()
    print(f"{records.height} holder records · {people} people · {records['source_rows'].sum()} source rows")


if __name__ == "__main__":
    main()
