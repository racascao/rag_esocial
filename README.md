
# RAG eSocial

> Assistente local, auditável e baseado em evidências para consulta à documentação oficial do eSocial.

O **RAG eSocial** é um projeto CLI-first para consulta estruturada a documentos oficiais do eSocial, com foco em **rastreabilidade, provenance, versionamento de corpus, resolução determinística de fatos, evidências autorizadas e respostas verificáveis**.

O projeto trabalha atualmente com três famílias documentais:

- **MOS** — Manual de Orientação do eSocial;
- **Leiautes** — estrutura formal de eventos, grupos, campos, regras e referências;
- **XSD** — schemas XML e suas restrições estruturais.

Diferentemente de um chatbot convencional, o modelo de linguagem **não é tratado como fonte de conhecimento**. O LLM só pode gerar respostas a partir de fatos previamente resolvidos e evidências explicitamente autorizadas pelo pipeline.

Se não houver suporte suficiente:

> **o sistema se abstém antes de consultar o modelo.**

---

## Por que este projeto é diferente?

O RAG eSocial foi projetado para cenários em que uma resposta plausível não é suficiente: é necessário saber **de onde ela veio, qual versão documental a sustenta e quais fatos foram realmente autorizados para geração**.

### Evidence-first

O pipeline separa explicitamente:

```text
retrieval
    !=
evidence
    !=
fact resolution
    !=
generation
    !=
validation
```

Um resultado encontrado pela busca não se torna automaticamente evidência.

Uma evidência encontrada também não autoriza automaticamente qualquer afirmação.

---

### O modelo nunca é a fonte

O `gemma4:12b` é usado exclusivamente como **gerador controlado**.

O pipeline segue o princípio:

```text
model != source
```

O modelo não pode:

* completar lacunas com conhecimento paramétrico;
* inventar fatos;
* inventar referências;
* usar informação externa ao contexto autorizado;
* substituir evidence ausente;
* transformar interpretação em fato persistido.

---

### Abstention antes do LLM

Se nenhum fato autorizado puder ser resolvido:

```text
0 fatos RESOLVED
        ↓
ABSTAINED
        ↓
0 chamadas ao modelo
```

Isso reduz o risco de respostas convincentes, porém não sustentadas pela documentação carregada no corpus.

---

### Provenance ponta a ponta

Uma afirmação autorizada pode ser rastreada até sua origem documental:

```text
AnswerClaim
    ↓
FactResolution
    ↓
FactResolutionSupport
    ↓
EvidenceUnit
    ↓
CitationTarget
    ↓
DocumentVersion / artefato oficial
```

A resposta não precisa ser aceita "porque o modelo disse".

O objetivo é permitir que ela seja **auditada**.

---

### Corpus versionado e builds reproduzíveis

O corpus é tratado como um conjunto versionado de artefatos.

O projeto distingue:

```text
DocumentVersion
DocumentArtifact
CorpusSnapshot
CorpusBuild
CitationTarget
CanonicalEntity
```

Cada build possui identidade própria.

Isso permite comparar execuções sem misturar silenciosamente documentos ou estados diferentes do corpus.

---

### Identidade estável

Citações e entidades não dependem apenas de IDs internos do banco.

O projeto utiliza identidade documental estável para permitir:

* reprocessamento;
* builds distintos do mesmo snapshot;
* comparação B1/B2;
* provenance reproduzível;
* avaliação independente de PKs de banco.

---

### Resolução determinística antes da geração

A etapa de geração não recebe diretamente textos arbitrários recuperados pela busca.

Antes dela existem:

```text
RequestedFact
    ↓
FactResolution
    ↓
RuntimeStatus
    ↓
FactResolutionSupport
```

Entre os estados suportados estão:

```text
RESOLVED
SOURCE_NOT_APPLICABLE
ASPECT_NOT_COVERED
NO_RELEVANT_EVIDENCE
UNSUPPORTED
```

