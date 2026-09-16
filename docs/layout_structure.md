# Parser estrutural do Leiaute — Fase 3B

O `LAYOUT_MAIN` HTML é lido com `html.parser` e convertido em uma representação própria `LayoutParseResult`. A materialização transacional cria `LayoutDocument`, `LayoutEvent`, `LayoutGroup` e `LayoutField` vinculados ao `CorpusBuild`.

Stable paths usam a identidade técnica completa: `LAYOUT/S-9999/info/dados/detalhe/aliqRat`. Groups preservam parent, level, descrição, ocorrência e condição; fields preservam tipo, ocorrência, tamanho, casas decimais, condição e descrição. Locator metadata (`source=html`) é apresentação e não participa da CitationIdentity.

`REGRA_*`, `Tabela N`, códigos de evento e `Ver: X > Y` são referências D2, preservadas como `ExplicitReference` com origem no Event/Group/Field mais específico e status `UNRESOLVED`. Nenhuma CanonicalEntity ou resolução D3 é criada.

O harness PostgreSQL reutilizado da Fase 3A valida snapshot sintético congelado, build real, E2E, nova session, idempotência, rollback, reuso de CitationTarget entre dois builds e árvores específicas por build. Anexos I e II não são parseados nesta fase: seus formatos físicos oficiais não estão confirmados no repositório; permanecem apenas artifacts de provenance.

