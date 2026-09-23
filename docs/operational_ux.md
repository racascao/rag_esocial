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
`parser-suite-v2`, busca `fts-baseline-v3` e profile padrão `LAYOUT_ALL`.
Eles não aparecem como perguntas do onboarding.

Se apenas a search revision está desatualizada, o launcher materializa
projections v3 no mesmo build e snapshot, sem parser, facts, HTTP ou novas URLs.
Uma parser revision diferente continua exigindo build novo. O runtime anterior
e sua geração permanecem intactos até o readiness integral; só então ocorre
troca atômica. Uma falha preserva o runtime anterior.

Se os hashes já corresponderem a um snapshot congelado, a cadeia é reutilizada
e nenhuma nova versão é criada. Se forem diferentes, a nova cadeia preserva a
anterior. Downloads e parsing de uma atualização ocorrem fora de uma transação
longa; somente a troca final do runtime é uma transação curta.

## Diagnóstico

O menu usa `MOS_ALL`, `LAYOUT_ALL` e `XSD_ALL` nas três escolhas de família.
A opção 4 mostra evidências cross-source, sem alegar execução do Answer Contract
Complete estruturado. Projeções granulares permanecem para diagnóstico e
benchmarks. Perguntas naturais são analisadas lexicalmente; escopo por evento,
identidade técnica, atributos e relações pai/filho precedem a menção textual.
O índice artificial não é exibido como se fosse conteúdo oficial. A camada
`presentation.py` formata o conteúdo estrutural autorizado em painéis Rich por
tipo de unidade, com atributos, fonte, path e score; ela não recupera nem
persiste evidência. A opção 4 mostra blocos separados para MOS, Leiaute e XSD,
incluindo ausência de evidência por fonte, sem conclusão artificial. Zero hits
produzem aviso de abstenção, não erro técnico. A abertura mostra apenas estado
e versões humanas; a opção **Status** separa visão geral, runtime e corpus,
incluindo IDs e revisões para diagnóstico. O conteúdo permanece legível sem cor
e em saída capturada. Detalhes adicionais de manifest e build digest continuam
nos comandos administrativos.
