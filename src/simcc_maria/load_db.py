"""Builds the `maria` schema: grants, holders, embeddings, advisor links,
productions and the hybrid search functions.

Usage:
    poetry run load-db                        # everything
    poetry run load-db --from links           # recompute advisor links (e.g. after changing cutoffs)
    poetry run load-db --from links --resume  # continue an interrupted links stage
    poetry run load-db --from finalize        # recreate views/functions (e.g. after changing theme cutoffs)

Only the `maria` schema is written; SIMCC tables in `public` are read-only.
Embeddings are cached in maria.embedding_cache, so re-running is cheap.
"""

import argparse
import asyncio
import time

import asyncpg
import polars as pl

from simcc_maria.config import get_settings
from simcc_maria.embeddings import CACHE_DDL, Embedder
from simcc_maria.ingest import read_grants

DROP = """
DROP TABLE IF EXISTS maria.bolsas CASCADE;
DROP FUNCTION IF EXISTS maria.grant_outcomes CASCADE;
DROP FUNCTION IF EXISTS maria.search_grants CASCADE;
DROP FUNCTION IF EXISTS maria.search_productions CASCADE;
DROP VIEW IF EXISTS maria.grant_researchers CASCADE;
DROP MATERIALIZED VIEW IF EXISTS maria.productions CASCADE;
DROP TABLE IF EXISTS maria.grant_advisor_links CASCADE;
DROP TABLE IF EXISTS maria.grant_link_progress CASCADE;
DROP TABLE IF EXISTS maria.guidance_title_vectors CASCADE;
DROP TABLE IF EXISTS maria.guidance_titles CASCADE;
DROP TABLE IF EXISTS maria.grant_holders CASCADE;
DROP TABLE IF EXISTS maria.grants CASCADE;
"""

BASE_DDL = """
-- Accent/case/punctuation-insensitive text, used for lexical matching
CREATE OR REPLACE FUNCTION maria.norm(t text) RETURNS text
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
  SELECT trim(regexp_replace(lower(public.unaccent(coalesce(t, ''))), '[^a-z0-9]+', ' ', 'g'))
$$;

CREATE TABLE maria.grants (
  grant_id            text PRIMARY KEY,
  title               text,
  abstract            text,
  keywords            text[],
  modality            text NOT NULL,
  modality_label      text NOT NULL,
  institution_acronym text,
  institution         text,
  major_area          text,
  area                text,
  start_date          date,
  end_date            date,
  planned_end_date    date,
  holder_count        smallint NOT NULL,
  title_norm          text,
  search_text         text,
  title_key           text,
  content_key         text
);

CREATE TABLE maria.grant_holders (
  grant_id      text NOT NULL REFERENCES maria.grants,
  holder_seq    smallint NOT NULL,
  lattes_id     varchar(16),
  lattes_status text NOT NULL,
  start_date    date,
  end_date      date,
  unit          text,
  department    text,
  course        text,
  source_rows   integer NOT NULL,
  PRIMARY KEY (grant_id, holder_seq)
);
"""

COMMENTS = {
    "maria.grants": "One row per grant (bolsa). A grant can have more than one holder: see holder_count and maria.grant_holders.",
    "maria.grants.grant_id": "Derived id: hash of normalized title + abstract + modality + institution_acronym + planned_end_date.",
    "maria.grants.modality": "undergraduate_research | masters | professional_masters | doctorate.",
    "maria.grants.modality_label": "Original label, e.g. 'Iniciação Científica - Cotas'.",
    "maria.grants.start_date": "Earliest start among the grant holders.",
    "maria.grants.end_date": "Latest actual end among the grant holders.",
    "maria.grants.planned_end_date": "Planned end of the funding cycle.",
    "maria.grants.holder_count": "Number of holders (bolsistas) of this grant. Usually 1; 544 grants have 2 or 3.",
    "maria.grant_holders": "One row per (grant, holder). Holder = student who received the scholarship.",
    "maria.grant_holders.lattes_id": "Lattes id of the holder; NULL when lattes_status <> 'found'.",
    "maria.grant_holders.lattes_status": "found | not_found | foreign_document.",
    "maria.grant_holders.source_rows": "Identical rows collapsed from the source sheet.",
}

