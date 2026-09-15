# CorpusBuild e identidade transversal

`CorpusSnapshot` representa fontes oficiais congeladas. `CorpusBuild` é uma materialização derivada e reproduzível, identificada por `manifest_sha256 + parser_revision + parser_config_digest`; ele só pode ser criado sobre snapshot congelado e verificado. Não contém `projection_version`, embeddings ou parâmetros de retrieval.

`CitationTarget` registra onde algo aparece: sua identidade estável é `DocumentVersion + DocumentFamily + source_local_stable_path`. Build, snapshot, label humano e locator físico não participam dela. `CanonicalEntity` registra sobre o que algo fala, com identidade `entity_kind + canonical_key`; não é versionada por `DocumentVersion`.

O predicado único `SNAPSHOT_MEMBERSHIP_VALIDITY` verifica se uma `DocumentVersion` pertence aos membros do snapshot. A associação build-alvo reutiliza esse validador. Não há grafo semântico, parser ou SearchProjection nesta fase.

