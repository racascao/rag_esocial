# Evidence-first

Em um domínio normativo e técnico, encontrar texto semelhante não basta. O
rag_esocial separa a recuperação do que pode realmente sustentar uma afirmação:

```text
SearchUnit != EvidenceUnit != CitationTarget
retrieval != evidence
evidence != generation
```

`SearchUnit` é uma unidade indexada para busca. `CitationTarget` representa uma
origem estável e citável. `EvidenceUnit` é o vínculo autorizado usado na cadeia
de evidência. A evidência precisa pertencer ao build consultado, ter identidade
de fonte e satisfazer a política do contrato em uso. Quando há geração, o LLM só
atua depois da construção e autorização da evidência; ele não é fonte factual nem
decide essa autorização.

```text
pergunta → retrieval → evidência autorizada → geração → validação → renderização
```

O menu operacional do MVP termina em evidência autorizada, apresentação ou
abstenção. A etapa posterior é usada pela infraestrutura de geração fundamentada
do projeto, não pela consulta pública normal.

!!! important
    Sem evidência autorizada, o resultado é abstenção. Um modelo não recebe
    permissão para completar o fato com memória paramétrica.

Leia também [evidence assembly](../evidence_assembly.md).