GUIDANCE_DDL = """
-- Supervisions (orientações) from SIMCC whose nature matches a grant modality
CREATE TABLE maria.guidance_titles AS
SELECT g.id AS guidance_id,
       g.researcher_id,
       g.title,
       maria.norm(g.title) AS title_norm,
       g.nature,
       g.year,
       CASE
         WHEN maria.norm(g.nature) LIKE 'iniciacao cientifica%' THEN 'undergraduate_research'
         WHEN maria.norm(g.nature) LIKE 'dissertacao%' THEN 'masters'
         WHEN maria.norm(g.nature) LIKE 'tese%' THEN 'doctorate'
       END AS modality_group,
       NULL::text AS title_key
FROM public.guidance g
WHERE length(trim(g.title)) >= 10 AND g.year >= 2003;
DELETE FROM maria.guidance_titles WHERE modality_group IS NULL;
ALTER TABLE maria.guidance_titles ADD PRIMARY KEY (guidance_id);
"""

# Docker's default /dev/shm (64 MB) is too small for parallel index builds and
# parallel scans over vectors: heavy sessions run without parallel workers.
HEAVY_SESSION_SQL = """
SET max_parallel_maintenance_workers = 0;
SET max_parallel_workers_per_gather = 0;
SET maintenance_work_mem = '2GB';  -- the HNSW graph (~1 GB) is built in memory
SET hnsw.ef_search = 100;
"""

VECTORS_SQL = """
DROP TABLE IF EXISTS maria.guidance_title_vectors CASCADE;
CREATE TABLE maria.guidance_title_vectors AS
SELECT DISTINCT t.title_key, c.embedding
FROM maria.guidance_titles t JOIN maria.embedding_cache c ON c.key = t.title_key;
ALTER TABLE maria.guidance_title_vectors ADD PRIMARY KEY (title_key);
CREATE INDEX ON maria.guidance_title_vectors USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS guidance_titles_title_norm_idx ON maria.guidance_titles (title_norm);
CREATE INDEX IF NOT EXISTS guidance_titles_title_key_idx ON maria.guidance_titles (title_key);
"""

LINKS_TABLE_SQL = """
DROP TABLE IF EXISTS maria.grant_advisor_links CASCADE;
DROP TABLE IF EXISTS maria.grant_link_progress;
CREATE TABLE maria.grant_advisor_links (
  grant_id              text NOT NULL,
  guidance_id           uuid NOT NULL,
  advisor_researcher_id uuid NOT NULL,
  advisor_lattes_id     varchar,
  advisor_name          varchar,
  guidance_title        varchar,
  guidance_nature       varchar,
  guidance_year         int,
  lexical_score         float8 NOT NULL,
  semantic_score        float8 NOT NULL,
  link_method           text NOT NULL,
  link_score            float8 NOT NULL,
  PRIMARY KEY (grant_id, guidance_id)
);
-- grants already processed, so an interrupted run can resume (--resume)
CREATE TABLE maria.grant_link_progress (grant_id text PRIMARY KEY);
"""

