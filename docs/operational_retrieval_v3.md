# Retrieval operacional determinístico — fts-baseline-v3

O parser e o `CorpusBuild` permanecem `parser-suite-v2`. A revisão v3 cria
`SearchProjection` separadas para o mesmo build; não muda artefatos, snapshot,
CitationTarget nem os benchmarks Q14/Complete. Projections v2 ficam históricas.
Falha de indexação não troca `ActiveRuntime`; sucesso no mesmo build com uma nova
projection incrementa a geração uma única vez.

## Query analysis e vocabulário de schema

`operational_query.analyze_query` produz evento S-XXXX, nomes técnicos já
presentes em paths, famílias explícitas, atributo solicitado, relação e termos
factuais. O vocabulário estático mapeia apenas propriedades existentes:

| Propriedade | Aliases reconhecidos |
| --- | --- |
| `occurrence` | ocorrência, ocorre, cardinalidade, minOccurs, maxOccurs |
| `condition` | condição |
| `description` | descrição |
| `type` | tipo |
| `size` | tamanho |
| `decimals` | decimais |
| `pattern`, `enum` | padrão/pattern, enum/enumeração/valores |
| `parent`, `children` | pai, filho(s), campos/elementos em contexto relacional |

Diacríticos são normalizados para reconhecer o conceito; nomes técnicos e
códigos não são traduzidos nem gerados por modelo. Termos de interface como
“compare”, “evidências”, MOS, Leiaute e XSD são retirados da consulta factual
cross-source, não usados como condições obrigatórias do FTS de cada família.

## Seleção e ordenação

Um código de evento explícito restringe MOS/Leiaute ao segmento estrutural do
path. Para XSD, o código é associado ao `schema_key` pelo nome da raiz XML do
evento já materializado no Leiaute; mapeamento ausente ou ambíguo falha fechado.
Assim, uma menção textual a S-XXXX em outro evento não vira pertencimento.
Nomes técnicos em path prevalecem sobre menções em descrições. Relações
`LayoutGroup → LayoutField/child Group` e `XsdElement.parent_element_id` retornam
filhos **diretos**. Busca de atributos verifica valor persistido antes de
selecionar a unidade. Depois entram hits FTS no escopo; empates usam path
estável. `top_k` limita o máximo: não há preenchimento com ruído externo.

O texto da projection v3 rotula valores estruturados para busca lexical. A CLI
exibe, porém, conteúdo estrutural renderizado da unidade citável, após validar
`CorpusBuildCitationTarget`; não apresenta rótulos artificiais como se fossem
trechos oficiais. A navegação seleciona evidência, mas não cria fatos ou
`CitationTarget` sintéticos. `retrieval`, `EvidenceUnit` e `CitationTarget`
continuam objetos distintos.

Tipos XSD compartilhados são evidência complementar somente quando há cadeia
de tipo demonstrável. O materializer atual não persiste filhos de complex types
compartilhados nem o mapa de prefixos QName necessário para provar toda ligação;
nesses casos o retrieval não inventa filhos. A relação pai/filho diretamente
materializada no schema de evento é suportada sem mudança de parser.

Não há fine-tuning, embeddings, busca vetorial, reranker, LLM judge ou query
rewriting por LLM. A opção cross-source é somente coleta de evidências por
família, com `AVAILABLE`/`NO_AUTHORIZED_EVIDENCE`; não executa synthesis Complete.
