# Arquitetura

## Objetivo

Responder pelo terminal a perguntas como:

> As bolsas contemplam pesquisas na temática Dengue? Se sim, qual o resultado
> desse fomento? Ele gerou artigos? livros? capítulos? de quem, quando e quantos

Isso exige quatro coisas:

1. **Busca temática nos registros de bolsistas**, por palavra-chave e por
   semântica.
2. **Ligação do registro a pesquisadores do SIMCC**, seja o bolsista ou o
   orientador.
3. **Produção desses pesquisadores**, dentro de uma janela de tempo e sobre o
   mesmo tema.
4. **Agregação sem contar duas vezes**: uma pessoa pode ter vários registros, e
   uma obra aparece uma vez por coautor.

A base identifica **bolsistas, não bolsas**. Quando a pergunta fala em bolsas
(como a acima), a resposta deixa claro que os números se referem a bolsistas.

## Visão geral

```mermaid
flowchart TD
    Q[pergunta] --> A["<b>Agente</b> · LLM_MODEL<br/>loop de ferramentas, até 12 passos"]
    A -->|run_sql + :placeholders de embedding| DB
    subgraph DB [Postgres]
      direction LR
      F["funções maria.*<br/>search_records · search_productions · record_outcomes"]
      T["tabelas e views maria.*<br/>holder_records · record_researchers · productions"]
      S["SIMCC public.*<br/>researcher · guidance · bibliographic_production<br/>search_document_production (embeddings)"]
    end
    DB -->|resultado| A
    A --> R["resposta + conferência dos números"]
    A -.-> L[[logs/*.jsonl]]
```

A lógica que define **o que conta** como correto fica no banco, em funções e
views determinísticas e testáveis. O LLM decide **quais perguntas fazer ao
banco** e como agregar e apresentar o resultado. Assim, regras críticas como
"bolsistas, não bolsas" e "uma obra conta uma vez" não dependem
de o modelo acertar um JOIN complexo.

## Busca híbrida (lexical + semântica)

Toda busca por similaridade combina dois métodos. **Cada um tem a própria
linha de corte**, e o resultado é a **união** dos dois:

```
mantém o candidato se   lexical ≥ LEXICAL_MIN   OU   semantic ≥ SEMANTIC_MIN
score = LEXICAL_WEIGHT · lexical + SEMANTIC_WEIGHT · semantic
match_method = lexical | semantic | both
```

| Uso | Lexical | Semântico |
|---|---|---|
| **Tema nos registros de bolsistas** (`search_records`) | o termo aparece (início de palavra, sem acento) em título, resumo ou palavras-chave → 1/0 | cosseno entre o embedding da pergunta e o de título + resumo + palavras-chave |
| **Tema nas produções** (`search_productions`) | o termo aparece no título | cosseno com o embedding do SIMCC (`search_document_production`) |
| **Registro → orientador** (`record_advisor_links`) | similaridade de trigramas (`pg_trgm`) entre os títulos | cosseno entre o embedding do título do projeto e o do título da orientação |

!!! note "Candidatos da ligação registro → orientador"
    Comparar cada registro com as 158 mil orientações por trigramas levaria horas
    (~150 ms por registro, mesmo com índice GIN). Por isso, os **candidatos** de
    cada registro são as orientações de **título idêntico** mais os **20 títulos
    mais próximos no índice HNSW** (`LINK_CANDIDATES`). Sobre os candidatos,
    as **duas** notas são calculadas, e cada método aplica a própria linha de
    corte. Um título com trigramas ≥ 0,80 é quase idêntico e cai entre os
    vizinhos mais próximos, então a perda é teórica.

### Calibração (05/10/2026)

