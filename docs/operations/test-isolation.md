# Isolamento de testes

Testes PostgreSQL usam exclusivamente o banco `esocial_test`; a operação usa
`esocial`. A suíte exige `ESOCIAL_ENVIRONMENT=test` e o cleanup falha fechado se
o destino não for o banco de testes. O corpus de teste também usa volume próprio.

```sh
docker compose exec -T app uv run pytest -q
```

Pytest não deve alterar o runtime operacional, snapshots oficiais ou artefatos
do corpus de produção.
