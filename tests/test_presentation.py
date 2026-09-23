"""Public CLI presentation contracts without a production database."""

from contextlib import contextmanager
from io import StringIO
from types import SimpleNamespace

import pytest
from rich.console import Console

from rag_esocial import presentation


def rendered(*items, width=90, color=False):
    stream = StringIO()
    console = Console(
        file=stream,
        width=width,
        force_terminal=color,
        color_system="standard" if color else None,
    )
    for item in items:
        console.print(item)
    return stream.getvalue()


def row(family, kind, path):
    return {
        "document_family": family,
        "unit_kind": kind,
        "source_local_stable_path": path,
        "score": 100.0,
    }


@pytest.mark.parametrize("width", [60, 100])
def test_startup_menu_and_status(width):
    summary = {
        "versions": {
            "MOS_MAIN": "MOS 1.3",
            "LAYOUT_MAIN": "Leiaute 1.3",
            "XSD_PACKAGE": "XSD 1.3",
        },
        "parser_revision": "parser-suite-v2",
        "generation": 3,
    }
    details = {
        "build_id": "build-123",
        "search_revision": "fts-baseline-v3",
        "corpus_status": "COMPLETE",
        "snapshot_id": "snapshot-123",
        "snapshot_status": "Congelado",
        "artifact_count": 5,
    }
    startup = rendered(presentation.header(summary), width=width)
    assert all(part in startup for part in ("eSocial RAG", "MOS", "Leiaute", "XSD"))
    assert "build-123" not in startup
    menu = rendered(presentation.menu(), width=width)
    assert all(f"[{number}]" in menu for number in range(7))
    assert "Evidências cross-source" in menu and "Sair" in menu
    status = rendered(presentation.status(summary, details), width=width)
    assert all(
        part in status
        for part in (
            "Visão geral",
            "Runtime",
            "Corpus",
            "build-123",
            "snapshot-123",
            "fts-baseline-v3",
            "parser-suite-v2",
        )
    )


@pytest.mark.parametrize(
    ("family", "kind", "content", "expected"),
    [
        ("MOS", "MOS_EVENT_SECTION", "Event: S-1000\nTitle: Empregador", "Empregador"),
        (
            "MOS",
            "MOS_EVENT_METADATA",
            "Metadata: Conceito\nContent: Texto oficial",
            "Conceito",
        ),
        ("MOS", "MOS_EVENT_TOPIC", "Event topic: 1 Orientação", "Orientação"),
        ("MOS", "MOS_TOPIC", "Topic: 2 Procedimento\nTexto do tópico", "Procedimento"),
        ("MOS", "MOS_SUBITEM", "Subitem: 1.1 Passo", "Passo"),
        ("LAYOUT", "LAYOUT_EVENT", "Event: S-1000\nTitle: Empregador", "Empregador"),
        (
            "LAYOUT",
            "LAYOUT_GROUP",
            "Path: LAYOUT/S-1000/grupo\nGroup: grupo\nDescription: Descrição\n"
            "Occurrence: 1\nCondition: O",
            "Ocorrência",
        ),
        (
            "LAYOUT",
            "LAYOUT_FIELD",
            "Path: LAYOUT/S-1000/grupo/campo\nName: campo\nDescription: Valor\n"
            "Type: C\nOccurrence: 1\nSize: 8\nDecimals: \nCondition: ",
            "Tamanho",
        ),
        (
            "XSD",
            "XSD_EVENT_SCHEMA",
            "Schema: evtTeste\nNamespace: urn:teste\nDocumentation: Oficial",
            "evtTeste",
        ),
        (
            "XSD",
            "XSD_ELEMENT",
            "Path: XSD/evtTeste/campo\nElement: campo\nType: xs:string\nRef: \n"
            "minOccurs: 0\nmaxOccurs: 1\nDocumentation: Descrição\n"
            "Facets: {'pattern': '[A-Z]+'}\nEnumerations: A, B",
            "Enumerações",
        ),
        (
            "XSD",
            "XSD_SHARED_TYPE",
            "Path: XSD/tipo\nShared type: tipo\nBase: xs:string\nFacets: {}",
            "Tipo compartilhado",
        ),
    ],
)
def test_evidence_kind_renderers(family, kind, content, expected):
    path = f"{family}/test/path"
    output = rendered(presentation.evidence(row(family, kind, path), content, 1))
    assert expected in output
    assert path in output
    assert "100.0000" in output
    assert "Evidência 1" in output
    assert "{}" not in output
    assert "Enumerations:" not in output


