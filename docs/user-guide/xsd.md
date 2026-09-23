# Consultar o XSD

Use **XSD** para schemas, elementos, tipos, cardinalidade `minOccurs` e
`maxOccurs`, enumerações e patterns. Com um evento explícito, o retrieval limita
o universo ao schema associado deterministicamente à raiz XML do Leiaute.

Exemplos: “quais elementos são filhos de ideEmpregador no XSD do S-1000?”,
“qual o tipo do elemento?” e “há enumeração?”. Filhos diretos só são exibidos
quando a relação estrutural está materializada. Cadeias de shared types que não
possam ser demonstradas com segurança não são inventadas.

Detalhes: [estrutura XSD](../xsd_structure.md).
