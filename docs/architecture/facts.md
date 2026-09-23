# Facts e resolução

`SourceFact` guarda fato extraído com origem e build. `ResolvedFact` representa
derivação persistida; `FactResolution` resolve uma solicitação por fonte e
`FactResolutionSupport` registra o suporte autorizado. Relações entre entidades
e referências são persistidas para travessias auditáveis.

| Categoria | Uso no projeto |
| --- | --- |
| D1 | determinístico nativo de estrutura/schema |
| D2 | determinístico por convenção documental |
| D3 | travessia ou relação determinística entre unidades |
| G1/G2 | categorias generativas previstas pela arquitetura, não fato nativo do MVP |
| A | ambíguo ou aberto; não é resolvido por adivinhação |

O MVP executa fatos D1/D2 e relações D3 quando comprovadas. Consulte
[fatos determinísticos](../deterministic_facts.md) e
[fact resolution](../fact_resolution.md).
