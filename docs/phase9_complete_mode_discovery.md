# Fase 9 — descoberta do Complete Mode e síntese cross-source

> Registro histórico: esta descoberta foi aprovada e sua camada de persistência e
> orquestração foi implementada na subfase 9A pela migration
> `0012_complete_answer`. Agregação e synthesis permanecem fora da 9A.

## Escopo e baseline

Esta descoberta é exclusivamente arquitetural. Nenhum model, migration, service,
comando CLI, fixture, benchmark ou prompt de produção foi criado ou alterado.

- baseline inspecionado: commit `e3fb9b1856cd0d967b40db28621ff72494547cd7`
  (`e3fb9b1`);
- Alembic head existente: `0011_answer_contract`;
- Fase 8: `COMPLETE`, com 51 testes registrados no baseline;
- Q14 v1: congelado, canonical JSON SHA-256
  `30dad081fde8b59f448bd8675fdfa298c22c8d2da5dddf9ba7f30e3e8796e3c7`;
- provider/model existentes: Ollama / `gemma4:12b`;
- Fase 9: implementação `NOT_STARTED`.

O digest acima é o digest canônico calculado sobre o JSON normalizado e registrado
em `evaluation/q14/q14_v1.json.sha256`. Ele não deve ser confundido com o hash dos
bytes físicos do arquivo, que pode mudar com formatação sem mudar o dataset lógico.

## Artefatos e símbolos inspecionados

Foram inspecionados diretamente:

- `rag_esocial/models/corpus.py`: `CorpusSnapshot`, `SnapshotMember`,
  `DocumentArtifact`, `DocumentVersion`, `DocumentFamily`, `ArtifactRole`;
- `rag_esocial/models/build.py`: `CorpusBuild`, `CitationTarget`,
  `CorpusBuildCitationTarget`, `CanonicalEntity`;
- `rag_esocial/models/mos.py`, `layout.py` e `xsd.py`: estruturas materializadas
  e paths locais estáveis;
- `rag_esocial/models/facts.py`: `SourceFact`, `ResolvedFact`,
  `ReferenceResolution`, `EntityRelation`;
- `rag_esocial/models/search.py`: `SearchProjection`, `SearchUnit` e associação
  de targets;
- `rag_esocial/models/evidence.py`: `EvidenceSet`, `EvidenceUnit` e
  `EvidenceSetItem`;
- `rag_esocial/models/fact_resolution.py`: `RequestedFact`, `FactResolution`,
  `FactResolutionSupport` e `RuntimeStatus`;
- `rag_esocial/models/answer.py`: todo o modelo persistente da Fase 8;
- `rag_esocial/facts_service.py`, `search_service.py`, `evidence_service.py`,
  `fact_resolution_service.py` e `answer_service.py`;
- client Ollama, protocolo do model client, validator, renderer e comandos CLI da
  Fase 8;
- migrations `0001` a `0011_answer_contract`, com atenção especial a `0010` e
  `0011`;
- testes PostgreSQL de nova session, idempotência/múltiplos runs, rollback,
  B1/B2, upstream immutability, validator, retry e CLI;
- `evaluation/q14/q14_v1.json`, reports fake/live/smoke e human-review template;
- `docs/answer_contract.md`, `docs/evaluation_q14.md`,
  `docs/fact_resolution.md`, `docs/evidence_assembly.md`,
  `docs/deterministic_facts.md`, README, roadmap e `AGENTS.md`.

## Estado real da Fase 8

### Identidade e persistência

`AnswerRequest` é uma definição lógica, idempotente e estritamente single-source.
Ela contém `corpus_build_id` e `document_family` não nulos, pergunta e digest,
revisões de contrato/prompt, modelo, configuração e respectivos digests. A
constraint `UNIQUE(corpus_build_id, request_digest)` impede duplicar a mesma
definição dentro do build.

O `request_digest` produzido por `create_answer_request` inclui source, pergunta,
resoluções ordenadas, revisões, modelo e configuração. A associação
`AnswerRequestFactResolution` é ordenada e usa chave primária composta
`(answer_request_id, fact_resolution_id)`. O service rejeita resolução de outro
build ou de outra família antes de persistir o request.

Na implementação atual, os IDs persistentes das resoluções participam desse digest
interno. Isso não os expõe no contrato do modelo, mas não deve ser copiado como
identidade externa do Complete Mode; a identidade futura usa os request digests e
o plano canônico.

