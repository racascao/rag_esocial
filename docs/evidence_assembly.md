# Retrieval e evidence assembly

A Fase 6 usa somente o FTS lexical da projeção escolhida. `SearchUnit` e seu texto continuam retrieval-only: um hit apenas seleciona uma `CitationTarget` autorizada.

`EvidenceUnit` é renderizada novamente das estruturas do `CorpusBuild` (MOS, Leiaute ou XSD), nunca de `SearchUnit.search_text`. `EvidenceSet` é idempotente por build, projeção, query e políticas versionadas; itens preservam rank e score do hit que motivou a inclusão. Alvos sem associação ao build são recusados.

Evidence e seus conjuntos são build-specific; CitationTarget continua versionada e transversal. Não há embedding, reranker, LLM, answerer ou RequestedFact nesta fase.