def test_cross_source_abstention_errors_prompts_and_no_color():
    layout = (
        row("LAYOUT", "LAYOUT_FIELD", "LAYOUT/S-1000/campo"),
        "Name: campo\nDescription: Valor autorizado\nType: C",
    )
    xsd = (
        row("XSD", "XSD_ELEMENT", "XSD/evtTeste/campo"),
        "Element: campo\nType: xs:string",
    )
    output = rendered(
        presentation.query_intro("CROSS_SOURCE"),
        presentation.source_block("MOS", []),
        presentation.source_block("LAYOUT", [layout]),
        presentation.source_block("XSD", [xsd]),
        presentation.warning("Nenhuma evidência encontrada", "Consulta sem suporte."),
        presentation.error("Falha operacional", "URL inválida"),
        width=78,
    )
    assert output.index("╭─ MOS") < output.index("╭─ LEIAUTE") < output.index("╭─ XSD")
    assert "Nenhuma evidência autorizada encontrada no MOS" in output
    assert "LAYOUT/S-1000/campo" in output and "XSD/evtTeste/campo" in output
    assert "Nenhuma evidência encontrada" in output
    assert "Falha operacional" in output and "URL inválida" in output
    assert "Conclusão" not in output
    assert "\x1b[" not in output
    colored = rendered(presentation.source_block("MOS", []), color=True)
    assert "\x1b[" in colored


def test_long_text_wraps_without_truncation():
    description = "Texto oficial longo " * 60
    content = f"Name: campo\nDescription: {description}\nType: C"
    output = rendered(
        presentation.evidence(
            row("LAYOUT", "LAYOUT_FIELD", "LAYOUT/S-1000/grupo/campo"),
            content,
            1,
        ),
        width=70,
    )
    assert output.count("Texto") == 60
    assert "LAYOUT/S-1000/grupo/campo" in output


def test_missing_values_do_not_render_empty_sections():
    output = rendered(
        presentation.evidence(
            row("XSD", "XSD_ELEMENT", "XSD/evtTeste/campo"),
            "Element: campo\nType: \nRef: \nFacets: {}\nEnumerations: ",
            1,
        )
    )
    assert "{}" not in output
    assert "Enumerações" not in output
    assert "Referência" not in output
    assert "campo" in output


def test_cli_status_uses_existing_runtime_data(monkeypatch):
    import rag_esocial.cli as cli

    summary = {
        "versions": {
            "MOS_MAIN": "MOS 1.3",
            "LAYOUT_MAIN": "Leiaute 1.3",
            "XSD_PACKAGE": "XSD 1.3",
        },
        "parser_revision": "parser-suite-v2",
        "generation": 3,
    }
    snapshot = SimpleNamespace(id="snapshot-123", frozen_at="frozen", members=[1, 2, 3])
    runtime = SimpleNamespace(
        corpus_build_id="build-123",
        build=SimpleNamespace(snapshot=snapshot, status="COMPLETE"),
        projection=SimpleNamespace(projection_revision="fts-baseline-v3"),
    )

    @contextmanager
    def fake_session():
        yield object()

    monkeypatch.setattr(cli, "session_factory", lambda: fake_session)
    monkeypatch.setattr(cli, "active_runtime_summary", lambda _session: summary)
    monkeypatch.setattr(cli, "get_active_runtime", lambda _session: runtime)
    stream = StringIO()
    monkeypatch.setattr(cli, "console", Console(file=stream, color_system=None))
    cli._normal_runtime_status()
    assert "build-123" not in stream.getvalue()
    stream.seek(0)
    stream.truncate(0)
    cli._detailed_runtime_status()
    assert all(
        value in stream.getvalue()
        for value in ("build-123", "snapshot-123", "fts-baseline-v3", "3")
    )
