from rag_esocial.mos_parser import parse_mos_text

TEXT = """CAP I
10 Tópico principal
10.3 Subtópico
10.3.4 Subitem profundo
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
2 Tópico adicional
2.1 Detalhe
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
