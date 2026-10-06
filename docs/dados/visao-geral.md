# Visão geral: bolsistas por cotas

## O que é

Um registro de **bolsistas por cotas** de Iniciação Científica, Mestrado,
Mestrado Profissional e Doutorado, a partir de 2005, quase todos em
instituições da Bahia. Cada linha da planilha descreve **um bolsista**
(estudante) em **um projeto**: título, resumo, palavras-chave, instituição,
área e período.

O arquivo é `data/raw/scholarships.parquet`. O CPF da origem foi trocado pelo
Lattes ID (veja o relatório no `README.md` do repositório e as
[limpezas](limpeza.md)).

!!! important "Conhecemos os bolsistas, não as bolsas"
    A planilha identifica **quem recebeu bolsa** (o bolsista, pelo Lattes), mas
    **não identifica a bolsa**. Não há como saber quais registros pertencem à
    mesma bolsa, nem quantas bolsas existem. Por isso:

    - **contamos bolsistas** (pessoas distintas) e **registros de bolsistas**;
    - **não informamos número de bolsas.** Quando alguém pergunta por bolsas, o
      chatbot explica essa distinção e responde em bolsistas.

## Números principais

| Métrica | Valor |
|---|---:|
| Linhas na planilha | 45.425 |
| **Registros de bolsistas** (`maria.holder_records`) | **43.176** |
| **Bolsistas** (pessoas distintas) | **32.959** |
| Pessoas com mais de um registro | 7.858 (até 7) |
| Instituições (siglas) | 61 |
| Áreas | 164, em 11 grandes áreas |
| Início dos registros | 2005 a 2026 |
| Bolsas | **não identificáveis** na base |

!!! warning "Registro ≠ pessoa"
    Uma pessoa pode ter vários registros, como renovações de IC ou IC seguida
    de mestrado. "Quantos bolsistas" conta **pessoas** (Lattes distintos).
    "Quantos registros" conta **linhas**. São 43.176 registros para 32.959
    pessoas.

## Por modalidade

| `modality` | Rótulo original | Registros | Bolsistas (pessoas) |
|---|---|---:|---:|
| `undergraduate_research` | Iniciação Científica - Cotas | 31.139 | 23.825 |
| `masters` | Mestrado - Cotas | 7.345 | 7.211 |
| `doctorate` | Doutorado - Cotas | 3.793 | 3.672 |
| `professional_masters` | Mestrado Profissional - Cotas | 899 | 895 |

A soma de pessoas por modalidade (35.603) é maior que o total de pessoas
(32.959), porque quem passou por mais de uma modalidade conta em cada uma.

## Instituições com mais bolsistas

| Sigla | Registros | Bolsistas |
|---|---:|---:|
| UFBA | 13.466 | 10.957 |
| UESC | 4.914 | 3.727 |
| UESB | 4.577 | 3.409 |
| UEFS | 4.361 | 3.199 |
| UNEB | 4.229 | 3.427 |
| UFRB | 2.326 | 1.940 |
| UNIFACS | 1.204 | 1.004 |
| EMBRAPA | 1.145 | 596 |
| FIOCRUZ | 1.081 | 659 |
| IFBA | 1.035 | 816 |

## Ligação com o SIMCC

Os bolsistas são em sua maioria **estudantes**, e poucos estão cadastrados no
SIMCC. Para chegar à produção científica, cada registro também é ligado ao
**orientador**, pela orientação registrada no SIMCC. Veja [SIMCC e
ligações](simcc.md).

Para a análise completa, veja [Análise da base](analise.md). Para cada
transformação feita nos dados, veja [Limpezas](limpeza.md).
