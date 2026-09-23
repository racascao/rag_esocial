# Migrations

As migrations Alembic rodam dentro do container:

```sh
docker compose exec -T app uv run alembic heads
docker compose exec -T app uv run alembic current
docker compose exec -T app uv run alembic upgrade head
```

O head atual é `0015_active_runtime`. Mudanças de documentação não requerem
migration. Downgrade só deve ocorrer sob procedimento explícito.
