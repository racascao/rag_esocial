# Answer Contract v1

## Escopo e fronteira de confiança

A Fase 8 gera respostas para uma única `DocumentFamily` por `AnswerRequest`.
O modelo `gemma4:12b` é somente um gerador: não é fonte documental, não resolve
fatos e não pode complementar lacunas com conhecimento paramétrico. O contexto é
formado apenas por `FactResolution` com status `RESOLVED` e pelo
`EvidenceUnit.rendered_content` ligado por `FactResolutionSupport`.

O preflight valida build, fonte, associação do request, status da resolução,
membership do `EvidenceUnit` no `EvidenceSet`, membership do `CitationTarget` no
build e a cadeia de suporte. Em seguida cria allowlists locais `F1..Fn` e
`E1..En`. `SearchUnit.search_text` nunca é enviado ao modelo.

## Persistência e identidade

- `AnswerRequest` é build-specific e idempotente por build, fonte, pergunta,
  conjunto canônico de resoluções, revisões de contrato/prompt e configuração do
  modelo.
- Um request admite múltiplos `AnswerRun`, porque a geração é probabilística.
- `AnswerClaim` guarda a claim validada e seu SHA-256.
- `AnswerClaimFact` liga a claim à resolução autorizada.
- `AnswerCitation` liga a claim ao `EvidenceUnit`, em ordem determinística.

As revisões são `answer-contract-v1` e `answer-prompt-v1`. Parâmetros do modelo,
digest de configuração, resposta estruturada, tentativas rejeitadas, metadata do
provider e diagnóstico da validação ficam auditáveis no run/request.

## Contrato estruturado

O Ollama recebe JSON Schema nativo. A única raiz permitida é `claims`. Cada claim
possui exatamente `claim_id`, `text`, `fact_resolution_refs` e `evidence_refs`.
IDs de claim devem ser únicos; texto e listas não podem ser vazios; referências
não podem se repetir nem sair das allowlists. Há limites de 32 claims, 4.000
caracteres por claim e 32 referências de cada tipo por claim.

O validator também exige que cada evidência citada suporte ao menos uma das
resoluções citadas pela mesma claim. Qualquer claim inválida bloqueia o rendering
e produz `VALIDATION_FAILED`. Citation validation prova membership e cadeia de
suporte; ela não prova correção jurídica, entailment semântico ou completude.

O renderer não usa LLM. Ele concatena claims na ordem persistida, apresenta os
rótulos humanos dos `CitationTarget` e acrescenta limitações derivadas dos
`RuntimeStatus` negativos.

## Status e retry

- `ANSWERED`: todas as resoluções solicitadas estão resolvidas e o ledger é
  válido.
- `PARTIAL`: há resoluções válidas e também negativas; somente as válidas chegam
  ao modelo e as demais viram limitações determinísticas.
- `ABSTAINED`: não há fato resolvido com suporte; a resposta é determinística e
  o provider recebe zero chamadas.
- `MODEL_ERROR`: falha do runtime ou structured output ainda inválido após um
  único retry.
- `VALIDATION_FAILED`: JSON estruturado recebido, mas reprovado pelo validator.

Somente uma tentativa adicional é permitida para structured output sem a raiz
`claims`. Não há segundo modelo nem extrator de texto livre.

## Ollama e CLI

O Compose fornece o serviço `ollama` no profile `llm`, com volume persistente,
endpoint interno `http://ollama:11434` e porta diagnóstica configurável por
`ESOCIAL_OLLAMA_HOST_PORT` (default `11436`). O modelo fixo é `gemma4:12b`.

```sh
docker compose --profile llm up -d
docker compose exec app uv run esocial llm status
docker compose exec app uv run esocial answer generate \
  --build BUILD --source LAYOUT --question "..." --resolution RESOLUTION_ID
docker compose exec app uv run esocial answer show --run RUN_ID
```

Não há question decomposition, síntese cross-source, API HTTP, embeddings,
reranker ou fallback paramétrico nesta fase.
