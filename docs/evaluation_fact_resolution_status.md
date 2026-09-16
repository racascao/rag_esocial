# Avaliação DEV de Fact Resolution

O dataset `evaluation/dev/fact_resolution_status_v1.json` é DEV, não holdout cego. `GoldCoverageState` (`COVERED`, `SOURCE_NOT_APPLICABLE`, `ASPECT_NOT_COVERED`, `CORPUS_UNSUPPORTED`) não é `RuntimeStatus`.

O report mede `CoveredFactResolutionRecall`, `ResolvedValueExactMatch`, `RuntimeStatusExactMatch` e `NoRelevantEvidenceRateOnCovered`. Este último é uma falha de retrieval/evidence em corpus coberto, não ausência gold. A matriz gold × runtime torna a separação auditável; não há auto-tuning nem thresholds de produto.
