# Repositório

Os módulos de aplicação ficam em `rag_esocial/`; testes em `tests/`; migrations
em `alembic/`; benchmarks e relatórios em `evaluation/`; documentação em `docs/`.
O launcher público é `./esocial` e `docker-compose.yaml` define o ambiente local.

Antes de mudar contratos ou modelos, leia as páginas de arquitetura e os testes
de regressão correspondentes. O produto separa snapshot, build, projection,
runtime, retrieval e evidência.
