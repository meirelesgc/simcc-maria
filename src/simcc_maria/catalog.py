"""Catálogo da tabela maria.bolsas: tipos, descrições e regras de negócio.

É a fonte única usada no DDL (COMMENT ON COLUMN) e no prompt do LLM.
"""

TABLE = "maria.bolsas"

TABLE_DESCRIPTION = (
    "Bolsas de produtividade do CNPq (PQ e DT) VIGENTES em 08/09/2026. "
    "Uma linha por bolsa. Não é histórico: bolsas encerradas não aparecem."
)

# coluna -> (tipo Postgres, descrição)
COLUMNS: dict[str, tuple[str, str]] = {
    "id_lattes": ("varchar(16)", "ID do currículo Lattes (16 dígitos, texto). Identifica a pessoa."),
    "nome_beneficiario": ("text", "Nome do pesquisador. Há homônimos; use id_lattes para contar pessoas."),
    "pais": ("text", "Sempre 'Brasil'."),
    "regiao": ("text", "Região do Brasil."),
    "uf": ("char(2)", "Sigla da UF (ex.: SP, BA). Prefira filtrar por esta coluna."),
    "uf_nome": ("text", "Nome da UF SEM ACENTO (ex.: 'Sao Paulo')."),
    "cidade": ("text", "Cidade da instituição, SEM ACENTO (ex.: 'Florianopolis')."),
    "linha_fomento": ("text", "Constante: 'BOLSAS DE FORMAÇÃO E DE PESQUISADORES'."),
    "grande_area": ("text", "Grande área do conhecimento. 'Tecnologias' só existe em bolsas DT."),
    "area": ("text", "Área do conhecimento."),
    "subarea": ("text", "Subárea. 'Não informada' em 1.459 linhas."),
    "modalidade_cod": ("varchar(2)", "'PQ' (Produtividade em Pesquisa) ou 'DT' (Desenvolvimento Tecnológico)."),
    "modalidade": ("text", "Nome por extenso da modalidade."),
    "chamada": ("text", "Título do edital que concedeu a bolsa."),
    "categoria_nivel": ("varchar(2)", "Nível da bolsa. DUAS ESCALAS: chamadas até 2023 usam 1A>1B>1C>1D>2; chamadas 18/2024 e 23/2025 usam A>B>C. SR = sênior. Não são equivalentes."),
    "programa_fomento": ("text", "Programa de fomento. 'Programas Básicos' em 94%; em DT indica o programa tecnológico."),
    "instituicao": ("text", "Nome da instituição seguido da sigla na mesma string (ex.: 'Universidade de Brasília UnB'). Filtre com ILIKE."),
    "data_inicio": ("date", "Início da vigência."),
    "data_termino": ("date", "Término da vigência. Todas terminam a partir de 31/12/2026."),
    "data_extracao": ("date", "Constante: 2026-09-08."),
    "qtd_auxilio": ("smallint", "Sempre 0."),
    "qtd_bolsa": ("smallint", "Quantidade de bolsas da linha (1, ou 2 em 7 linhas)."),
}

# Colunas com poucos valores distintos: o prompt recebe a lista completa,
# para o LLM filtrar com valores que existem de fato.
CATEGORICAL = [
    "regiao", "uf", "grande_area", "modalidade_cod",
    "categoria_nivel", "programa_fomento", "chamada",
]

RULES = """\
- "Quantos pesquisadores/bolsistas/pessoas" → count(DISTINCT id_lattes). \
"Quantas bolsas" → sum(qtd_bolsa). São 17.952 bolsas para 17.940 pessoas.
- Texto livre do usuário (cidade, instituição, área): use \
unaccent(coluna) ILIKE unaccent('%termo%'). uf_nome e cidade não têm acento.
- Se o termo do usuário corresponde exatamente a um valor existente de \
grande_area, area ou subarea (ignorando acento/caixa), use IGUALDADE \
(area = 'Física'). Só use ILIKE quando não houver valor exato; nesse caso, \
registre nas ressalvas que áreas relacionadas foram incluídas.
- Sigla de instituição: compare a sigla exata no FIM do campo, \
instituicao ~ '\\mUSP$'. Não use '%USP%': pegaria unidades vinculadas que \
são instituições distintas na base (ex.: HCFMUSP, EEUSP). Se o usuário quiser \
incluí-las, ele dirá; mencione essa escolha nas ressalvas.
- Nível: se o usuário citar '1A', a resposta cobre só chamadas antigas; \
'A' só as novas. Nunca some as duas escalas como se fossem uma.
- Percentuais, totais e médias devem ser calculados no SQL, nunca estimados.
- Ordene rankings de forma determinística e use LIMIT em listagens.
"""
