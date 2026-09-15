# RAG eSocial

Assistente futuro para documentação oficial do eSocial (MOS, Leiaute e XSD). O projeto está na **Fase 0 — Bootstrap**: somente a fundação operacional está implementada.

## Princípios

O projeto é CLI-first, sem frontend, API HTTP ou FastAPI. Todo o ambiente Python roda em containers; o host precisa apenas de Docker e Docker Compose. O banco é PostgreSQL em container, com imagem preparada para pgvector, ainda sem uso de vetores.

O modelo futuro está fixado declarativamente como `gemma4:12b`, mas não é baixado nem executado nesta fase. Quando houver answerer, o LLM só poderá responder com evidência autorizada suficiente e deverá se abster quando ela faltar. Não haverá fallback para conhecimento paramétrico, fine-tuning ou hardcode/overfitting de perguntas específicas.

## Bootstrap

```sh
docker compose build
docker compose up -d
docker compose exec app uv run esocial --version
docker compose exec app uv run esocial db status
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

Fase 0 fornece Typer + Rich, configuração tipada, logging, SQLAlchemy/Alembic, baseline vazio, PostgreSQL e testes. Ainda não existem ingestão, parsers, entidades eSocial, corpus, retrieval, Evidence Assembly, resolução de fatos, embeddings, RAG, prompts, answerer, avaliação DEV ou integração com LLM.

Próximas fases: corpus e proveniência; parsing/modelagem; unidades de busca e evidência; resolução determinística; síntese restrita por evidência; avaliação.

