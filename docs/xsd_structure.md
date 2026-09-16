# Estrutura XSD

A Fase 3C lê exclusivamente o artefato `XSD_PACKAGE` de um snapshot congelado. O ZIP é inventariado na Fase 1; cada build recebe uma árvore derivada própria.

Schemas são classificados como `EVENT_SCHEMA`, `SHARED_TYPES_SCHEMA` ou `AUXILIARY_SCHEMA`. Namespaces, QNames, cardinalidades, hierarquia nomeada, tipos compartilhados, facets, enumerações e documentação são preservados. Stable paths usam namespace e nomes técnicos, nunca XPath ou índices posicionais.

`CitationTarget` é reutilizado entre builds. `ExplicitReference` registra includes, imports, tipos compartilhados e convenções documentais como `UNRESOLVED`, com origin estrutural. Cardinalidade XML não implica requiredness funcional; documentation é D2. Não há resolução D3, `SourceFact`, search ou RAG nesta fase.

O harness PostgreSQL valida materialização em nova sessão, idempotência por contagens, rollback após falha intermediária, origins persistidas e dois builds sobre o mesmo snapshot congelado, com árvores distintas e `CitationTarget` compartilhada. O snapshot oficial continua DRAFT e não é processado.
