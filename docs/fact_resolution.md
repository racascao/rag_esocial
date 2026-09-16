# Fact Resolution

`RequestedFact` é uma necessidade factual estruturada, específica de `CorpusBuild`, identificada por tipo, `subject_kind`, `subject_key` estável e qualifiers canônicos. A unidade de execução é `RequestedFact × DocumentFamily`.

O registry é derivado dos `SourceFact` materializados no build; ele declara as famílias capazes de sustentar cada tipo. A resolução usa somente `SourceFact` cujo `CitationTarget` esteja em `EvidenceSet`. O precheck de cobertura apenas prova existência: nunca fornece valor.

Os estados são `RESOLVED`, `SOURCE_NOT_APPLICABLE`, `ASPECT_NOT_COVERED`, `NO_RELEVANT_EVIDENCE` e `UNSUPPORTED`. Um resultado resolvido exige `FactResolutionSupport` até EvidenceUnit, CitationTarget e SourceFact. Valores SINGLE conflitantes retornam `UNSUPPORTED`, jamais o primeiro valor.

RequestedFact, FactResolution e support são idempotentes por build/configuração e transacionais. B1/B2 mantêm essas linhas próprias, embora possam reutilizar CitationTarget e CanonicalEntity transversais.