`AnswerRun` é execution-specific. Possui `run_key` aleatório e único, status,
provider/model/config, metadata do provider, número de tentativas, raw response,
resposta renderizada e validation summary. Múltiplos runs podem apontar para a
mesma definição `AnswerRequest`.

### Nullability e constraints relevantes

| Entidade/campo | Regra observada |
|---|---|
| `AnswerRequest.corpus_build_id` | não nulo, FK para `CorpusBuild` |
| `AnswerRequest.document_family` | não nulo; sem modo multi-source |
| pergunta, revisões, modelo e digests | não nulos |
| `AnswerRequestFactResolution.request_order` | não nulo |
| `AnswerRun.answer_request_id`, `run_key`, `status` | não nulos |
| provider/model/config/digest/attempt count | não nulos |
| `raw_response`, `rendered_answer` | anuláveis |
| `validation_summary` | não nulo |
| `AnswerClaim` key/order/text/hash/state | não nulos; key única por run |
| `AnswerClaimFact` | PK composta claim/resolution |
| `AnswerCitation` | PK composta claim/evidence/order |

As FKs de `0011_answer_contract` não possuem cascades implícitos. A migration não
contém checks cross-table para igualdade de build/source; essas provas pertencem
ao service e ao validator. O downgrade remove somente as tabelas da Fase 8, em
ordem inversa das dependências.

### Preflight, geração, validação e renderer

O preflight de `answer_service.py`:

1. carrega as resoluções associadas ao request na ordem registrada;
2. confirma build e source;
3. deixa passar como fatos apenas resoluções `RESOLVED`;
4. percorre `FactResolutionSupport` até `EvidenceUnit`;
5. confirma build/family da evidence, family da `CitationTarget`, membership da
   target no build e membership da evidence no `EvidenceSet` da resolução;
6. cria refs locais determinísticas `F1..Fn` e `E1..En`;
7. transforma os demais runtime statuses em limitations determinísticas.

O modelo recebe a pergunta, valores resolvidos e `EvidenceUnit.rendered_content`.
Ele não recebe `SearchUnit.search_text` como evidência. O validator exige schema
exato, limites, IDs válidos, ausência de duplicatas, allowlists F/E e pelo menos
uma evidence que suporte um fato citado. Ele prova membership e cadeia de suporte,
mas não prova entailment semântico nem correção jurídica.

O renderer só entra após validação. Ele ordena claims e citações, resolve a
apresentação humana pela `CitationTarget.human_label` ou pelo stable path e inclui
a família. A apresentação humana não participa da identidade estável.

### Status da Fase 8

- `ANSWERED`: há fatos resolvidos, output válido e nenhuma limitation negativa;
- `PARTIAL`: há pelo menos um fato resolvido e output válido, mas também há
  resoluções negativas, renderizadas como limitations;
- `ABSTAINED`: nenhum fato autorizado passou no preflight; resposta e limitations
  são determinísticas e o model client não é chamado;
- `MODEL_ERROR`: provider falhou ou o structured output continuou malformado após
  o único retry;
- `VALIDATION_FAILED`: JSON parseável não satisfaz o contrato/allowlists/support.

Somente `ANSWERED`, `PARTIAL` e `ABSTAINED` produzem resposta humana utilizável.
Outputs inválidos não são convertidos em resposta factual.

### Transação atual

`execute_answer_request` cria e faz flush do `AnswerRun`, executa preflight,
chama o provider quando aplicável, persiste claims/links/citations e renderiza. A
session e o commit pertencem ao caller. O CLI mantém a mesma transaction aberta
durante a chamada síncrona ao modelo e faz rollback em exceção. Isso é aceitável
no pipeline isolado atual, mas não deve ser multiplicado por quatro chamadas no
Complete Mode sem uma boundary explícita.

## Identidades e invariantes upstream

- `CorpusSnapshot` é distinto de `CorpusBuild`; build real exige snapshot
  congelado.
- `CorpusBuild` é build-specific e tem `build_digest` único.
- `CitationTarget` é estável e transversal a builds. Sua identidade combina versão,
  família e source-local stable path; página/linha/índice posicional não são usados.
- `CanonicalEntity` também é transversal, com stable key de kind + canonical key.
- `SourceFact`, `ResolvedFact`, `RequestedFact`, `FactResolution`, estruturas,
  search e evidence são build-specific.
- A unidade de resolução é `RequestedFact × DocumentFamily`.
- `FactResolutionSupport` é obrigatório para uma resolução `RESOLVED` alcançar um
  gerador.
