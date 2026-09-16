# Plano de implementação — Fases 0–10

- Fase 0: fundação operacional CLI, containers, PostgreSQL e migrations.
- Fase 1: aquisição, versionamento, provenance física e freeze de snapshots.
- Fase 2: `CorpusBuild`, registries de `CitationTarget`/`CanonicalEntity` e `SNAPSHOT_MEMBERSHIP_VALIDITY`; sem parsing semântico e sem `projection_version`. Build somente sobre snapshot congelado; SearchProjection fica na Fase 5.
- Fase 3A: COMPLETE — parser estrutural MOS, PDF textual, materialização PostgreSQL transacional, tópicos/subitens, eventos, metadata e referências D2 unresolved; sem resolução, SourceFact ou SearchProjection.
- Fase 3B: COMPLETE para `LAYOUT_MAIN` — parser HTML Event/Group/Field, materialização PostgreSQL, CitationTargets, referências D2 unresolved, idempotência, rollback e E2E; Anexos I/II permanecem não parseados por formato oficial ainda não confirmado.
- Fase 3C: COMPLETE para `XSD_PACKAGE` — parser estrutural, materialização PostgreSQL, E2E em nova sessão, idempotência, rollback, provenance e B1/B2 com CitationTargets compartilhadas.
- Fase 4: COMPLETE — SourceFacts D1/D2, CanonicalEntities transversais, resolução determinística de referências, relações auditáveis e validação PostgreSQL; próxima Fase 5: SearchProjection + baseline FTS.
- Fase 5: COMPLETE — SearchProjection configurável, nove perfis de SearchUnit e baseline PostgreSQL FTS; próxima Fase 6: retrieval e evidence assembly.
- Fase 6: COMPLETE — retrieval FTS, EvidenceSet/EvidenceUnit renderizada de fonte autorizada e validação PostgreSQL; próxima Fase 7: RequestedFact e resolução orientada à consulta.
- Avaliação DEV da Fase 6: dataset versionado, métricas por profile e relatório determinístico; não é holdout cego nem seleciona profile vencedor.
- Fase 3: identidade determinística, incluindo tipos compartilhados `T_*/TS_*`.
- Fase 4: fatos e travessia D3; `FactType` não é D1/D2/D3.
- Fase 5: `SearchProjection` e `SearchUnit`, distintos de `CitationTarget`.
- Fase 6: Evidence Assembly experimental e resolução.
- Fase 7: síntese restrita por evidência.
- Fase 8: benchmark de answerer/modelo.
- Fase 9: investigação de stale-copy, sem presumir que exista.
- Fase 10: avaliação e operação.

Invariantes são introduzidos na fase em que surgem. NL → RequestedFact, G2, Example/Observation, relações/divergências e referências órfãs permanecem decisões dependentes de evidência e amostragem.
