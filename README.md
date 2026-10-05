# SIMCC Maria

Chatbot no terminal para perguntas em linguagem natural sobre as bolsas de produtividade do CNPq (PQ/DT).

```bash
poetry install --with docs,dev
poetry run ingest       # data/raw/raw-data.xlsx -> data/processed/bolsas_pq_dt.csv
poetry run load-db      # CSV -> maria.bolsas (Postgres)
poetry run maria        # chat
poetry run evaluate     # avaliação com respostas conhecidas
poetry run mkdocs serve # documentação em http://127.0.0.1:8000
```

Requer `.env` com `DATABASE_URL` e `OPENAI_API_KEY`.