# Candidates: identical normalized title, plus the {k} nearest titles in the
# HNSW index. A trigram index search per grant (~150 ms each) would take hours;
# titles with trigram similarity >= the lexical cutoff are near-identical and
# land among the nearest neighbours. BOTH scores are then computed for every
# candidate and each method applies its own cutoff.
LINKS_CHUNK_SQL = """
INSERT INTO maria.grant_advisor_links
WITH g AS (
  SELECT gr.grant_id, gr.title_norm, c.embedding AS title_vec,
         CASE gr.modality WHEN 'professional_masters' THEN 'masters' ELSE gr.modality END AS grp,
         extract(year FROM gr.start_date)::int - {before} AS y0,
         extract(year FROM coalesce(gr.planned_end_date, gr.end_date))::int + {after} AS y1
  FROM maria.grants gr JOIN maria.embedding_cache c ON c.key = gr.title_key
  WHERE gr.grant_id = ANY($1::text[]) AND length(gr.title_norm) >= 10
),
exact AS (
  SELECT g.grant_id, t.guidance_id
  FROM g JOIN maria.guidance_titles t
    ON t.title_norm = g.title_norm AND t.modality_group = g.grp AND t.year BETWEEN g.y0 AND g.y1
),
nearest AS (
  SELECT g.grant_id, t.guidance_id
  FROM g
  CROSS JOIN LATERAL (
    SELECT v.title_key FROM maria.guidance_title_vectors v
    ORDER BY v.embedding <=> g.title_vec LIMIT {k}
  ) nn
  JOIN maria.guidance_titles t
    ON t.title_key = nn.title_key AND t.modality_group = g.grp AND t.year BETWEEN g.y0 AND g.y1
),
candidates AS (SELECT * FROM exact UNION SELECT * FROM nearest),
scored AS (
  SELECT c.grant_id, t.guidance_id, t.researcher_id AS advisor_researcher_id,
         r.lattes_id AS advisor_lattes_id, r.name AS advisor_name,
         t.title AS guidance_title, t.nature AS guidance_nature, t.year AS guidance_year,
         similarity(t.title_norm, g.title_norm)::float8 AS lexical_score,
         (1 - (e.embedding <=> g.title_vec))::float8 AS semantic_score
  FROM candidates c
  JOIN g USING (grant_id)
  JOIN maria.guidance_titles t USING (guidance_id)
  JOIN maria.embedding_cache e ON e.key = t.title_key
  JOIN public.researcher r ON r.id = t.researcher_id
)
SELECT *,
       CASE WHEN lexical_score >= {lex_min} AND semantic_score >= {sem_min} THEN 'both'
            WHEN lexical_score >= {lex_min} THEN 'lexical'
            ELSE 'semantic' END AS link_method,
       {lex_w} * lexical_score + {sem_w} * semantic_score AS link_score
FROM scored
WHERE lexical_score >= {lex_min} OR semantic_score >= {sem_min};
"""

LINKS_CHUNK = 1000

RESEARCHERS_VIEW_SQL = """
-- Researchers in SIMCC connected to a grant: the holder (same lattes_id) or the
-- advisor (supervision whose title matches the grant title)
CREATE VIEW maria.grant_researchers AS
SELECT h.grant_id, r.id AS researcher_id, r.lattes_id, r.name AS researcher_name,
       'holder'::text AS role, 'lattes_id'::text AS link_method, 1.0::float8 AS link_score
FROM maria.grant_holders h JOIN public.researcher r ON r.lattes_id = h.lattes_id
UNION ALL
SELECT * FROM (
  -- one row per (grant, advisor): the strongest of its supervision matches
  SELECT DISTINCT ON (grant_id, advisor_researcher_id)
         grant_id, advisor_researcher_id, advisor_lattes_id, advisor_name,
         'advisor'::text, link_method, link_score
  FROM maria.grant_advisor_links
  ORDER BY grant_id, advisor_researcher_id, link_score DESC
) advisors;
"""

PRODUCTIONS_SQL = """
-- Articles, books and chapters. The same work appears once per co-author in
-- SIMCC: use work_key to count distinct works.
CREATE MATERIALIZED VIEW maria.productions AS
SELECT b.id AS production_id, b.researcher_id, r.lattes_id, r.name AS researcher_name,
       b.type AS production_type, b.title, b.year_ AS year,
       nullif(lower(trim(b.doi)), '') AS doi,
       maria.norm(b.title) AS title_norm,
       coalesce('doi:' || nullif(lower(trim(b.doi)), ''),
                'title:' || md5(maria.norm(b.title)) || ':' || coalesce(b.year_::text, '')) AS work_key
FROM public.bibliographic_production b
JOIN public.researcher r ON r.id = b.researcher_id
WHERE b.type IN ('ARTICLE', 'BOOK', 'BOOK_CHAPTER');
CREATE UNIQUE INDEX ON maria.productions (production_id);
CREATE INDEX ON maria.productions (researcher_id, year);
"""

