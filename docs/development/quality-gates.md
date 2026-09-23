# Quality gates

```sh
docker compose exec -T app uv run ruff check .
docker compose exec -T app uv run ruff format --check .
docker compose exec -T app uv run pytest -q
docker compose exec -T app uv run --group docs mkdocs build --strict
```

O build strict valida links, nav e warnings. Benchmarks congelados devem manter
os hashes canônicos e não podem ser alterados para acomodar uma execução.
