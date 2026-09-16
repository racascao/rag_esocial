# SearchProjection e baseline FTS

`SearchProjection` é derivada de um `CorpusBuild`, mas não altera sua identidade. Cada perfil, revisão e configuração produz uma projeção independente; `SearchUnit` é específica da projeção e não é `CitationTarget` nem evidência.

Os nove perfis coexistem: MOS event section/topic/subitem, Leiaute event/group/field e XSD event schema/element/shared type. Cada unidade conserva o alvo citável raiz por associação de provenance.

O baseline usa PostgreSQL FTS `simple`, `tsvector`, GIN e `ts_rank_cd`, com desempate por path estável. Termos técnicos recebem normalização genérica preservando originais e formas sem hífen/prefixo. Texto de busca é derivado para retrieval e não é evidência autorizada.

Não há embedding, pgvector, reranker, EvidenceSet, answerer ou RAG nesta fase.

O harness PostgreSQL também prova rollback atômico da projeção e B1/B2: unidades
e projeções são específicas do build, enquanto os `CitationTarget` que as
originam permanecem transversais quando a identidade documental é a mesma.