FUNCTIONS_SQL = """
CREATE FUNCTION maria.search_grants(
  p_terms text[], p_vec vector,
  p_lexical_min float8 DEFAULT {lex_min}, p_semantic_min float8 DEFAULT {sem_min},
  p_lexical_weight float8 DEFAULT {lex_w}, p_semantic_weight float8 DEFAULT {sem_w})
RETURNS TABLE (grant_id text, lexical float8, semantic float8, match_method text, match_score float8)
LANGUAGE sql STABLE AS $$
  WITH s AS (
    SELECT g.grant_id,
           CASE WHEN EXISTS (
             SELECT 1 FROM unnest(p_terms) t
             WHERE maria.norm(t) <> '' AND ' ' || g.search_text || ' ' LIKE '% ' || maria.norm(t) || '%'
           ) THEN 1.0 ELSE 0.0 END::float8 AS lexical,
           coalesce(1 - (c.embedding <=> p_vec), 0)::float8 AS semantic
    FROM maria.grants g LEFT JOIN maria.embedding_cache c ON c.key = g.content_key
  )
  SELECT grant_id, lexical, semantic,
         CASE WHEN lexical >= p_lexical_min AND semantic >= p_semantic_min THEN 'both'
              WHEN lexical >= p_lexical_min THEN 'lexical' ELSE 'semantic' END,
         p_lexical_weight * lexical + p_semantic_weight * semantic
  FROM s WHERE lexical >= p_lexical_min OR semantic >= p_semantic_min
$$;

CREATE FUNCTION maria.search_productions(
  p_terms text[], p_vec vector,
  p_lexical_min float8 DEFAULT {lex_min}, p_semantic_min float8 DEFAULT {sem_min},
  p_lexical_weight float8 DEFAULT {lex_w}, p_semantic_weight float8 DEFAULT {sem_w})
RETURNS TABLE (production_id uuid, lexical float8, semantic float8, match_method text, match_score float8)
LANGUAGE sql STABLE AS $$
  WITH s AS (
    SELECT p.production_id,
           CASE WHEN EXISTS (
             SELECT 1 FROM unnest(p_terms) t
             WHERE maria.norm(t) <> '' AND ' ' || p.title_norm || ' ' LIKE '% ' || maria.norm(t) || '%'
           ) THEN 1.0 ELSE 0.0 END::float8 AS lexical,
           coalesce(1 - (d.embedding <=> p_vec), 0)::float8 AS semantic
    FROM maria.productions p
    LEFT JOIN public.search_document_production d ON d.production_id = p.production_id
  )
  SELECT production_id, lexical, semantic,
         CASE WHEN lexical >= p_lexical_min AND semantic >= p_semantic_min THEN 'both'
              WHEN lexical >= p_lexical_min THEN 'lexical' ELSE 'semantic' END,
         p_lexical_weight * lexical + p_semantic_weight * semantic
  FROM s WHERE lexical >= p_lexical_min OR semantic >= p_semantic_min
$$;

-- One row per (grant, researcher, production): theme-matching productions of
-- researchers linked to theme-matching grants, published from the grant start
-- to `p_years_after` years after its end. A production may repeat across grants
-- and researchers: count with count(DISTINCT work_key).
-- Only the candidate productions (of linked researchers, inside the window) are
-- scored, with the same rule as maria.search_productions.
CREATE FUNCTION maria.grant_outcomes(p_terms text[], p_vec vector, p_years_after int DEFAULT {years_after})
RETURNS TABLE (
  grant_id text, grant_title text, modality text, institution_acronym text,
  grant_start date, grant_end date, holder_count smallint,
  grant_match text, grant_score float8,
  researcher_id uuid, lattes_id varchar, researcher_name varchar, role text,
  link_method text, link_score float8,
  production_id uuid, work_key text, production_type varchar, production_title varchar,
  production_year int, doi text, production_match text, production_score float8)
LANGUAGE sql STABLE AS $$
  WITH g AS MATERIALIZED (SELECT * FROM maria.search_grants(p_terms, p_vec)),
  -- MATERIALIZED stops the planner from scoring all productions before the join
  candidates AS MATERIALIZED (
    SELECT gr.grant_id, gr.title AS grant_title, gr.modality, gr.institution_acronym,
           gr.start_date, gr.end_date, gr.holder_count, g.match_method AS grant_match,
           g.match_score AS grant_score,
           r.researcher_id, r.lattes_id, r.researcher_name, r.role, r.link_method, r.link_score,
           pr.production_id, pr.work_key, pr.production_type, pr.title AS production_title,
           pr.year AS production_year, pr.doi, pr.title_norm
    FROM g
    JOIN maria.grants gr ON gr.grant_id = g.grant_id
    JOIN maria.grant_researchers r ON r.grant_id = gr.grant_id
    JOIN maria.productions pr ON pr.researcher_id = r.researcher_id
     AND pr.year BETWEEN extract(year FROM gr.start_date) AND extract(year FROM gr.end_date) + p_years_after
  ),
  scored AS (
    SELECT c.*,
           CASE WHEN EXISTS (
             SELECT 1 FROM unnest(p_terms) t
             WHERE maria.norm(t) <> '' AND ' ' || c.title_norm || ' ' LIKE '% ' || maria.norm(t) || '%'
           ) THEN 1.0 ELSE 0.0 END::float8 AS lexical,
           coalesce((SELECT 1 - (d.embedding <=> p_vec) FROM public.search_document_production d
                     WHERE d.production_id = c.production_id), 0)::float8 AS semantic
    FROM candidates c
  )
  SELECT grant_id, grant_title, modality, institution_acronym, start_date, end_date, holder_count,
         grant_match, grant_score, researcher_id, lattes_id, researcher_name, role, link_method, link_score,
         production_id, work_key, production_type, production_title, production_year, doi,
         CASE WHEN lexical >= {lex_min} AND semantic >= {sem_min} THEN 'both'
              WHEN lexical >= {lex_min} THEN 'lexical' ELSE 'semantic' END,
         {lex_w} * lexical + {sem_w} * semantic
  FROM scored
  WHERE lexical >= {lex_min} OR semantic >= {sem_min}
$$;
"""


