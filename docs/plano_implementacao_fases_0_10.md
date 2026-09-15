# Plano de implementação — Fases 0–10

- Fase 0: fundação operacional CLI, containers, PostgreSQL e migrations.
- Fase 1: aquisição, versionamento, provenance física e freeze de snapshots.
- Fase 2: `CorpusBuild`, registries de `CitationTarget`/`CanonicalEntity` e `SNAPSHOT_MEMBERSHIP_VALIDITY`; sem parsing semântico e sem `projection_version`. Build somente sobre snapshot congelado; SearchProjection fica na Fase 5.
- Fase 3: identidade determinística, incluindo tipos compartilhados `T_*/TS_*`.
- Fase 4: fatos e travessia D3; `FactType` não é D1/D2/D3.
- Fase 5: `SearchProjection` e `SearchUnit`, distintos de `CitationTarget`.
- Fase 6: Evidence Assembly experimental e resolução.
- Fase 7: síntese restrita por evidência.
- Fase 8: benchmark de answerer/modelo.
- Fase 9: investigação de stale-copy, sem presumir que exista.
- Fase 10: avaliação e operação.

Invariantes são introduzidos na fase em que surgem. NL → RequestedFact, G2, Example/Observation, relações/divergências e referências órfãs permanecem decisões dependentes de evidência e amostragem.
