# Fase 9D — CLI pública do Complete Mode

A Fase 9D expõe a orquestração Complete como uma camada CLI sobre os serviços
9A, 9B e 9C. A entrada é um plano JSON estruturado; não há decomposição de
perguntas por LLM.

## Comandos

```bash
esocial complete generate --build BUILD_ID_O_DIGEST --input complete.json
esocial complete show --run RUN_KEY
```

`generate` cria um novo `CompleteAnswerRun`. O `CompleteAnswerRequest` é
idempotente para o mesmo plano canônico, build e configuração, enquanto cada
execução mantém seu próprio run e seus próprios vínculos de source.

`show` apenas lê o ledger persistido. Ele pode ser executado em uma nova sessão,
não chama Ollama, não reagrega o contexto e não altera projeções, evidências,
fontes ou configurações.

## Entrada estruturada

Exemplo mínimo:

```json
{
  "question": "Como o aspecto é representado nas fontes?",
  "aspects": [
    {
      "aspect_key": "event.concept",
      "subject_kind": "EVENT",
      "subject_key": "S-9999",
      "source_inputs": [
        {
          "source": "MOS",
          "requested_fact_id": "REQUESTED_FACT_ID",
          "profile": "MOS_EVENT_SECTION",
          "query": "S-9999",
          "top_k": 5
        }
      ]
    }
  ]
}
```

`requested_fact_id` aceita o ID persistido de `RequestedFact`; por
compatibilidade também aceita um ID de `FactResolution` já existente. A fonte
deve ser `MOS`, `LAYOUT` ou `XSD`, e o perfil deve pertencer à mesma família.
As relações de identidade, build, proveniência e suporte continuam sendo
validadas pelos serviços determinísticos existentes.

## Estados

O resultado público preserva os estados `ANSWERED`, `PARTIAL`, `ABSTAINED`,
`MODEL_ERROR` e `VALIDATION_FAILED`. Quando nenhum fato autorizado é resolvido,
o pipeline abstém-se e não faz chamada de geração. Falhas ou limitações de uma
fonte permanecem como metadata; não são convertidas em fatos.

As claims finais e citações são persistidas no ledger Complete com referências a
`FactResolution`, `EvidenceUnit` e `CrossSourceComparison`. Respostas
single-source intermediárias não são usadas como evidência da síntese.

## Verificação

A implementação não cria migration nova: o head continua
`0014_complete_synthesis`. A validação inclui suíte PostgreSQL, nova sessão,
idempotência, múltiplos runs, rollback, B1/B2, imutabilidade upstream e CLI
registrada. Benchmark Complete e execução live em lote permanecem fora desta
fase.
