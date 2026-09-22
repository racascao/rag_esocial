import pytest

from rag_esocial.mos_parser import (
    MosStructureError,
    NumericCandidate,
    NumericCandidateKind,
    classify_event_numeric_candidate,
    parse_mos_pages,
    parse_mos_text,
)
from rag_esocial.pdf_text import PdfPageText

TEXT = """CAP I
10. Tópico principal
10.3. Subtópico
10.3.4. Subitem profundo
CAP III
S-1200 Remuneração do trabalhador
Conceito
Texto sobre {ideDmDev} e S-1210.
Quem está obrigado
Empregadores.
Prazo de envio
Até o prazo aplicável.
Pré-requisitos
REGRA_REMUN_JA_EXISTE_DESLIGAMENTO e [infoPerAnt]. Tabela 05.
Informações adicionais
2. Tópico adicional
2.1. Detalhe
"""


def test_mos_structure_and_references() -> None:
    result = parse_mos_text(TEXT)
    assert [node.number for node in result.topics] == ["10", "10.3", "10.3.4"]
    assert result.topics[2].parent_number == "10.3"
    assert result.events[0].code == "S-1200"
    assert len(result.events[0].metadata) == 4
    assert result.events[0].topics[0].number == "2"
    assert result.events[0].subitems[0].path.endswith("/2.1")
    kinds = {reference[0] for reference in result.references}
    assert {
        "EVENT_CODE",
        "FIELD_REFERENCE",
        "GROUP_REFERENCE",
        "RULE_REFERENCE",
        "DOMAIN_TABLE_REFERENCE",
    } <= kinds


def test_missing_metadata_is_diagnostic_and_not_invented() -> None:
    result = parse_mos_text("CAP III\nS-1070 Tabela de processos\nConceito\nExiste")
    assert result.events[0].metadata == [("CONCEITO", "Conceito", "Existe")]
    assert len(result.diagnostics) == 3
    assert result.metadata_coverage["CONCEITO"] == 1


def test_table_of_contents_is_not_materialized_or_allowed_to_change_chapter_state():
    text = """Sumário
CAPÍTULO I – INFORMAÇÕES GERAIS ................ 7
1. Apresentação ................................. 7
2. Quem está obrigado ao eSocial ............... 8
CAPÍTULO III – EVENTOS ......................... 90
S-1200 Remuneração ............................. 100
CAPÍTULO I – INFORMAÇÕES GERAIS
1. Apresentação
2. Quem está obrigado ao eSocial
CAPÍTULO III – EVENTOS
S-1200 Remuneração
Conceito
Texto normativo.
"""
    result = parse_mos_text(text)
    assert [topic.path for topic in result.topics] == ["MOS/CapI/1", "MOS/CapI/2"]
    assert [event.code for event in result.events] == ["S-1200"]
    assert all("Remuneração" not in block[2] for block in result.content_blocks)


def test_duplicate_stable_paths_are_rejected_before_materialization():
    with pytest.raises(MosStructureError, match="MOS/CapI/2"):
        parse_mos_text("CAP I\n2. Primeiro\n2. Segundo")


def test_event_aware_numeric_candidates_preserve_lists_and_real_topics() -> None:
    result = parse_mos_pages(
        [
            PdfPageText(
                89,
                """89
CAPÍTULO III – ORIENTAÇÃO ESPECÍFICA POR EVENTO
S-1000 – Evento de cadastro
Conceito: Texto inicial.
1 – Etapa de procedimento REGRA_PROCEDIMENTO Tabela 12
Quem está obrigado: Todos.
Prazo de envio: Hoje.
Pré-requisitos: Nenhum.
Informações adicionais:
1. Assuntos gerais
1.1. Texto do tópico com {campo}.
1 – Forma unificada S-1210
2 – Forma não unificada
2. Outro tópico
2.1. Subitem válido
""",
            ),
            PdfPageText(
                90,
                """90
101 Empregado geral
102 Empregado rural
S-1005 – Outro evento
Conceito: Sem tópicos.
""",
            ),
        ]
    )

    event = result.events[0]
    assert [node.number for node in event.topics] == ["1", "2"]
    assert [node.number for node in event.subitems] == ["1.1", "2.1"]
    assert event.metadata[0] == (
        "CONCEITO",
        "Conceito",
        "Texto inicial.\n1 – Etapa de procedimento REGRA_PROCEDIMENTO Tabela 12",
    )
    contents = "\n".join(block[2] for block in result.content_blocks)
    assert "1 – Forma unificada S-1210" in contents
    assert "102 Empregado rural" in contents
    assert all(block[0] != "MOS/CapIII/S-1000/1" for block in result.content_blocks)
    assert {reference[1] for reference in result.references} >= {
        "REGRA_PROCEDIMENTO",
        "Tabela 12",
        "S-1210",
        "{campo}",
    }
    assert all(
        reference[3] != "MOS/CapIII/S-1000/1"
        for reference in result.references
        if reference[1] in {"REGRA_PROCEDIMENTO", "Tabela 12"}
    )


def test_repeated_event_code_uses_documentary_variant_identity() -> None:
    result = parse_mos_text(
        """CAP III
S-2500 Processo em uma jurisdição
Observação: contexto.
Conceito: Primeiro.
S-2500 Processo em outra jurisdição
Observação: contexto.
Conceito: Segundo.
"""
    )
    assert [event.path for event in result.events] == [
        "MOS/CapIII/S-2500",
        "MOS/CapIII/S-2500/variant/295ad473c8ec6889",
    ]


def test_event_candidate_classifier_is_contextual_and_not_event_specific() -> None:
    structural = NumericCandidate(
        1, 1, "1. Assuntos gerais", "1", True, "Assuntos gerais"
    )
    procedure = NumericCandidate(1, 2, "1 – Procedimento", "1", False, "– Procedimento")
    table_row = NumericCandidate(1, 3, "102 Empregado", "102", False, "Empregado")

    assert (
        classify_event_numeric_candidate(
            structural, region="ADDITIONAL", metadata_open=False
        )
        == NumericCandidateKind.STRUCTURAL_TOPIC
    )
    assert (
        classify_event_numeric_candidate(
            procedure, region="ADDITIONAL", metadata_open=False
        )
        == NumericCandidateKind.CONTENT_ENUMERATION
    )
    assert (
        classify_event_numeric_candidate(
            table_row, region="ADDITIONAL", metadata_open=True
        )
        == NumericCandidateKind.CONTENT_OTHER
    )