- `SearchProjection` e `SearchUnit` são retrieval, não evidência.
- `EvidenceUnit` é materializada a partir da estrutura do build e aponta para uma
  `CitationTarget` autorizada.

`EvidenceSet` não possui uma coluna `document_family`; sua localidade decorre da
projection/profile e dos itens montados pelo service. `EvidenceUnit` possui family.
Assim, o agregador não pode inferir isolamento apenas da FK do set: deve validar a
family de cada unit, sua origem no set e o support correspondente.

As FKs do banco não conseguem, sozinhas, provar todas as igualdades transitivas de
build/source. Os services existentes fazem essas validações. A Fase 9 precisará
repetir e ampliar essas provas na boundary do agregador, sem confiar apenas nos
IDs recebidos.

## Capacidades reais por família

### MOS

Perfis: `MOS_EVENT_SECTION`, `MOS_TOPIC`, `MOS_SUBITEM`. Fatos observados são
principalmente metadata textual D2 de evento, como conceito e prazo. O MOS é
orientação/manual operacional textual; essa descrição não estabelece precedência.

### Leiaute

Perfis: `LAYOUT_EVENT`, `LAYOUT_GROUP`, `LAYOUT_FIELD`. Fatos D1 incluem descrição,
ocorrência, tipo, tamanho e condição de campos/grupos. O Leiaute representa a
estrutura formal presente no artefato adquirido.

### XSD

Perfis: `XSD_EVENT_SCHEMA`, `XSD_ELEMENT`, `XSD_SHARED_TYPE`. Fatos D1 incluem
`minOccurs`, `maxOccurs`, type QName e ref QName. O XSD representa constraints de
schema/XML; cardinalidade XML não deve ser promovida automaticamente a
obrigatoriedade funcional.

O registry atual é derivado dos `SourceFact` materializados. Logo, o mesmo texto
de query ou o mesmo profile não serve universalmente. Retrieval e evidence
assembly devem continuar source-local e explicitamente configurados.

## Alinhamento cross-source já disponível — e o que falta

O repositório oferece:

- `CanonicalEntity` para identidade transversal conhecida, por exemplo um evento;
- `EntityRelation` e `ReferenceResolution` D3 para relações determinísticas;
- `RequestedFact` com fact type, subject kind/key e qualifiers;
- `ResolvedFact` apenas para derivação lossless comprovada;
- stable paths locais e `CitationTarget` para origem citável.

Isso não constitui uma ontologia universal de aspectos. Fact types como
`EVENT_PRAZO_DE_ENVIO`, `LAYOUT_OCCURRENCE` e `XSD_MAX_OCCURS` não são
intercambiáveis. `CanonicalEntity` prova o sujeito quando disponível, não prova
que duas propriedades têm a mesma semântica. `EntityRelation` pode auxiliar
roteamento deterministicamente, mas não autoriza fuzzy matching nem interpretação
por LLM.

A lacuna real é um contrato explícito que diga quais RequestedFacts pertencem ao
mesmo aspecto solicitado. A recomendação é tornar esse agrupamento parte do input
estruturado do Complete Mode, e não inferi-lo da pergunta textual.

## Anexos e disponibilidade documental

`ArtifactRole` já prevê `LAYOUT_ANNEX_I_DOMAIN_TABLES` e
`LAYOUT_ANNEX_II_VALIDATION_RULES`, mas sua presença em um snapshot não é garantida.
Os estados de resolução da Fase 7 não distinguem “artefato esperado ausente” de
“artefato presente sem evidência relevante”. Essa diferença deve ser capturada por
um outcome de disponibilidade no plano/execução source da Fase 9, sem alterar os
runtime statuses históricos.

“Anexo II” não é identidade suficiente: o Anexo II do Leiaute trata de regras de
validação; o Anexo II do MOS é outro documento. Família, role, version e stable path
já permitem desambiguar e devem permanecer explícitos.

## Q14 e orçamento observado

O Q14 continua sendo um benchmark single-source e não deve ser reutilizado como
benchmark de síntese. O live report contém 14 casos: 8 `ANSWERED`, 3 `PARTIAL` e 3
`ABSTAINED`. Foram 11 model calls; os três abstentions tiveram zero calls. Nos calls
registrados, `prompt_eval_count` variou de 137 a 169 tokens, com soma 1.713, e
`eval_count` variou de 55 a 97, com soma 825. O `num_ctx` configurado é 8192 e
`num_predict` é 256.

