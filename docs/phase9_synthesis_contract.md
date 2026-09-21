# Fase 9C — contrato de synthesis cross-source

## Estado

9C está COMPLETE pela migration `0014_complete_synthesis`. A API interna está em
`rag_esocial/synthesis_service.py`. A CLI Complete pertence à 9D e não foi criada.

## Boundary factual

`build_synthesis_context` chama a materialização 9B e expõe somente:

- pergunta e RequestedAspects;
- facts `RESOLVED` com refs `MOS:F*`, `LAYOUT:F*` e `XSD:F*`;
- EvidenceUnits alcançadas por `FactResolutionSupport`, com refs `*:E*`;
- comparisons 9B com refs `X*`;
- cobertura e limitações determinísticas;
- digests de build/request/agregação e revisões.

O contexto não contém PK, `AnswerClaim`, `rendered_answer`, `SearchUnit` ou raw
output de qualquer execução anterior. Source answers podem ser promovidas somente
no caminho single-source, depois de seus links já validados; nunca entram como
evidence ou contexto factual do provider.

## Contract e provider

- contract: `complete-answer-contract-v1`;
- prompt: `complete-synthesis-prompt-v1`;
- renderer: `complete-answer-renderer-v1`;
- provider/model: Ollama / `gemma4:12b`;
- configuração: `temperature=0`, `seed=42`, `num_ctx=8192`, `num_predict=2048`,
  timeout de 600 segundos;
- structured output fechado: `claims`, com `claim_id`, `text`, `fact_refs`,
  `evidence_refs` e `comparison_refs`.

Há no máximo um retry para output estruturalmente inválido. Output estruturalmente
válido, mas com refs/support/membership inválidos, resulta em
`VALIDATION_FAILED`, sem retry. Exceção do provider ou duas falhas estruturais
resultam em `MODEL_ERROR`.

## Status e persistência

`CompleteAnswerRun.execution_state` permanece separado de `status`. A finalização
persiste claims somente depois da validação:

- `complete_answer_claims`;
- `complete_answer_claim_facts`;
- `complete_answer_citations`;
- `complete_answer_claim_comparisons`.

Metadados de provider, model/config digest, revisions, prompt digest, attempts,
raw structured output, validation summary e rendered result ficam no
`CompleteAnswerRun`. A migration `0014_complete_synthesis` é aditiva e não altera
0011, 0012 ou 0013.

Sem facts autorizados, não há model call e o run finaliza deterministicamente como
`ABSTAINED`. Com uma única family factual, claims source-local válidas são
promovidas sem synthesis LLM. Com duas ou três families, o provider é chamado.
Limitações de coverage e falhas source-specific permanecem visíveis e produzem
`PARTIAL` quando há claim final. Divergências são renderizadas a partir das
comparisons persistidas; nenhuma source recebe precedência.

## Validação e renderer

O validator é fechado e determinístico: rejeita refs desconhecidas, prefixos
inválidos, cross-build/cross-run, claims sem fact/evidence, support incompatível,
comparison sem os members da claim e claims multi-source sem comparison quando
necessário. O renderer usa apenas claims validadas, CitationTargets humanas,
atribuição de source, limitações e disclosure determinístico de divergências.

Não há synthesis live, benchmark cross-source, tuning ou comando CLI Complete nesta
subfase. Q14 v1 e Answer Contract v1 permanecem inalterados.