Somente fatos `RESOLVED` com suporte autorizado podem entrar no contexto factual do modelo.

---

### Answer Contract estruturado

Na Fase 8 foi implementado um contrato explícito entre aplicação e LLM.

O modelo produz um ledger estruturado de claims, conceitualmente:

```json
{
  "claims": [
    {
      "claim_id": "C1",
      "text": "...",
      "fact_refs": ["F1"],
      "evidence_refs": ["E1"]
    }
  ]
}
```

A saída do modelo é então validada deterministicamente.

O validator verifica, entre outros pontos:

* referências de fatos;
* referências de evidências;
* membership;
* build;
* source;
* status `RESOLVED`;
* support chain;
* referências desconhecidas;
* citações não autorizadas.

Validação de citação significa:

> **a evidência pertence ao suporte autorizado daquela claim.**

Isso não é confundido com julgamento automático de correção jurídica ou semântica.

---

### Complete Mode preserva o contrato single-source

A Fase 9 introduz o **Complete Mode**, mas sem desmontar o que já foi provado na Fase 8.

`AnswerRequest` e `AnswerRun` continuam estritamente **single-source**.

A camada Complete é aditiva e possui identidade própria para orquestrar:

```text
MOS
 +
Leiaute
 +
XSD
```

A subfase 9A já implementa:

* identidade build-specific;
* requests idempotentes;
* múltiplos runs;
* plano por source;
* RequestedAspects;
* vínculos com novos `AnswerRun` single-source;
* proteção contra mistura de builds;
* lifecycle estrutural;
* rollback;
* B1/B2.

A agregação factual cross-source da **Fase 9B** está implementada com
`CrossSourceComparison`/`CrossSourceComparisonMember`, refs `MOS:F*`/`E*` e
contexto canônico derivado somente de fatos resolvidos e suportes autorizados.
Não há precedência silenciosa entre fontes.

A synthesis cross-source interna da **Fase 9C** está implementada com contexto
fechado, validator determinístico, claim ledger e renderer. A CLI Complete
pública da **Fase 9D** compõe esses serviços sem duplicar retrieval ou síntese.

---

# Arquitetura em alto nível

```text
                    ┌──────────────────────┐
                    │ Documentos oficiais  │
                    │ MOS / Leiaute / XSD  │
                    └──────────┬───────────┘
                               │
                               ▼
                    ┌──────────────────────┐
                    │ Versionamento        │
                    │ + Corpus Snapshot    │
                    └──────────┬───────────┘
                               │
                               ▼
                    ┌──────────────────────┐
                    │ CorpusBuild          │
                    │ + parsing estrutural │
                    └──────────┬───────────┘
                               │
                               ▼
                    ┌──────────────────────┐
                    │ SourceFacts          │
                    │ + relações D1/D2/D3  │
                    └──────────┬───────────┘
                               │
                               ▼
                    ┌──────────────────────┐
                    │ SearchProjection     │
                    │ PostgreSQL FTS       │
                    └──────────┬───────────┘
                               │
                               ▼
                    ┌──────────────────────┐
                    │ Retrieval            │
                    └──────────┬───────────┘
                               │
                               ▼
                    ┌──────────────────────┐
                    │ Evidence Assembly    │
                    └──────────┬───────────┘
                               │
                               ▼
                    ┌──────────────────────┐
                    │ Fact Resolution      │
                    │ RequestedFact        │
                    │ FactResolution       │
                    └──────────┬───────────┘
                               │
                               ▼
                    ┌──────────────────────┐
                    │ Answer Contract v1   │
                    │ single-source        │
                    └──────────┬───────────┘
                               │
                               ▼
                    ┌──────────────────────┐
                    │ gemma4:12b / Ollama │
                    └──────────┬───────────┘
                               │
                               ▼
                    ┌──────────────────────┐
                    │ Claim validation     │
                    │ + renderer           │
                    └──────────────────────┘
```

O Complete Mode adiciona uma camada acima das execuções single-source:

```text
CompleteAnswerRequest
        │
        ├── MOS    → AnswerRequest → AnswerRun
        ├── Layout → AnswerRequest → AnswerRun
        └── XSD    → AnswerRequest → AnswerRun
```

A 9A implementa essa infraestrutura de orquestração.

A 9B agrega deterministicamente facts/evidence por aspecto, preserva cobertura
negativa e divergência, e persiste as comparisons no mesmo `CompleteAnswerRun`.
Synthesis continua fora do escopo.

---

# Stack

## Aplicação

* Python
* `uv`
* Typer
* Rich
* Pydantic
* SQLAlchemy
* Alembic
* pytest
* Ruff

## Persistência

* PostgreSQL
* imagem preparada para `pgvector`

O projeto ainda utiliza **retrieval lexical via PostgreSQL FTS**.

Embeddings e vector retrieval não fazem parte do pipeline atual.

## LLM

* Ollama containerizado
* modelo fixo: `gemma4:12b`

Não é necessário instalar Ollama ou Python no host.

---

# Pré-requisitos

No host são necessários apenas:

* Docker;
* Docker Compose;
* Git.

Verifique:

```sh
docker --version
docker compose version
git --version
```

Python, PostgreSQL, Ollama e dependências do projeto são executados em containers.

---

# Subindo o projeto

## 1. Clone o repositório

```sh
git clone <URL_DO_REPOSITORIO>
cd rag_esocial
```

---

## 2. Build dos containers

```sh
docker compose build
```

---

## 3. Suba aplicação e banco

```sh
docker compose up -d
```

Verifique os containers:

```sh
docker compose ps
```

---

## 4. Verifique a CLI

```sh
docker compose exec app uv run esocial --version
```

Para visualizar os comandos disponíveis:

```sh
docker compose exec app uv run esocial --help
```

---

# Banco de dados

## Verificar estado

```sh
docker compose exec app uv run esocial db status
```

## Aplicar migrations

```sh
docker compose exec app uv run alembic upgrade head
```

## Ver migration atual

```sh
docker compose exec app uv run alembic current
```

## Ver heads

```sh
docker compose exec app uv run alembic heads
```

O head atual do projeto é:

```text
0013_cross_source_aggregation
```

---

# Inicializando o corpus

Inicialize a infraestrutura local:

```sh
docker compose exec app uv run esocial corpus init
```

Consulte o estado:

```sh
docker compose exec app uv run esocial corpus status
```

Verifique integridade:

```sh
docker compose exec app uv run esocial corpus verify
```

---

# Importando documentos oficiais

A aquisição de documentos é deliberadamente explícita no estágio atual.

O projeto **não faz download ou scraping automático de documentos oficiais**.

Isso evita que o corpus mude silenciosamente entre execuções.

Para importar um artefato previamente obtido e autorizado:

```sh
docker compose exec app uv run esocial corpus artifact import \
  --role <ROLE> \
  --file <ARQUIVO> \
  --official-url <URL_OFICIAL> \
  --version-label <VERSAO> \
  --title <TITULO> \
  --family <FAMILIA>
```

Exemplo de famílias:

```text
MOS
LAYOUT
XSD
```

Consulte a ajuda do comando antes da importação:

```sh
docker compose exec app uv run esocial corpus artifact import --help
```

O conteúdo físico do corpus fica no volume:

```text
corpus_data
```

Esse volume não é versionado no Git.

---

# Ollama e gemma4

O serviço do Ollama usa o profile:

```text
llm
```

Suba-o com:

```sh
docker compose --profile llm up -d
```

Verifique o estado pela própria aplicação:

```sh
docker compose exec app uv run esocial llm status
```

Configuração padrão:

```text
Provider: Ollama
Model: gemma4:12b
Internal URL: http://ollama:11434
Diagnostic host port: 11436
```

A porta do host pode ser alterada por:

```sh
ESOCIAL_OLLAMA_HOST_PORT
```

Exemplo:

```sh
ESOCIAL_OLLAMA_HOST_PORT=11437 docker compose --profile llm up -d
```

A aplicação continua utilizando internamente:

```text
http://ollama:11434
```

---

# Executando uma resposta single-source

A Fase 8 disponibiliza os comandos:

```text
esocial answer generate
esocial answer show
```

Consulte o contrato exato da CLI instalada:

```sh
docker compose exec app uv run esocial answer generate --help
```

```sh
docker compose exec app uv run esocial answer show --help
```

O fluxo single-source é:

```text
Question
   ↓
RequestedFacts
   ↓
Retrieval
   ↓
Evidence Assembly
   ↓
Fact Resolution
   ↓
Preflight
   ↓
gemma4:12b
   ↓
Structured Claims
   ↓
Deterministic Validation
   ↓
Renderer
```

Se nenhum fato autorizado estiver resolvido, o fluxo termina em:

```text
ABSTAINED
```

sem realizar chamada ao Ollama.

---

# Inspecionando o LLM

```sh
docker compose exec app uv run esocial llm status
```

Esse comando é apenas diagnóstico.

Ele não realiza consulta factual.

---

# Executando o Q14

O benchmark single-source congelado da Fase 8 está em:

```text
evaluation/q14/q14_v1.json
```

SHA-256 canônico:

```text
30dad081fde8b59f448bd8675fdfa298c22c8d2da5dddf9ba7f30e3e8796e3c7
```

Ele contém:

```text
14 casos

8 ANSWERED
3 PARTIAL
3 ABSTAINED
```

Distribuídos entre:

```text
MOS
LAYOUT
XSD
```

Para consultar a CLI:

```sh
docker compose exec app uv run esocial eval q14 --help
```

O benchmark não faz auto-tuning de:

* modelo;
* prompt;
* `top_k`;
* retrieval;
* evidence budget;
* resolução factual.

Os reports da Fase 8 ficam em:

```text
evaluation/q14/
```

Entre eles:

```text
q14_v1_fake_report.json
q14_v1_live_smoke_report.json
q14_v1_live_report.json
q14_v1_human_review_template.json
```

O template de revisão humana permanece separado das métricas automáticas.

---

# Executando os testes

Execute toda a suíte:

```sh
docker compose exec app uv run pytest
```

Estado validado após a Fase 9A:

```text
56 passed
0 skipped
0 xfailed
```

---

# Qualidade de código

## Ruff

```sh
docker compose exec app uv run ruff check .
```

```sh
docker compose exec app uv run ruff format --check .
```

---

# Testando migrations

Para validar o ciclo de migrations:

```sh
docker compose exec app uv run alembic upgrade head
```

Na Fase 9A, o downgrade específico pode ser validado com:

```sh
docker compose exec app uv run alembic downgrade 0011_answer_contract
```

Depois:

```sh
docker compose exec app uv run alembic upgrade head
```

E confirme:

```sh
docker compose exec app uv run alembic current
```

Esperado:

```text
0013_cross_source_aggregation
```

---

# Desenvolvimento

## Abrir shell no container

```sh
docker compose exec app bash
```

Dentro dele:

```sh
uv run esocial --help
uv run pytest
uv run ruff check .
```

Não instale dependências Python diretamente no host.

---

# Estrutura conceitual do projeto

```text
rag_esocial/
├── rag_esocial/
│   ├── models/
│   ├── answer_service.py
│   ├── complete_answer_service.py
│   └── ...
│
├── migrations/
│   └── versions/
│
├── tests/
│
├── docs/
│
├── evaluation/
│   └── q14/
│
├── docker-compose.yml
├── pyproject.toml
├── README.md
└── AGENTS.md
```

A organização exata pode evoluir, mas a separação arquitetural permanece entre:

```text
corpus
parsing
facts
search
evidence
resolution
answering
complete-mode orchestration
evaluation
```

---

# Estado atual

## Fases concluídas

### Fase 0 — Bootstrap

Infraestrutura inicial:

