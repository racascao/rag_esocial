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

Fase 0 fornece Typer + Rich, configuração tipada, logging, SQLAlchemy/Alembic, PostgreSQL e testes. Fase 1 fornece `DocumentVersion`, `DocumentArtifact`, `CorpusSnapshot`, `SnapshotMember`, armazenamento persistente de raw artifacts, SHA-256, inventário de ZIP e manifesto canônico. O snapshot inicial permanece DRAFT até os cinco papéis obrigatórios serem adquiridos e verificados; nenhum freeze real foi feito.

Para importação manual autorizada, use `esocial corpus artifact import --role ... --file ... --official-url ... --version-label ... --title ... --family ...`. O volume `corpus_data` não é versionado no Git.

Ainda não existem ingestão semântica, parsers MOS/Leiaute/XSD, CorpusBuild, retrieval, Evidence Assembly, resolução de fatos, embeddings, RAG, prompts, answerer, avaliação DEV ou integração com LLM.

Próximas fases: corpus e proveniência; parsing/modelagem; unidades de busca e evidência; resolução determinística; síntese restrita por evidência; avaliação.
