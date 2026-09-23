# Ingestão

As entradas principais são MOS, pacote XSD e Leiaute principal. Cada artefato
tem URL oficial, hash, tipo de mídia, nome original, método de captura e caminho
de armazenamento em `DocumentArtifact`; ele pertence a uma `DocumentVersion`.

O Leiaute descobre Anexos I e II por links determinísticos da página principal.
A aquisição valida tipo físico e conteúdo antes da persistência. Um snapshot só
é congelado após validar os papéis obrigatórios. O pipeline não usa LLM nem OCR
automático para definir a estrutura.

Veja [manifest de snapshot](../corpus_snapshot_manifest_v1.md).