def _quote(text: str) -> str:
    return "'" + text.replace("'", "''") + "'"


def content_text(title: str | None, abstract: str | None, keywords: list[str] | None) -> str:
    parts = [title or "", abstract or ""]
    if keywords:
        parts.append("Palavras-chave: " + "; ".join(keywords))
    return "\n".join(p for p in parts if p)


STAGES = ["tables", "guidance", "vectors", "links", "finalize"]


async def load(start: str, resume: bool) -> None:
    s = get_settings()
    pool = await asyncpg.create_pool(
        s.asyncpg_dsn, min_size=1, max_size=18, init=Embedder.init_connection, command_timeout=None,
        # if this process dies, the server aborts the running query instead of
        # keeping it (and its locks on the maria schema) alive
        server_settings={"client_connection_check_interval": "10s"},
    )
    embedder = Embedder(pool)
    t0 = time.monotonic()
    run = STAGES[STAGES.index(start):]

    def stage(name: str) -> None:
        print(f"[{time.monotonic() - t0:5.0f}s] {name}", flush=True)

    async with pool.acquire() as con:
        await con.execute(CACHE_DDL)

    if "tables" in run:
        grants, holders = read_grants()
        stage("embeddings: grants")
        title_keys = await embedder.ensure(grants["title"].to_list(), "grant titles")
        contents = [content_text(*row) for row in grants.select("title", "abstract", "keywords").iter_rows()]
        content_keys = await embedder.ensure(contents, "grant contents")
        grants = grants.with_columns(pl.Series("title_key", title_keys), pl.Series("content_key", content_keys))

        stage("tables")
        async with pool.acquire() as con, con.transaction():
            await con.execute(DROP)
            await con.execute(BASE_DDL)
            for obj, text in COMMENTS.items():
                kind = "TABLE" if obj.count(".") == 1 else "COLUMN"
                await con.execute(f"COMMENT ON {kind} {obj} IS {_quote(text)}")
            await con.copy_records_to_table("grants", schema_name="maria", columns=grants.columns,
                                            records=grants.iter_rows())
            await con.execute("""
                UPDATE maria.grants SET
                  title_norm = maria.norm(title),
                  search_text = maria.norm(concat_ws(' ', title, abstract, array_to_string(keywords, ' ')))
            """)
            h_cols = ["grant_id", "holder_seq", "lattes_id", "lattes_status", "start_date", "end_date",
                      "unit", "department", "course", "source_rows"]
            await con.copy_records_to_table("grant_holders", schema_name="maria", columns=h_cols,
                                            records=holders.select(h_cols).iter_rows())
            for idx in ("grant_holders (lattes_id)", "grants (modality)", "grants (institution_acronym)",
                        "grants (start_date)"):
                await con.execute(f"CREATE INDEX ON maria.{idx}")
            await con.execute(GUIDANCE_DDL)
            await con.execute(PRODUCTIONS_SQL)

    if "guidance" in run:
        stage("embeddings: guidance titles")
        async with pool.acquire() as con:
            titles = [r["title"] for r in await con.fetch("SELECT DISTINCT title FROM maria.guidance_titles")]
        keys = await embedder.ensure(titles, "guidance titles")
        async with pool.acquire() as con, con.transaction():
            await con.execute("CREATE TEMP TABLE tk (title text, title_key text) ON COMMIT DROP")
            await con.copy_records_to_table("tk", records=list(zip(titles, keys)))
            await con.execute("UPDATE maria.guidance_titles t SET title_key = tk.title_key "
                              "FROM tk WHERE tk.title = t.title")

    if "vectors" in run:
        stage("guidance title vectors + HNSW index")
        async with pool.acquire() as con:
            await con.execute(HEAVY_SESSION_SQL)
            async with con.transaction():
                await con.execute(VECTORS_SQL)

    if "links" in run:
        async with pool.acquire() as con:
            await con.execute(HEAVY_SESSION_SQL)
            exists = await con.fetchval("SELECT to_regclass('maria.grant_link_progress') IS NOT NULL")
            if not (resume and exists):
                await con.execute(LINKS_TABLE_SQL)
            todo = [r["grant_id"] for r in await con.fetch("""
                SELECT grant_id FROM maria.grants
                WHERE grant_id NOT IN (SELECT grant_id FROM maria.grant_link_progress)
                ORDER BY grant_id""")]
            stage(f"grant -> advisor links: {len(todo)} grants to process")
            sql = LINKS_CHUNK_SQL.format(
                lex_min=s.link_lexical_min, sem_min=s.link_semantic_min,
                lex_w=s.link_lexical_weight, sem_w=s.link_semantic_weight,
                before=s.link_years_before, after=s.link_years_after, k=s.link_candidates,
            )
            started = time.monotonic()
            for i in range(0, len(todo), LINKS_CHUNK):
                chunk = todo[i : i + LINKS_CHUNK]
                async with con.transaction():
                    await con.execute(sql, chunk)
                    await con.execute("INSERT INTO maria.grant_link_progress SELECT unnest($1::text[])", chunk)
                done = i + len(chunk)
                rate = done / (time.monotonic() - started)
                print(f"    {done}/{len(todo)} grants · {rate:.0f}/s · ~{(len(todo) - done) / rate / 60:.0f} min left",
                      flush=True)

    if "finalize" in run:
        stage("views and functions")
        async with pool.acquire() as con, con.transaction():
            await con.execute("CREATE INDEX IF NOT EXISTS grant_advisor_links_advisor_idx "
                              "ON maria.grant_advisor_links (advisor_researcher_id)")
            await con.execute("DROP VIEW IF EXISTS maria.grant_researchers CASCADE")
            for fn in ("grant_outcomes", "search_grants", "search_productions"):
                await con.execute(f"DROP FUNCTION IF EXISTS maria.{fn} CASCADE")
            await con.execute(RESEARCHERS_VIEW_SQL)
            await con.execute(FUNCTIONS_SQL.format(
                lex_min=s.theme_lexical_min, sem_min=s.theme_semantic_min,
                lex_w=s.theme_lexical_weight, sem_w=s.theme_semantic_weight,
                years_after=s.outcome_years_after,
            ))
        async with pool.acquire() as con:
            await con.execute("ANALYZE maria.grants; ANALYZE maria.grant_holders; "
                              "ANALYZE maria.productions; ANALYZE maria.grant_advisor_links;")
            summary = await con.fetchrow("""
                SELECT (SELECT count(*) FROM maria.grants) AS grants,
                       (SELECT count(*) FROM maria.grant_holders) AS holders,
                       (SELECT count(*) FROM maria.guidance_titles) AS guidance_titles,
                       (SELECT count(*) FROM maria.productions) AS productions,
                       (SELECT count(*) FROM maria.grant_advisor_links) AS advisor_links,
                       (SELECT count(DISTINCT grant_id) FROM maria.grant_researchers) AS grants_with_researcher
            """)
            print(dict(summary))
    await pool.close()
    stage("done")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--from", dest="start", choices=STAGES, default=STAGES[0],
                        help="start at this stage (earlier stages must already be loaded)")
    parser.add_argument("--resume", action="store_true",
                        help="with --from links: continue an interrupted links stage")
    args = parser.parse_args()
    asyncio.run(load(args.start, args.resume))


if __name__ == "__main__":
    main()
