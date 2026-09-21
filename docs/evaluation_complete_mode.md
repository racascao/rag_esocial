# Avaliação Complete Mode — Fase 9E

O benchmark Complete é independente do Q14. O Q14 continua single-source,
congelado e imutável em `evaluation/q14/q14_v1.json`.

## Benchmark v1

O dataset declarativo está em:

```text
evaluation/complete/complete_v1.json
evaluation/complete/complete_v1.json.sha256
```

Ele contém 26 casos, derivados da matriz de cobertura da Fase 9E: agreement,
complementarity, divergence, `NOT_COMPARABLE`, `DIFFERENT_ASPECT`, composições
de uma, duas e três fontes, estados negativos, falhas de source/synthesis,
referências não autorizadas, cross-build, disclosure e replay persistido. O
validator exige IDs únicos, categorias completas, composição válida, status
conhecido, relações `required ⊆ allowed` e ausência de interseção com
`forbidden`.

Digest canônico congelado:

```text
ee18fa66904fe874e13c3b342c93c58c0078ba9d1c4c36b2b6184e438ab013bc
```

O runner nunca reescreve o dataset. Mudança posterior exige novo benchmark
versionado.

## Execuções

```bash
docker compose exec app uv run esocial eval complete --mode fake
docker compose exec app uv run esocial eval complete --mode live-smoke
docker compose exec app uv run esocial eval complete --mode live
docker compose exec app uv run esocial eval complete-review
```

Os reports são separados:

```text
evaluation/complete/complete_v1_fake_report.json
evaluation/complete/complete_v1_live_smoke_report.json
evaluation/complete/complete_v1_live_report.json
evaluation/complete/complete_v1_human_review_template.json
```

O fake é determinístico e cobre todos os 26 casos. O smoke executa um caso
live-eligible representativo; o live executa todos os casos live-eligible. A
configuração live usa exclusivamente o provider Ollama configurado e o modelo
`gemma4:12b`. Q14 não é usado pelo runner Complete.

## Métricas e gates

Os reports distinguem métricas por caso, agregados por categoria e composição
de fontes, fake/live e gates objetivos. São medidos status, política de
chamadas, recall de facts/evidence/comparisons requeridos, referências não
autorizadas, validade de citações, cadeia de suporte, atribuição de fonte,
limitações, disclosure de divergência, validade estrutural, completude de
suporte e replay read-only.

Essas métricas medem estrutura, provenance e política. Não significam correção
semântica, correção jurídica ou qualidade da redação.

## Revisão humana

O template separado começa com `reviewer_status: NOT_REVIEWED` e todos os
julgamentos como `null`. Ele cobre factual correctness, groundedness,
completeness, source attribution, divergence/limitation handling, usefulness
das citações e `overall_human_pass`. Nenhum LLM ou heurística preenche esses
campos.

## Reprodutibilidade e limites

O report fake não contém timestamps ou latência no digest lógico. O report live
registra provider, modelo, runtime e metadados disponíveis, mas o texto live não
é comparado byte a byte. Não existe auto-tuning: resultados semânticos devem ser
encaminhados à revisão humana, sem alterar gold, prompt, retrieval ou modelo.

A Fase 9E não cria migration; o head permanece `0014_complete_synthesis`.
O fechamento da Fase 10 e os gates finais do MVP estão em
[`docs/mvp_final_validation.md`](mvp_final_validation.md).