* Python/uv;
* Typer + Rich;
* SQLAlchemy;
* Alembic;
* PostgreSQL;
* Docker;
* testes;
* lint.

### Fase 1 — Acquisition e versionamento

Introduziu:

* `DocumentVersion`;
* `DocumentArtifact`;
* `ArchiveMember`;
* `CorpusSnapshot`;
* `SnapshotMember`;
* hashes;
* manifest;
* freeze/verify.

### Fase 2 — CorpusBuild e identidade

Introduziu:

* `CorpusBuild`;
* `CitationTarget`;
* `CanonicalEntity`;
* identidade e digests de build.

### Fase 3 — Parsing estrutural

Implementados parsers para:

* MOS;
* Leiaute;
* XSD.

### Fase 4 — Fatos e relações determinísticas

Introduziu:

* `SourceFact`;
* `ReferenceResolution`;
* `EntityRelation`;
* `ResolvedFact`.

### Fase 5 — SearchProjection / FTS

Introduziu:

* `SearchProjection`;
* `SearchUnit`;
* PostgreSQL FTS;
* ranking lexical;
* índices GIN.

### Fase 6 — Retrieval e Evidence Assembly

Introduziu:

* `EvidenceSet`;
* `EvidenceUnit`;
* retrieval explícito;
* avaliação DEV.

### Fase 7 — RequestedFact e Fact Resolution

Introduziu:

* `RequestedFact`;
* `FactResolution`;
* `FactResolutionSupport`;
* runtime statuses;
* resolução factual determinística por source.

### Fase 8 — Answer Contract

**COMPLETE**

Implementa:

* `AnswerRequest`;
* `AnswerRun`;
* `AnswerClaim`;
* `AnswerClaimFact`;
* `AnswerCitation`;
* allowlists F*/E*;
* preflight;
* structured claim ledger;
* validator determinístico;
* renderer determinístico;
* Ollama;
* `gemma4:12b`;
* Q14 fake/live;
* CLI de answer/evaluation.

### Fase 9A — Complete Mode: persistência e orquestração

**COMPLETE**

Implementa:

* `CompleteAnswerRequest`;
* `CompleteAnswerRequestSource`;
* `CompleteAnswerRequestedAspect`;
* `CompleteAnswerSourceInput`;
* `CompleteAnswerRun`;
* `CompleteAnswerSourceRun`;
* identidade build-specific;
* idempotência;
* múltiplos runs;
* source membership;
* proteção cross-build;
* lifecycle estrutural;
* rollback;
* B1/B2.

A camada Complete referencia os objetos single-source existentes sem alterar seu contrato.

---

# Roadmap

Estado atual:

```text
Fase 0   COMPLETE
Fase 1   COMPLETE
Fase 2   COMPLETE
Fase 3A  COMPLETE
Fase 3B  COMPLETE
Fase 3C  COMPLETE
Fase 4   COMPLETE
Fase 5   COMPLETE
Fase 6   COMPLETE
Fase 7   COMPLETE
Fase 8   COMPLETE
Fase 9A  COMPLETE
Fase 9B  COMPLETE
Fase 9C  COMPLETE
Fase 9D  COMPLETE
Fase 9E  PLANNED
Fase 10  PLANNED
```

## Fase 9B — agregação determinística cross-source

Implementada sem LLM, embeddings, fuzzy matching ou conversão semântica implícita.
O agregador alinha apenas `RequestedAspect`/`RequestedFact` compatíveis no mesmo
build, valida a cadeia `FactResolution → EvidenceSet → EvidenceUnit →
CitationTarget`, gera refs source-qualified e persiste comparações com ordem,
revision e digest determinísticos. `COMPLEMENTARY` e `DIFFERENT_ASPECT` exigem
relação declarada no plano; divergência fica preservada como metadata.

A camada 9B alinha informações entre:

```text
MOS
Layout
XSD
```

sem usar LLM para decidir fatos. A CLI pública é responsabilidade da Fase 9D.

