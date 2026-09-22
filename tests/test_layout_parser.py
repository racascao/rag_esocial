from rag_esocial.layout_parser import parse_layout_html

HTML = """<section data-kind='event' code='S-9999' title='Evento fixture'>
<div data-kind='group' name='info' level='1' description='Raiz'>
<div data-kind='group' name='dados' level='2' description='Dados'>
<div data-kind='group' name='detalhe' level='3'>
<p data-kind='field' name='aliqRat' type='N' occurrence='1-1' size='5'
condition='REGRA_EXEMPLO'>Descrição com REGRA_EXEMPLO, Tabela 05 e S-1210</p>
</div></div></div></section>"""


def test_layout_event_group_field_hierarchy_and_references() -> None:
    result = parse_layout_html(HTML)
    assert result.events[0].code == "S-9999"
    root = result.events[0].groups[0]
    assert root.children[0].children[0].path.endswith("/info/dados/detalhe")
    field = root.children[0].children[0].fields[0]
    assert field.path.endswith("/info/dados/detalhe/aliqRat")
    assert field.attrs["condition"] == "REGRA_EXEMPLO"
    assert {ref.kind for ref in result.references} == {
        "RULE_REFERENCE",
        "DOMAIN_TABLE_REFERENCE",
        "EVENT_CODE",
    }


def test_layout_reference_without_a_structural_owner_is_not_materialized() -> None:
    result = parse_layout_html("<title>Tabela 12 REGRA_GLOBAL</title>" + HTML)

    assert all(reference.owner_path != "LAYOUT" for reference in result.references)
