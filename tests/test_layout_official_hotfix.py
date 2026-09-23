import pytest

import rag_esocial.cli as cli_module
from rag_esocial.layout_parser import LayoutStructureError, parse_layout_html
from rag_esocial.search_service import normalize_query


def _summary(code, rows):
    body = "".join(
        f"<tr><td id='r_{ident}'>{name}</td><td><a href='#r_{parent}'>{parent}</a></td>"
        f"<td>{level}</td><td>{description}</td><td>1</td><td>-</td><td>{condition}</td></tr>"
        for ident, name, parent, level, description, condition in rows
    )
    return (
        "<table class='table resumo'><tr><th>Tabela de Resumo</th></tr>"
        "<tr><td>Grupo</td><td>Grupo Pai</td><td>Nível</td><td>Descrição</td>"
        "<td>Ocor.</td><td>Chave</td><td>Condição</td></tr>"
        f"{body}</table>"
    )


def _complete(rows):
    body = "".join(
        f"<tr><td id='{ident}' title='{ident}'></td><td>{name}</td>"
        f"<td><a href='#r_{parent}'>{parent}</a></td><td>{kind}</td>"
        f"<td>{field_type}</td><td>1</td><td>{size}</td><td>{decimals}</td>"
        f"<td>{description}</td></tr>"
        for ident, name, parent, kind, field_type, size, decimals, description in rows
    )
    return (
        "<table class='table completo'><tr><th>#</th><th>Grupo/Campo</th>"
        "<th>Grupo Pai</th><th>Elem.</th><th>Tipo</th><th>Ocor.</th>"
        f"<th>Tamanho</th><th>Dec.</th><th>Descrição</th></tr>{body}</table>"
    )


def _event(code, event_name, branch):
    prefix = code[2:]
    root = prefix
    groups = [
        (f"{prefix}_ideEmpregador", "ideEmpregador", root, 3, "Identificação", "O"),
        (f"{prefix}_infoEmpregador", "infoEmpregador", root, 3, "Informações", "O"),
        (
            f"{prefix}_infoEmpregador_{branch}",
            branch,
            f"{prefix}_infoEmpregador",
            4,
            "Operação",
            "O",
        ),
        (
            f"{prefix}_infoEmpregador_{branch}_infoCadastro",
            "infoCadastro",
            f"{prefix}_infoEmpregador_{branch}",
            5,
            "Cadastro",
            "N (se procEmi = [8]); O (nos demais casos)",
        ),
    ]
    complete = [
        (root, event_name, f"{prefix}_eSocial", "G", "-", "-", "-", "Evento"),
        (
            f"{prefix}_ideEmpregador",
            "ideEmpregador",
            root,
            "G",
            "-",
            "-",
            "-",
            "Identificação",
        ),
        (
            f"{prefix}_ideEmpregador_tpInsc",
            "tpInsc",
            f"{prefix}_ideEmpregador",
            "E",
            "N",
            "1",
            "-",
            "REGRA_X Tabela 05 S-1000",
        ),
        (
            f"{prefix}_ideEmpregador_nrInsc",
            "nrInsc",
            f"{prefix}_ideEmpregador",
            "A",
            "C",
            "14",
            "-",
            "Número",
        ),
        (
            f"{prefix}_infoEmpregador",
            "infoEmpregador",
            root,
            "G",
            "-",
            "-",
            "-",
            "Informações",
        ),
        (
            f"{prefix}_infoEmpregador_{branch}",
            branch,
            f"{prefix}_infoEmpregador",
            "CG",
            "-",
            "-",
            "-",
            "Operação",
        ),
        (
            f"{prefix}_infoEmpregador_{branch}_infoCadastro",
            "infoCadastro",
            f"{prefix}_infoEmpregador_{branch}",
            "G",
            "-",
            "-",
            "-",
            "Cadastro",
        ),
        (
            f"{prefix}_infoEmpregador_{branch}_infoCadastro_classTrib",
            "classTrib",
            f"{prefix}_infoEmpregador_{branch}_infoCadastro",
            "E",
            "N",
            "2",
            "1",
            "Classificação",
        ),
    ]
    return f"<h3>{code} - Evento</h3>" + _complete(complete) + _summary(code, groups)


