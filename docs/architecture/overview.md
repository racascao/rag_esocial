# Visão arquitetural

O sistema preserva o caminho da fonte até a experiência de consulta. Dados
derivados pertencem a um `CorpusBuild`; o runtime aponta atomicamente para um
build e uma projection prontos.

```mermaid
flowchart TD
    A[DocumentArtifact] --> B[DocumentVersion]
    B --> C[CorpusSnapshot congelado]
    C --> D[CorpusBuild]
    D --> E[MOS / Leiaute / XSD]
    E --> F[CitationTarget]
    F --> G[SourceFact e relações]
    D --> H[SearchProjection]
    H --> I[Retrieval]
    I --> J[EvidenceUnit autorizado]
    G --> J
    J --> K[CLI de evidências / Answer Contract]
```

Consulte [ingestão](ingestion.md), [versionamento](versioning.md) e
[runtime](runtime.md) para os contratos de cada etapa.

A CLI operacional do MVP apresenta diretamente a evidência autorizada ou a
abstenção. O Answer Contract representa a infraestrutura avançada de geração
fundamentada, separada desse fluxo público.
