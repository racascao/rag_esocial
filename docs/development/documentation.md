# Manutenção da documentação

As páginas do portal ficam em `docs/` e o nav central fica em `mkdocs.yml`.
Para criar uma página, adicione o Markdown no grupo temático correspondente,
adicione-o ao nav e execute o build strict.

```sh
docker compose run --rm -p 8000:8000 app \
  uv run --group docs mkdocs serve -a 0.0.0.0:8000
```

Abra `http://localhost:8000`, que redireciona para `/rag_esocial/`. Para validar sem servidor:

```sh
docker compose exec -T app uv run --group docs mkdocs build --strict
```

O diretório `site/` é gerado e ignorado pelo Git. O workflow de Pages constrói
o mesmo site com `uv sync --frozen --group docs`; não use `mkdocs gh-deploy` nem
publique em branch `gh-pages`. Para ativar a primeira publicação, configure no
repositório: **Settings → Pages → Build and deployment → Source: GitHub Actions**.
