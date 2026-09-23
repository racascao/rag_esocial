# Métricas e revisão humana

Para retrieval, o baseline mede `STRICT_TARGET_RECALL`,
`ACCEPTABLE_TARGET_RECALL` e `GRANULARITY_QUALITY`. Para evidence assembly,
mede `REQUIRED_EVIDENCE_RECALL`, `EVIDENCE_EXCESS` e `EVIDENCE_COVERAGE`.

Essas métricas verificam unidade correta e cobertura de evidência sem excesso.
Elas não comprovam sozinhas a correção semântica de uma conclusão; essa etapa
requer revisão humana. Detalhes estão em [avaliação DEV](../evaluation_dev.md).
