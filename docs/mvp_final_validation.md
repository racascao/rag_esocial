# Validação final do MVP

## Status

**Fase 10 — COMPLETE.** As Fases 0–10 estão concluídas. A Fase 11 não foi
iniciada.

Baseline: `b28cd91` na branch `main`. O head Alembic da validação do MVP era
`0014_complete_synthesis`; a operacionalização pós-MVP adiciona somente a
migration aditiva `0015_active_runtime`.

## Gates reproduzíveis

| Gate | Resultado |
|---|---|
| Corpus/versionamento | PASS; o banco atual não materializa snapshot oficial |
| Parsers MOS/Layout/XSD | PASS |
| Facts, resolução e cadeia de suporte | PASS |
| SearchProjection/FTS | PASS |
| Answer Contract single-source | PASS |
| Q14 congelado | PASS; digest canônico `30dad081fde8b59f448bd8675fdfa298c22c8d2da5dddf9ba7f30e3e8796e3c7` |
| Complete benchmark congelado | PASS; digest canônico `ee18fa66904fe874e13c3b342c93c58c0078ba9d1c4c36b2b6184e438ab013bc` |
| Complete orchestration, aggregation e synthesis | PASS |
| CLI Complete e avaliação | PASS |
| Rollback, B1/B2 e nova sessão PostgreSQL | PASS |
| Imutabilidade upstream | PASS |
| Alembic, Ruff e pytest | PASS |
| Revisão humana | `NOT_REVIEWED`; template preparado, sem julgamento automático |

Os reports congelados cobrem fake `26/26`, smoke live `1/1` e execução live
`6/6`, todos com gates estruturais aprovados. O manifesto reproduzível está em
`evaluation/mvp/mvp_v1_manifest.json` no diretório `evaluation/` do repositório.

## Limitações explícitas

O estado atual não é uma certificação jurídica nem um release de produção. A
revisão semântica humana do Complete permanece pendente. O banco corrente não
tem snapshot/build oficial materializado; isso é uma limitação operacional
registrada, não uma alteração do contrato. Retrieval usa PostgreSQL FTS; não há
embeddings, reranker, LLM-as-judge, auto-tuning, fallback paramétrico ou
precedência entre fontes. Anexos físicos cujo formato oficial não foi
confirmado permanecem fora do escopo.

## Reprodução

```text
docker compose build
docker compose up -d db
docker compose exec -T app alembic upgrade head
docker compose exec -T app ruff check .
docker compose exec -T app ruff format --check .
docker compose exec -T app pytest -q
docker compose exec -T app esocial eval mvp
```

O comando `esocial eval mvp` deriva o status dos artefatos e escreve o manifesto;
ele não contém um status final hardcoded.
