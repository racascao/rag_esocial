# Instruções permanentes

- Não instalar dependências Python no host; executar build, testes, lint e migrations em containers.
- O produto é CLI-first: não criar frontend, API HTTP ou servidor web.
- Não implementar fine-tuning, LoRA ou treinamento do modelo.
- Não criar lógica especial para perguntas individuais nem hardcode de casos DEV.
- Não escolher embedding, reranker ou chunking sem fase e medição correspondentes.
- Futuras respostas devem ser exclusivamente baseadas em evidência autorizada.
- Preservar proveniência e auditabilidade.
- Atualizar README ao fim de fases que alterem estado, funcionalidades ou roadmap.
- Não fazer commit, push ou tag.
- `CorpusSnapshot` é diferente de `CorpusBuild`; build real exige snapshot congelado.
- `CitationTarget` é diferente de `CanonicalEntity`; CitationIdentity não inclui build ou snapshot.
- Nunca usar página, linha ou índice posicional como identidade estável de citação.
- Apresentação humana não faz parte da identidade estável.
- Reutilizar o único `SNAPSHOT_MEMBERSHIP_VALIDITY`; não duplicar o predicado.
- `SearchProjection` não pertence ao `CorpusBuild`; não antecipar parser ou retrieval.
