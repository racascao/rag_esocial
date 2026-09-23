# Testes

```sh
docker compose exec -T app uv run pytest -q
```

Há testes unitários, de integração PostgreSQL e regressões estruturais de MOS,
Leiaute, XSD, retrieval, runtime, Answer Contract e Complete Mode. Testes de
banco usam somente `esocial_test`, com proteção fail-closed antes de operações
destrutivas. Consulte [isolamento de testes](../operations/test-isolation.md).