Esses números provam apenas o tamanho das fixtures Q14. O report não persiste o
prompt bruto nem todas as EvidenceUnits, portanto não sustenta uma estimativa
honesta para o corpus oficial combinado. O risco de multiplicação é real: até três
contextos source-local mais fatos, comparisons, instruções e schema de synthesis.
Antes do benchmark live da Fase 9 serão necessários caps determinísticos por source,
contagem do prompt final e falha fechada quando o orçamento não couber. A descoberta
não altera `num_ctx`.

## Comparação de famílias arquiteturais

| Opção | Vantagens | Desvantagens e riscos | Veredito |
|---|---|---|---|
| A. adicionar mode ao `AnswerRequest/Run` | menos tabelas e aparente reuso | torna `document_family` insuficiente/nullable, mistura semântica de refs e status, fragiliza Q14/0011, eleva regressão e cria claims multi-build/source possíveis | rejeitada |
| B. agregador aditivo sobre requests/runs single-source | preserva F8, provenance e testes; separa identidade lógica de execução; permite claims finais multi-source validadas contra facts originais | exige migration/tabelas e validator próprios; orchestration mais explícita | recomendada |
| C. contrato cross-source totalmente independente | isolamento forte e liberdade de modelagem | duplicaria retrieval, evidence, resolution, retry, persistence e renderer; duas implementações poderiam divergir | rejeitada como duplicação |
| D. agregação efêmera, sem persistência | migration mínima | perde reprodutibilidade, vínculos source-run, comparison snapshot, rollback e auditoria | rejeitada |
| E. agregado aditivo, mas synthesis de rendered answers | implementação superficial | source laundering, perda da cadeia de suporte e propagação de hallucination | proibida |

A opção B reutiliza o pipeline single-source como unidade comprovada e cria um
segundo contrato somente para orchestration, comparison e final claims. Ela não
altera `AnswerRequest.document_family`, `AnswerRunStatus` nem `0011`.

Na opção A, a migration teria de alterar 0011 ou criar colunas discriminadoras nas
tabelas históricas. O validator passaria a ter dois significados para as mesmas refs
F/E, a identidade do request deixaria de ser naturalmente source-local, rollback
abrangeria registros heterogêneos e B1/B2 teria mais caminhos para mistura. É a
opção de maior risco de regressão para Q14 e para a CLI existente.

Na opção B, a futura 0012 só adiciona tabelas. O validator agregado é novo e chama
as mesmas provas source-local antes de acrescentar provas cross-source. Request e
run conservam a separação idempotente/execution-specific; rollback final não apaga
source runs válidos; B1/B2 é garantido no agregador e novamente em cada vínculo.
O custo é mais schema e orchestration, justificado por auditabilidade.

Na opção C, a migration também seria aditiva, mas o novo contrato precisaria
duplicar fact resolution, evidence allowlists, provider retry e persistência. A
idempotência teria duas implementações; rollback/B1B2 e validators teriam de ser
provados duas vezes. Mesmo sem regressão direta na Fase 8, o risco de divergência
semântica futura é alto.

Na opção D, nenhuma ou pouca migration seria necessária, mas não haveria identidade
idempotente, snapshot de comparison nem vínculo reproduzível a source runs. Rollback
seria impossível de distinguir de perda de processo e o gate B1/B2 dependeria só de
memória transitória. Ela não satisfaz os requisitos de provenance.

Na opção E, idempotência e migration não resolvem o defeito central: o validator só
conseguiria provar que um texto foi gerado por outro run, não que cada claim final
possui support documental. Rollback preservaria uma cadeia auditável de outputs,
mas não uma cadeia factual. Por isso ela é incompatível, não apenas arriscada.

## Entradas possíveis para o synthesizer

| Representação | Provenance/validação | Risco | Decisão recomendada |
|---|---|---|---|
| claims intermediárias | refs podem ser revalidadas, mas texto é probabilístico | hallucination e laundering | não entra em v1 |
| rendered answers | apresentação perde estrutura F/E | muito alto | proibido |
| `FactResolution` + `EvidenceUnit` autorizadas | cadeia completa e allowlist possível | repetição controlável | entrada factual canônica |
| facts/evidence + claims como “não autoritativas” | distinção pode ser ignorada pelo modelo | médio/alto sem ganho necessário | não entra em v1 |
| representação determinística derivada de facts/support/comparisons | auditável, compactável e preserva divergência | requer builder/validator | entrada recomendada |

**Pode entrar no modelo de synthesis:** pergunta, facts `RESOLVED`, conteúdos das
EvidenceUnits autorizadas por seus supports, outcomes/limitations determinísticos e
comparisons determinísticas, todos com refs source-qualified.

