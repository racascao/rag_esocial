# Diagnóstico

Use a opção **Status** para identificar versões, snapshot, build, revisões de
parser/search e geração. Para diagnóstico avançado, use a interface Typer no
container:

```sh
docker compose exec -T app uv run esocial --help
docker compose exec -T app uv run esocial db status
```

O diagnóstico não deve alterar o corpus ativo.
