# Fatos determinísticos

A Fase 4 transforma estruturas já materializadas em `CanonicalEntity` transversal e fatos locais `SourceFact` vinculados ao `CorpusBuild` e à sua `CitationTarget` de origem.

`SourceFact.extraction_kind` é somente `D1` (estrutura nativa) ou `D2` (convenção documental). Resoluções entre unidades são D3 e ficam em `ReferenceResolution`/`EntityRelation`; `ResolvedFact` só deve ser criado quando houver derivação lossless comprovada.

As referências preservam seu texto bruto e recebem uma chave normalizada. `REGRA_*` e `Tabela N` permanecem sem target documental enquanto os Anexos II/I não forem parseados. Não há fuzzy matching, LLM, Search, retrieval ou RAG.

Canonical entities são transversais a versões e builds; fatos, resoluções e relações são build-specific. Chaves e uniques tornam a execução idempotente e a camada externa controla commit/rollback. Origins apontam para `CitationTarget`; esse registro versionado não é confundido com `CanonicalEntity`.

A fixture estrutural atual comprova as camadas de identidade e a persistência das estruturas anteriores. A resolução dos Anexos I/II permanece indisponível porque esses artefatos ainda não foram parseados; por isso referências de regra e tabela não recebem alvo documental fictício.