---

## Fase 9C — synthesis cross-source controlada por evidência

Implementada como API interna consumida pela CLI pública da Fase 9D:

> **cross-source synthesis**

O pipeline recebe somente facts/evidence autorizados pela 9B, preserva
divergências, não dá precedência a MOS/Layout/XSD, valida refs F/E/X e persiste
claims finais com links relacionais para `FactResolution`, `EvidenceUnit` e
`CrossSourceComparison`. Respostas intermediárias nunca são evidence.

A synthesis continua sujeita aos mesmos princípios:

* fatos resolvidos;
* evidence autorizada;
* provenance;
* validação determinística;
* ausência de fallback paramétrico.

## Fase 9D — CLI pública e orquestração ponta a ponta

**COMPLETE**

Os comandos públicos são:

```bash
esocial complete generate --build BUILD_ID_O_DIGEST --input complete.json
esocial complete show --run RUN_KEY
```

`generate` recebe somente um plano JSON estruturado e compõe as pipelines
single-source, a agregação 9B e a síntese 9C. O request é idempotente e cada
execução cria um novo run. `show` é read-only, funciona em nova sessão e não
chama o provider. O contrato detalhado e o exemplo de entrada estão em
`docs/phase9_complete_mode_cli.md`.

O resultado preserva `ANSWERED`, `PARTIAL`, `ABSTAINED`, `MODEL_ERROR` e
`VALIDATION_FAILED`, com claims, facts, citations, comparisons e limitações
persistidos com proveniência. Não houve migration nova; o head permanece
`0014_complete_synthesis`.

---

# Funcionalidades deliberadamente ainda não implementadas

Atualmente o projeto **não possui**:

* embeddings;
* vector retrieval em produção;
* reranker;
* question decomposition por LLM;
* query expansion;
* auto-tuning;
* aquisição automática de documentos oficiais;
* frontend;
* API HTTP;
* fine-tuning;
* LoRA/QLoRA.

Essas ausências são intencionais.

O projeto prioriza primeiro:

```text
correção estrutural
auditabilidade
provenance
reprodutibilidade
evidence control
```

antes de adicionar técnicas probabilísticas mais complexas.

---

# Anexos do Leiaute

A infraestrutura já prevê papéis documentais para:

```text
LAYOUT_ANNEX_I_DOMAIN_TABLES
LAYOUT_ANNEX_II_VALIDATION_RULES
```

Porém esses anexos ainda não são parseados porque o formato físico oficial correspondente ainda não foi confirmado no corpus do projeto.

Também é importante distinguir:

```text
Leiaute Anexo II
    =
regras de validação

MOS Anexo II
    =
relação GFIP ↔ categorias eSocial
```

O projeto não trata ambos simplesmente como "Anexo II".

---

# Segurança arquitetural contra respostas não suportadas

O pipeline foi desenhado para impedir explicitamente alguns atalhos comuns em aplicações RAG:

```text
Search result
    ≠
Evidence

Evidence
    ≠
Authorized fact

Generated claim
    ≠
Source fact

Intermediate answer
    ≠
Evidence

Citation membership
    ≠
Semantic correctness
```

Essas distinções são parte central da arquitetura, não apenas convenções de implementação.

---

# Filosofia do projeto

O objetivo do RAG eSocial não é maximizar a quantidade de respostas produzidas.

O objetivo é maximizar a capacidade de responder:

> **"Por que o sistema afirmou isso e qual evidência autorizada sustenta essa afirmação?"**

Quando essa pergunta não pode ser respondida de forma satisfatória, o comportamento esperado é:

```text
ABSTAIN
```

e não completar a lacuna com conhecimento paramétrico.

---

# Aviso

O projeto é uma ferramenta técnica para consulta e análise da documentação carregada em seu corpus.

As respostas produzidas devem ser interpretadas juntamente com suas evidências e citações e não substituem a verificação das fontes oficiais aplicáveis ao caso concreto.