def _s1005():
    return (
        "<h3>S-1005 - Tabela de Estabelecimentos</h3>"
        + _summary(
            "S-1005",
            [
                ("1005_dadosEstab", "dadosEstab", "1005", 3, "Dados", "O"),
                (
                    "1005_dadosEstab_aliqGilrat",
                    "aliqGilrat",
                    "1005_dadosEstab",
                    4,
                    "Alíquota",
                    "O",
                ),
            ],
        )
        + _complete(
            [
                ("1005", "evtTabEstab", "1005_eSocial", "G", "-", "-", "-", "Evento"),
                (
                    "1005_dadosEstab",
                    "dadosEstab",
                    "1005",
                    "G",
                    "-",
                    "-",
                    "-",
                    "Dados",
                ),
                (
                    "1005_dadosEstab_aliqGilrat",
                    "aliqGilrat",
                    "1005_dadosEstab",
                    "G",
                    "-",
                    "-",
                    "-",
                    "Alíquota",
                ),
                (
                    "1005_dadosEstab_aliqGilrat_aliqRat",
                    "aliqRat",
                    "1005_dadosEstab_aliqGilrat",
                    "E",
                    "N",
                    "4",
                    "2",
                    "Percentual RAT",
                ),
            ]
        )
    )


def _paths(event):
    paths = set()
    stack = list(event.groups)
    while stack:
        group = stack.pop()
        paths.add(group.path)
        paths.update(item.path for item in group.fields)
        stack.extend(group.children)
    return paths


def test_official_tables_are_paired_by_identity_not_position():
    html = _event("S-1000", "evtInfoEmpregador", "inclusao")
    result = parse_layout_html(html)
    paths = _paths(result.events[0])
    assert "LAYOUT/S-1000/ideEmpregador" in paths
    assert "LAYOUT/S-1000/ideEmpregador/tpInsc" in paths
    assert "LAYOUT/S-1000/ideEmpregador/nrInsc" in paths
    assert "LAYOUT/S-1000/infoEmpregador/inclusao/infoCadastro/classTrib" in paths
    assert {r.kind for r in result.references} >= {
        "RULE_REFERENCE",
        "DOMAIN_TABLE_REFERENCE",
        "EVENT_CODE",
    }
    group = next(g for g in result.events[0].groups if g.name == "infoEmpregador")
    assert group.children[0].children[0].attrs["condition"].startswith("N (se")
    field = next(
        f for g in result.events[0].groups for f in g.fields if f.name == "tpInsc"
    )
    assert field.attrs["type"] == "N" and "condition" not in field.attrs


def test_branch_identity_and_structural_failure():
    html = _event("S-1000", "evtInfoEmpregador", "inclusao")
    altered = html.replace("inclusao", "alteracao")
    assert "LAYOUT/S-1000/infoEmpregador/alteracao/infoCadastro" in _paths(
        parse_layout_html(altered).events[0]
    )
    with pytest.raises(LayoutStructureError):
        parse_layout_html(html.replace("#r_1000_ideEmpregador", "#r_1000_missing"))
    with pytest.raises(LayoutStructureError):
        parse_layout_html("<html><body>nothing</body></html>")


def test_second_event_deep_field_path():
    result = parse_layout_html(
        _event("S-1000", "evtInfoEmpregador", "inclusao") + _s1005()
    )
    assert "LAYOUT/S-1005/dadosEstab/aliqGilrat/aliqRat" in _paths(result.events[1])


def test_reuse_row_is_reference_not_artificial_node():
    html = _event("S-1000", "evtInfoEmpregador", "inclusao")
    row = (
        "<tr><td>...</td>"
        + "<td></td>" * 7
        + "<td>Ver: <a href='#1000_infoEmpregador_inclusao_infoCadastro'>"
        "inclusao &gt; infoCadastro</a></td></tr>"
    )
    html = html.replace(
        "</table><table class='table resumo'>",
        row + "</table><table class='table resumo'>",
    )
    result = parse_layout_html(html)
    assert "..." not in " ".join(_paths(result.events[0]))
    assert any(
        ref.kind == "LOCAL_REUSE_REFERENCE"
        and ref.normalized_value == "#1000_infoEmpregador_inclusao_infoCadastro"
        for ref in result.references
    )


def test_lexical_normalization_preserves_technical_tokens():
    assert normalize_query("qual é o conceito do evento S-1000?") == "conceito S-1000"
    assert (
        normalize_query(
            "quais campos pertencem ao grupo ideEmpregador do evento S-1000?"
        )
        == "ideEmpregador S-1000"
    )
    assert (
        normalize_query(
            "quais elementos filhos existem em ideEmpregador no XSD do S-1000?"
        )
        == "ideEmpregador S-1000"
    )
    assert (
        normalize_query("REGRA_VALIDA_ID_EVENTO tpInsc")
        == "REGRA_VALIDA_ID_EVENTO tpInsc"
    )


def test_operator_menu_routes_to_family_profiles(monkeypatch):
    choices = iter(("1", "2", "3", "4", "0"))
    selected = []
    monkeypatch.setattr(cli_module.typer, "prompt", lambda *_args, **_kw: next(choices))
    monkeypatch.setattr(cli_module, "_query_active", selected.append)
    cli_module._main_menu()
    assert selected == ["MOS_ALL", "LAYOUT_ALL", "XSD_ALL", "CROSS_SOURCE"]