**Tema.** A escala do cosseno depende do texto embedado. Com `"dengue"`, o
corte de 0,40 traz poucos registros sem a palavra, todos de temas vizinhos
(chikungunya, arboviroses, *Aedes*). Com uma frase longa ("dengue e outras
arboviroses transmitidas pelo *Aedes aegypti*"), o mesmo corte traz mais de
340 registros, com muito ruído. Por isso, o prompt exige que o texto embedado seja
**o nome curto do tema**. Muitos registros que citam "dengue" ficam abaixo de
0,40: a parte lexical é indispensável.

**Ligação com o orientador.** Os casos aprovados só pela semântica (≥ 0,90)
são quase todos o mesmo projeto com título abreviado (ex.: "*Moniliophthora
perniciosa*" ↔ "*M. perniciosa*"). Os aprovados só pela parte lexical incluem
projetos "irmãos" do mesmo grupo (ex.: "*Rhinella hoogmoedi*" ↔ "*Rhinella
crucifer*", 0,83), que costumam ter o mesmo orientador. O embedding diferencia
maiúsculas e minúsculas ("ANÉIS E MÓDULOS" ↔ "Anéis E Módulos" dá 0,63), o que
subestima a nota semântica de títulos em CAIXA ALTA. Uma melhoria possível é
vetorizar os títulos em minúsculas.

Os valores padrão e as variáveis de ambiente estão em
[Pipeline › Parâmetros](../dados/pipeline.md#parametros-env). A coluna
`match_method` / `link_method` sempre diz por qual método cada item entrou, e
a resposta informa essa distribuição.

!!! note "Cobertura semântica das produções"
    Só artigos, livros e capítulos com documento em `search_document_production`
    têm embedding (131 mil de 295 mil). Os demais só são encontrados pelo método
    lexical.

## Ligação registro → pesquisador

```mermaid
flowchart LR
    H[maria.holder_records] -->|lattes_id = researcher.lattes_id| R[(public.researcher)]
    H -->|título ≈ título da orientação<br/>mesma modalidade · ano compatível| GT[maria.guidance_titles]
    GT -->|researcher_id| R
    R --> P[maria.productions]
```

- **`holder`:** o próprio bolsista está no SIMCC. A ligação é declarada pelo
  Lattes.
- **`advisor`:** existe uma orientação no SIMCC com título equivalente ao da
  projeto, mesma modalidade (IC ↔ Iniciação Científica, Mestrado ↔ Dissertação,
  Doutorado ↔ Tese) e ano entre o início − 1 e o fim previsto + 2. A ligação é
  **inferida**, e a evidência fica em `maria.record_advisor_links`.

## Resultado do fomento: `maria.record_outcomes`

Para um tema, a função devolve uma linha por **(registro de bolsista, pesquisador,
produção)** em que:

1. o registro (projeto do bolsista) casa com o tema;
2. o pesquisador está ligado ao registro (`holder` ou `advisor`);
3. a produção é artigo, livro ou capítulo do pesquisador, publicada entre o
   ano de início do registro e o ano de término + `OUTCOME_YEARS_AFTER`;
4. a produção também casa com o tema.

**Uma obra pode aparecer em várias linhas** (vários registros, vários
pesquisadores, um registro por coautor no SIMCC). Contamos obras com
`count(DISTINCT work_key)`, em que `work_key` é o DOI ou, sem DOI, o título
normalizado + ano.

## O agente

`src/simcc_maria/agent.py`

- **Modelo:** `gpt-5.5-2026-04-23` via **Responses API** (`use_responses_api`).
  Nesse modelo, a OpenAI só aceita ferramentas com `reasoning_effort` nessa API.
- **Uma ferramenta:** `run_sql(purpose, sql, embed[])`, que executa um SELECT
  somente leitura. Placeholders `:nome` no SQL são trocados pelo embedding do
  texto informado em `embed`, gerado com o mesmo modelo do SIMCC e guardado em
  cache.
- **Vários passos:** o modelo pode explorar, conferir títulos e agregar antes
  de responder, até `AGENT_MAX_STEPS` (15). O prompt pede economia: de 4 a 6
  consultas, com vários números por consulta. No limite, ele é obrigado a
  responder com o que tem e a dizer o que não conseguiu verificar.
- **Prompt de sistema** (`catalog.py`): descrição dos objetos, números de
  referência da base (lidos do banco na inicialização), as regras de contagem
  e o formato da resposta.
- **Conferência:** todo número citado na resposta precisa aparecer no
  resultado de algum passo. Os que não aparecem são marcados com ⚠.

### Regras de contagem no prompt

1. **Bolsistas, não bolsas.** A base não identifica bolsas: o chatbot nunca
   informa número de bolsas e, se perguntado, explica a distinção. Bolsistas
   (pessoas) são `count(DISTINCT lattes_id)` + registros sem Lattes; registros
   são as linhas de `holder_records`.
2. **Nunca contar linhas de um JOIN.** Sempre `count(DISTINCT …)` sobre a
   entidade contada.
3. **Obras contam por `work_key`.**
4. **Cobertura:** dizer quantos bolsistas do tema têm algum pesquisador ligado,
   para que "nenhuma produção encontrada" não seja lido como "nenhuma
   produção".
5. **Instituições:** agrupar pela sigla, que tem um nome canônico.

## Auditoria

Usamos um JSONL por sessão em `logs/`. O cabeçalho (`session_start`) guarda
todos os parâmetros (modelo, linhas de corte, pesos, janelas), o prompt
completo, o hash dos dados e o commit. Depois vêm um evento `step` por
consulta (propósito, SQL, textos embedados, linhas, amostra, erro) e um
`answer` por resposta (texto, números não conferidos, tokens, custo, tempo).

O custo (`cost_usd`) é calculado com os preços de
[Pipeline › Parâmetros](../dados/pipeline.md#parametros-env): tokens de entrada
(separando os lidos do cache da OpenAI, `tokens_cached`), de saída (incluindo
raciocínio) e de embeddings das consultas (`tokens_embed`). É uma estimativa:
confira os preços em [openai.com/api/pricing](https://openai.com/api/pricing)
quando o modelo mudar.

```python
import polars as pl
log = pl.read_ndjson("logs/*.jsonl", infer_schema_length=None)
log.filter(pl.col("event") == "step").select("turn", "step", "purpose", "sql", "rows")
log.filter(pl.col("event") == "answer").select(pl.col("cost_usd").sum())  # custo total
```
