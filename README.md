# RAG eSocial

Assistente futuro para documentação oficial do eSocial (MOS, Leiaute e XSD). A Fase 0 foi concluída e a Fase 1 implementa provenance física, aquisição manual, hashes, inventário XSD, snapshots e verificação/freeze.

## Princípios

O projeto é CLI-first, sem frontend, API HTTP ou FastAPI. Todo o ambiente Python roda em containers; o host precisa apenas de Docker e Docker Compose. O banco é PostgreSQL em container, com imagem preparada para pgvector, ainda sem uso de vetores.

O modelo futuro está fixado declarativamente como `gemma4:12b`, mas não é baixado nem executado nesta fase. Quando houver answerer, o LLM só poderá responder com evidência autorizada suficiente e deverá se abster quando ela faltar. Não haverá fallback para conhecimento paramétrico, fine-tuning ou hardcode/overfitting de perguntas específicas.

## Bootstrap

```sh
docker compose build
docker compose up -d
docker compose exec app uv run esocial --version
docker compose exec app uv run esocial db status
docker compose exec app uv run esocial corpus init
docker compose exec app uv run esocial corpus status
docker compose exec app uv run esocial corpus verify
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

Fase 0 fornece Typer + Rich, configuração tipada, logging, SQLAlchemy/Alembic, PostgreSQL e testes. Fases 1–5 fornecem provenance, builds, parsers estruturais, fatos determinísticos e baseline FTS. A Fase 6 adiciona retrieval lexical e evidence assembly auditável, mantendo SearchUnit distinta de EvidenceUnit e CitationTarget; não implementa answerer, embeddings ou RAG. O snapshot oficial inicial permanece DRAFT; nenhum freeze real foi feito.

Para importação manual autorizada, use `esocial corpus artifact import --role ... --file ... --official-url ... --version-label ... --title ... --family ...`. O volume `corpus_data` não é versionado no Git.

Ainda não existe parser semântico XSD, retrieval, Evidence Assembly, resolução de fatos, embeddings, RAG, prompts, answerer, avaliação DEV ou integração com LLM. `SearchProjection` permanece reservada para a Fase 5. Anexos I/II não são parseados por falta de formato físico oficial confirmado no repositório.

Próximas fases: corpus e proveniência; parsing/modelagem; unidades de busca e evidência; resolução determinística; síntese restrita por evidência; avaliação.
