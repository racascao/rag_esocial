# Ambiente de desenvolvimento

O projeto executa build, testes, lint, migrations e documentação dentro dos
containers. Isso evita exigir Python e `uv` no host.

```sh
docker compose up -d --build
docker compose exec -T app uv run ruff check .
docker compose exec -T app uv run pytest -q
```

O ambiente de docs é o grupo `docs` do `pyproject.toml`. Ele não depende de
PostgreSQL, Ollama, corpus, artefatos oficiais ou secrets para construir o site.
