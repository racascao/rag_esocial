# Invariantes arquiteturais

- Retrieval não é evidência; `EvidenceUnit`, `SearchUnit` e `CitationTarget` são distintos.
- Sem evidência autorizada, há abstenção.
- `CorpusSnapshot` congelado é imutável.
- Parser revision é diferente de search revision.
- Falha de atualização preserva o runtime anterior.
- Autoridade da fonte depende do tipo de afirmação.
- Não há fallback factual para memória paramétrica do modelo.
- Testes não podem alterar produção; usam `esocial_test`.
- Referências determinísticas exatas têm precedência sobre resolução vaga.
