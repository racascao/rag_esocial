# Corpus snapshot manifest v1

O snapshot é uma composição de `SnapshotMember[]`; não há colunas fixas por família. `ArtifactRole` é separado de `DocumentFamily`, portanto Anexos MOS e Leiaute nunca são identificados apenas por “Anexo I/II”. O identificador inicial é neutro: `esocial-s1.3-snapshot-001`.

Anexos I/II do Leiaute não recebem `DocumentVersion` independente por presunção: a aquisição registra a publicação física encontrada e permite que papéis distintos apontem para a mesma versão lógica. O hash do Leiaute é o SHA-256 do payload bruto capturado; extração pertence ao futuro `CorpusBuild`. Anexo I é a fonte canônica das tabelas `Tabela N` e Anexo II das regras `REGRA_*`, sem presumir faixas antes de inspeção.

O XSD preserva o hash do ZIP e o inventário de membros por caminho relativo e hash próprio. O `manifest_sha256` é SHA-256 de JSON canônico ordenado da composição, sem timestamps voláteis.

