# Parser estrutural do MOS — Fase 3A

O parser é determinístico e especializado no MOS. Ele materializa `MosDocument`, tópicos/subitens, seções de evento, blocos de metadata, `ContentBlock` e referências explícitas D2 não resolvidas. Não cria `CanonicalEntity`, `SourceFact` ou `SearchUnit`.

A fronteira PDF usa `pypdf`: `PdfTextExtractor` retorna `PdfPageText(page_number, text)` e não expõe objetos da biblioteca ao parser. PDFs inválidos ou sem camada textual geram erro fatal controlado; OCR não é usado. O materializer `materialize_mos` valida build/snapshot/artifact, cria ou reutiliza CitationTargets, associa-os via `CorpusBuildCitationTarget` e persiste referências com origem dentro da transação principal. A página inicial do owner é locator de apresentação (`locator_metadata.page`), nunca parte da stable identity. Reexecução no mesmo build/artifact retorna a materialização existente.

O harness PostgreSQL em `tests/test_mos_integration.py` monta os cinco ArtifactRoles, congela um snapshot sintético pela lógica da Fase 1, cria builds pela lógica da Fase 2 e valida o pipeline completo. Ele também prova idempotência por contagens, reuso de CitationTarget entre builds e rollback após falha intermediária em nova session. A transaction é controlada pela camada externa: o materializer apenas adiciona/flusheia; o commit ou rollback pertence ao chamador.

Paths estáveis usam capítulo, evento e numeração formal: `MOS/CapI/10.3`, `MOS/CapIII/S-1200`, `MOS/CapIII/S-1200/metadata/conceito` e `MOS/CapIII/S-1200/32.2.1`. Página, ordem física e linha são apenas locators futuros.

Os quatro blocos (`Conceito`, `Quem está obrigado`, `Prazo de envio`, `Pré-requisitos`) são detectados quando presentes; ausência gera diagnóstico e não conteúdo inventado. `Example` e `Observation` não são D1 universais. Referências a eventos, campos, grupos, regras e tabelas são D2 e permanecem `UNRESOLVED` até a Fase 4.

O resultado do parser é separado da persistência para permitir fixtures pequenas. A materialização deve ocorrer dentro da transação do `CorpusBuild`; reexecução no mesmo build deve ser rejeitada ou substituída atomicamente antes de qualquer implementação operacional real.
