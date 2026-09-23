# Evidência

Uma busca produz candidatos `SearchUnit`; ela não cria evidência por si só.
`EvidenceSet` organiza uma busca/configuração e `EvidenceUnit` aponta para
conteúdo autorizado, com `CitationTarget` associado ao build. A cadeia exige que
a origem exista no corpus ativo e permaneça citável.

Essa separação impede usar texto retornado pelo índice como prova implícita. A
montagem detalhada está em [evidence assembly](../evidence_assembly.md).
