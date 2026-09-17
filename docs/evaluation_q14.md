# Avaliação Q14 v1

## Dataset congelado

O benchmark DEV está em `evaluation/q14/q14_v1.json`, com digest canônico em
`evaluation/q14/q14_v1.json.sha256`. O validator exige exatamente 14 casos,
IDs únicos, schema fechado e esta distribuição:

- 8 `ANSWERED`: 3 MOS, 3 LAYOUT e 2 XSD;
- 3 `PARTIAL`: um por família;
- 3 `ABSTAINED`: um por família.

Cada caso declara RequestedFacts estruturados e identidades documentais estáveis,
nunca PKs do banco. O template de revisão humana fica em
`evaluation/q14/q14_v1_human_review_template.json`; seus julgamentos começam
como `null` e não são inferidos de citation membership.

## Execução

```sh
# valida schema e SHA-256 congelado
docker compose exec app uv run esocial eval q14 \
  --build BUILD --validate-only

# adapter fake determinístico
docker compose exec app uv run esocial eval q14 \
  --build BUILD --fake --output evaluation/q14/q14_v1_fake_report.json

# gemma4:12b real
docker compose exec app uv run esocial eval q14 \
  --build BUILD --output evaluation/q14/q14_v1_live_report.json
```

`--case CASE_ID` permite o smoke canônico sem mudar o arquivo congelado. A
execução completa sempre processa os 14 casos. Casos `ABSTAINED` comprovam zero
chamadas ao provider; casos `PARTIAL` enviam apenas fatos resolvidos.

## Métricas automáticas

- `StructuredOutputValidRate`: runs com contrato estrutural aceito / casos.
- `AnswerRunSuccessRate`: status observado igual ao esperado / casos.
- `ClaimCitationCoverage`: claims com ao menos uma citação / claims persistidas.
- `CitationMembershipValidity`: citações aceitas pela cadeia autorizada /
  citações persistidas.
- `UnauthorizedCitationRate`: casos com referência de evidência não autorizada /
  casos.
- `UnauthorizedFactReferenceRate`: casos com referência factual não autorizada /
  casos.
- `AbstentionComplianceRate`: abstentions observadas / abstentions esperadas.
- `ModelCallAvoidanceOnAbstain`: abstentions com zero chamadas / abstentions
  esperadas.
- `PartialAnswerContractCompliance`: partials observados / partials esperados.
- `ExpectedFactReferenceCoverage`: referências factuais persistidas / fatos
  resolvidos esperados nos casos executados.

O report contém dataset/build digests, provider, modelo/configuração, revisões,
resultado e claims por caso, erros, metadata de runtime/provider e agregados por
família. A serialização usa chaves ordenadas. O fake comprova determinismo lógico
e byte a byte; duas inferências reais não precisam produzir texto idêntico.

Estas métricas não alegam correção jurídica nem groundedness semântico. Esses
itens dependem da revisão humana registrada no template separado.

## Resultado canônico da Fase 8

Execução em 17/09/2026 com Ollama `0.33.2` e `gemma4:12b`, endpoint interno
`http://ollama:11434` e porta diagnóstica `11436`:

- SHA-256 canônico do Q14 v1:
  `30dad081fde8b59f448bd8675fdfa298c22c8d2da5dddf9ba7f30e3e8796e3c7`;
- smoke live: `ANSWERED`, structured output validado e persistido;
- fake: 14/14 status exatos;
- live: 14/14 status exatos (8 `ANSWERED`, 3 `PARTIAL`, 3 `ABSTAINED`);
- os três casos `ABSTAINED` tiveram zero chamadas ao modelo;
- todas as dez métricas automáticas atingiram o valor esperado (taxas positivas
  `1.0` e taxas de referência não autorizada `0.0`).

Artefatos: `q14_v1_fake_report.json`, `q14_v1_live_smoke_report.json` e
`q14_v1_live_report.json`, no mesmo diretório do dataset. Os resultados são DEV,
não holdout cego e não substituem revisão humana.
