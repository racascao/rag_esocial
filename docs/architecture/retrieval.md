# Retrieval estrutural v3

`fts-baseline-v3` combina PostgreSQL Full Text Search com sinais estruturais.
A análise determinística reconhece S-XXXX, nomes técnicos existentes, famílias,
atributos e relações pai/filho. Escopo de evento e path precedem menções
textuais externas; empates usam identidade estável.

```mermaid
flowchart LR
    A[Pergunta] --> B[Query analysis]
    B --> C[Escopo de evento/path]
    C --> D[FTS e relações estruturais]
    D --> E[SearchUnit]
    E --> F[Evidência autorizada ou abstenção]
```

`top_k` é limite máximo, sem preenchimento artificial. O índice não usa
embeddings, similaridade vetorial, reranker neural, fine-tuning ou reescrita por
LLM. O `pgvector` da infraestrutura não participa do retrieval ativo.

O retrieval é a etapa de recuperação do desenho arquitetural. No menu operacional
atual, a evidência autorizada é apresentada diretamente, sem encaminhá-la para
geração por LLM.

Detalhes: [retrieval operacional v3](../operational_retrieval_v3.md).
