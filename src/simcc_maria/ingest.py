"""Builds the grant model from the raw scholarship sheet.

Input:  data/raw/scholarships.parquet   (one row per scholarship record, holder = lattes_id)
Output: data/processed/grants.parquet         one row per grant
        data/processed/grant_holders.parquet  one row per (grant, holder)

A grant ("bolsa") can have MORE THAN ONE holder ("bolsista"): another student
in the same project and cycle (likely a replacement; the source does not say). The sheet has no grant id, so a
grant is identified by:

    normalized title + normalized abstract + modality + institution acronym
    + planned end date (the funding cycle)

Exact duplicate rows (same holder and every other field) are collapsed and
counted in `grant_holders.source_rows`.

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

GRANT_KEY = ["title_norm", "abstract_norm", "modality", "institution_acronym", "planned_end_date"]
KEYWORDS = ["keyword_1", "keyword_2", "keyword_3", "keyword_4"]


def _norm(col: str) -> pl.Expr:
    return pl.col(col).fill_null("").str.to_lowercase().str.replace_all(r"\s+", " ").str.strip_chars()


def _blank_to_null(col: str) -> pl.Expr:
    c = pl.col(col).str.strip_chars()
    return pl.when(c == "").then(None).otherwise(c).alias(col)


def _grant_id(key: dict) -> str:
    raw = "\x1f".join(str(key[k]) for k in GRANT_KEY)
    return hashlib.sha1(raw.encode()).hexdigest()[:16]


def _mode(col: str) -> pl.Expr:
    """Most frequent non-null value; ties broken alphabetically (deterministic)."""
    return pl.col(col).drop_nulls().mode().sort().first().alias(col)


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
            _norm("title").alias("title_norm"),
            _norm("abstract").alias("abstract_norm"),
        )
        .drop("subarea")  # always empty in the source
    )


def build(df: pl.DataFrame) -> tuple[pl.DataFrame, pl.DataFrame]:
    # Collapse exact duplicates, remembering how many source rows each one had
    df = df.group_by(df.columns, maintain_order=True).len("source_rows")

    keys = df.select(GRANT_KEY).unique().with_columns(
        pl.struct(GRANT_KEY).map_elements(_grant_id, return_dtype=pl.String).alias("grant_id")
    )
    df = df.join(keys, on=GRANT_KEY, nulls_equal=True)

    # Holder identity: lattes_id when known; otherwise every distinct record is its own holder
    df = df.with_columns(
        pl.when(pl.col("lattes_id").is_not_null())
        .then(pl.lit("lattes:") + pl.col("lattes_id"))
        .otherwise(pl.lit("record:") + pl.int_range(pl.len()).cast(pl.String))
        .alias("holder_key")
    )

    holders = (
        df.group_by("grant_id", "holder_key")
        .agg(
            pl.col("lattes_id").first(),
            pl.col("lattes_status").first(),
            pl.col("start_date").min(),
            pl.col("end_date").max(),
            _mode("unit"),
            _mode("department"),
            _mode("course"),
            pl.col("source_rows").sum(),
        )
        .sort("grant_id", "start_date", "holder_key")
        .with_columns(pl.int_range(1, pl.len() + 1).over("grant_id").cast(pl.Int16).alias("holder_seq"))
        .drop("holder_key")
    )

    grants = (
        df.group_by("grant_id")
        .agg(
            pl.col("title").first(),
            pl.col("abstract").first(),
            pl.concat_list(KEYWORDS).list.explode(keep_nulls=False, empty_as_null=False).drop_nulls().unique().sort().alias("keywords"),
            pl.col("modality").first(),
            pl.col("modality_label").first(),
            pl.col("institution_acronym").first(),
            _mode("institution"),
            _mode("major_area"),
            _mode("area"),
            pl.col("start_date").min(),
            pl.col("end_date").max(),
            pl.col("planned_end_date").first(),
        )
        .join(holders.group_by("grant_id").agg(pl.len().cast(pl.Int16).alias("holder_count")), on="grant_id")
        .sort("start_date", "grant_id")
    )
    return grants, holders


def read_grants() -> tuple[pl.DataFrame, pl.DataFrame]:
    d = get_settings().processed_dir
    return pl.read_parquet(d / "grants.parquet"), pl.read_parquet(d / "grant_holders.parquet")


def main() -> None:
    settings = get_settings()
    grants, holders = build(load_scholarships())
    settings.processed_dir.mkdir(parents=True, exist_ok=True)
    grants.write_parquet(settings.processed_dir / "grants.parquet")
    holders.write_parquet(settings.processed_dir / "grant_holders.parquet")
    multi = grants.filter(pl.col("holder_count") > 1).height
    print(f"{grants.height} grants ({multi} with more than one holder) · {holders.height} grant holders")


if __name__ == "__main__":
    main()
