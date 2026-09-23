# Runtime ativo

`ActiveRuntime` aponta para um `CorpusBuild` e uma `SearchProjection` prontos,
com uma geração crescente. A ativação ocorre após readiness; em falha de
atualização, a referência anterior continua ativa. Isso fornece rollback
operacional implícito sem alterar snapshots congelados.

O menu comum esconde IDs técnicos no cabeçalho, mas o Status os apresenta para
diagnóstico. A operação detalhada está em [ciclo de vida](../operations/lifecycle.md).
