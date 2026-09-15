# Fundação operacional

O container `app` permanece vivo com comando neutro para permitir CLI, Alembic e testes via `docker compose exec`. O ambiente virtual fica em `/opt/venv`, fora do bind mount do código. O serviço `db` usa PostgreSQL 16 com pgvector disponível para fases futuras, sem coluna ou operação vetorial na Fase 0.

Não há serviço Ollama: a CLI e os testes não dependem de LLM. A migration baseline é intencionalmente vazia e existe apenas para provar o pipeline de migrations.