**Nunca pode entrar como evidência:** AnswerClaim intermediária, rendered answer,
raw model output, SearchUnit, interpretação do synthesizer ou conhecimento externo.

As respostas source-specific continuam necessárias pelo requisito de produto e
para auditoria humana, mas não são uma fonte factual para a synthesis.

## Gaps e riscos encontrados

1. Não existe entidade agregadora nem identidade cross-source.
2. Não existe agrupamento explícito de RequestedFacts por aspecto transversal.
3. Não existe comparison persistida/determinística entre facts source-specific.
4. As refs F/E atuais são locais e colidem entre runs.
5. A semântica de availability de artefato/source ainda não existe.
6. O model client atual fixa o schema da Fase 8; transporte pode ser reaproveitado,
   mas o protocolo de synthesis precisa de schema/revisões independentes.
7. A transaction da Fase 8 atravessa um model call; replicá-la em um agregado
   monolítico aumentaria locks, duração e custo de retry.
8. Não há cap agregado explícito de facts/evidence/chars/tokens.
9. O banco não prova por FK todas as invariantes cross-table de build/source.
10. Não existe política de precedência documental aprovada; inventá-la apagaria
    divergências válidas.

## Questões fechadas tecnicamente

- Entidade agregadora: necessária e aditiva.
- `AnswerRequest` single-source: permanece sem alteração.
- Source request: reutilizar definição idempotente; source run: sempre novo por
  Complete run.
- Input: pergunta mais RequestedAspects/RequestedFacts explicitamente estruturados
  por source; nenhuma decomposição NL nesta fase.
- Retrieval/evidence: um plano, projection e EvidenceSet source-local por input.
- Synthesis input: facts/evidence originais e metadata determinística; nunca texto
  intermediário como evidência.
- Refs: `MOS:F1`, `LAYOUT:F1`, `XSD:F1` e equivalentes E, sem DB PK exposta.
- Alignment: RequestedAspect explícito + canonical subject + relações D3 aprovadas.
- Divergence: metadata/comparison, não status de erro nem regra de precedência.
- All-abstained: zero source-generation calls, zero synthesis calls, Complete run
  persistido e resposta/limitations determinísticas.
- Uma única source útil: source generation permitida; synthesis LLM proibida;
  promoção determinística dos claims validados com revalidação dos links.
- Duas ou três sources fact-bearing: synthesis LLM permitida após preflight agregado.
- Claim final: links diretos a `FactResolution` e `EvidenceUnit`, nunca somente ao
  AnswerClaim intermediário.
- Build: único e obrigatório para request, sources, runs, facts, evidence e claims.
- B1/B2: agregados separados; `CitationTarget` e `CanonicalEntity` podem ser
  compartilhados.
- Migration futura: `0012`, somente aditiva; `0011` imutável.
- Q14 e CLI single-source: permanecem semanticamente idênticos.

## Decisões recomendadas que exigem aprovação

1. Adotar as entidades e os nomes canônicos detalhados no documento de arquitetura.
2. Adotar RequestedAspect explícito como unidade de alinhamento, fornecida pelo
   caller e versionada no request, sem decomposition por LLM.
3. Permitir que uma source com `MODEL_ERROR`/`VALIDATION_FAILED` não bloqueie a
   síntese quando os facts/evidence upstream foram independentemente validados;
   seu output inválido é excluído e o agregado fica `PARTIAL`.
4. Considerar `SOURCE_NOT_APPLICABLE` uma limitation informativa que não torna o
   agregado partial quando todas as obrigações aplicáveis foram resolvidas.
5. Persistir comparison determinística e seus membros, em vez de derivá-la apenas
   no momento de renderização.
6. Não fornecer claims/rendered answers intermediários ao synthesizer v1.
7. Usar transactions curtas por source e finalização atômica separada, permitindo
   que source runs válidos sobrevivam a falha posterior de synthesis.

## Questões genuinamente abertas

Somente valores de budget permanecem abertos: máximo de inputs, EvidenceUnits por
fact/source, caracteres e tokens por source e total. O código e o Q14 não fornecem
uma amostra representativa do corpus oficial combinado. A arquitetura define que os
limites serão explícitos, digestados e falharão fechados; os números devem ser
calibrados em uma medição read-only do corpus real antes do benchmark da subfase 9E.

Não há questão arquitetural que obrigue alterar o contrato single-source ou iniciar
question decomposition. A implementação pode começar depois da aprovação das sete
recomendações acima.
