# Avaliação DEV de retrieval e evidence

O dataset versionado `evaluation/dev/retrieval_evidence_v1.json` é um baseline de engenharia e declara explicitamente que não é blind holdout. Ele contém seis casos sintéticos distribuídos entre MOS, Leiaute e XSD, com gold por `document_family` e path estável.

O evaluator resolve gold contra CitationTargets associados ao build; gold ausente falha explicitamente com `GOLD_TARGET_NOT_IN_BUILD`. Por caso/profile reporta RetrievalTargetRecall@K, MRR, EvidenceRequiredRecall, EvidenceTargetPrecision e `all_required_covered`. Resultados são observacionais e não escolhem profile vencedor.
