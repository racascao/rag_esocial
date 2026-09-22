# UX operacional pós-MVP

O entrypoint externo é `./esocial`. O script não instala Python no host: ele
verifica Docker e Docker Compose, executa `docker compose up -d --build`,
aguarda o PostgreSQL, roda `uv run alembic upgrade head` dentro do container e
encaminha a sessão interativa para `esocial app` como `appuser`.

O runtime normal continua no database `esocial`. Em desenvolvimento, a suíte
PostgreSQL cria e migra automaticamente o database separado `esocial_test` e
recusa cleanup fora dele; seu corpus usa o volume `test_corpus_data`, separado
de `corpus_data`. O reset deliberado do runtime real permanece uma operação
posterior e manual.

## Máquina de estados

```text
SEM_CORPUS ──3 URLs──> DRAFT ──verify/freeze──> FROZEN
FROZEN ──build/parsers/facts/search──> READY ──ativação──> ACTIVE
ACTIVE ──N──> ACTIVE
ACTIVE ──S + 3 URLs──> novo DRAFT/FROZEN/READY ──sucesso──> novo ACTIVE
                                      └─falha──> ACTIVE anterior
```

Um snapshot congelado nunca é alterado. O serviço procura uma cadeia válida
existente antes de pedir URLs, ignora builds com parser revision não canônica e
retoma materializações ausentes por identidade determinística. A ativação
atômica grava uma única linha `runtime_key=default` em `active_runtimes`; a
versão anterior só é substituída depois de todas as etapas pré-computáveis.

## Onboarding e atualização

O usuário comum informa apenas URL do MOS, URL do XSD e URL da página principal
do Leiaute. A aquisição usa arquivos temporários, valida magic bytes/ZIP/HTML,
calcula SHA-256 e só então persiste os artefatos. Links para Anexo I e Anexo II
são resolvidos por HTML, URL relativa/absoluta e labels determinísticos. A
descoberta remove fragments (`#...`) antes de deduplicar URLs-base, preserva
queries legítimas e valida física e semanticamente cada documento destino;
falta ou ambiguidade encerra a tentativa sem adivinhação nem persistência.

Os defaults internos são versionados em `runtime_defaults.py`: parser
`parser-suite-v1`, busca `fts-baseline-v1` e profile padrão `LAYOUT_FIELD`.
Eles não aparecem como perguntas do onboarding.

Se os hashes já corresponderem a um snapshot congelado, a cadeia é reutilizada
e nenhuma nova versão é criada. Se forem diferentes, a nova cadeia preserva a
anterior. Downloads e parsing de uma atualização ocorrem fora de uma transação
longa; somente a troca final do runtime é uma transação curta.

## Diagnóstico

O menu mostra MOS, Leiaute, XSD, consulta, importação de nova versão e status.
Detalhes de UUID, manifest, build digest e parser revision continuam nos
comandos administrativos/diagnósticos, não no caminho normal.
