# Identidade e citações

Uma citação é identificada por versão documental e path local estável. Em termos
conceituais: `CitationIdentity = DocumentVersion + SourceLocalStablePath`.
O path completo é necessário porque um nome técnico sozinho pode se repetir em
ramos e eventos distintos.

Por exemplo, `LAYOUT/S-1000/ideEmpregador/nrInsc` identifica uma origem de forma
mais precisa que apenas `nrInsc`. Posição de página, linha ou ordem de extração
não integra a identidade estável.

`CitationTarget` é distinto de `CanonicalEntity`: o primeiro aponta para uma
origem citável; o segundo permite identidade transversal quando ela pode ser
resolvida deterministicamente.
