# RAG eSocial

Assistente baseado em evidência para documentação oficial do eSocial (MOS, Leiaute e XSD), com corpus versionado, retrieval auditável, resolução determinística de fatos e Answer Contract single-source.

## Princípios

O projeto é CLI-first, sem frontend, API HTTP ou FastAPI. Todo o ambiente Python roda em containers; o host precisa apenas de Docker e Docker Compose. O banco é PostgreSQL em container, com imagem preparada para pgvector, ainda sem uso de vetores.

O modelo fixo é `gemma4:12b`, executado pelo Ollama containerizado. O LLM só recebe fatos e evidências autorizados; sem suporte suficiente, o pipeline se abstém antes da chamada. Não há fallback para conhecimento paramétrico, fine-tuning ou hardcode/overfitting de perguntas específicas.

## Bootstrap

```sh
docker compose build
docker compose up -d
docker compose exec app uv run esocial --version
docker compose exec app uv run esocial db status
docker compose exec app uv run esocial corpus init
docker compose exec app uv run esocial corpus status
docker compose exec app uv run esocial corpus verify
docker compose --profile llm up -d
docker compose exec app uv run esocial llm status
```

## Validação

```sh
docker compose exec app uv run alembic upgrade head
docker compose exec app uv run alembic downgrade -1
docker compose exec app uv run alembic upgrade head
docker compose exec app uv run ruff check .
docker compose exec app uv run ruff format --check .
docker compose exec app uv run pytest
```

## Estado e roadmap

Fase 0 fornece Typer + Rich, configuração tipada, logging, SQLAlchemy/Alembic, PostgreSQL e testes. Fases 1–5 fornecem provenance, builds, parsers estruturais, fatos determinísticos e baseline FTS. A Fase 6 adiciona retrieval lexical e evidence assembly auditável. A Fase 7 está COMPLETE: RequestedFact build-specific, resolução determinística por fonte, status de abstention, suporte factual autorizado e avaliação DEV. A Fase 8 está COMPLETE: Answer Contract v1, preflight e allowlists F*/E*, claim ledger persistido, validator e renderer determinísticos, Ollama/`gemma4:12b`, CLI e Q14 congelado. O Q14 fake e live processaram 14/14 casos com os status esperados; os reports estão em `evaluation/q14/`. O snapshot oficial inicial permanece DRAFT e nenhum CorpusBuild oficial foi criado.

Para importação manual autorizada, use `esocial corpus artifact import --role ... --file ... --official-url ... --version-label ... --title ... --family ...`. O volume `corpus_data` não é versionado no Git.

Ainda não existem embeddings, reranker, question decomposition ou síntese cross-source. O answerer permanece estritamente single-source e não arbitra fontes. Anexos I/II não são parseados por falta de formato físico oficial confirmado no repositório.

Próxima fase: Fase 9 — Complete Mode / síntese cross-source. Ela não foi iniciada.
