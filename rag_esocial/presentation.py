"""Rich presentation for the public terminal experience.

Only formats authorized results already selected by the operational pipeline.
It does not retrieve, rank, infer, or persist evidence.
"""

from rich.console import Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

STYLE_TITLE = "bold cyan"
STYLE_MOS = "blue"
STYLE_LAYOUT = "magenta"
STYLE_XSD = "cyan"
STYLE_SUCCESS = "green"
STYLE_WARNING = "yellow"
STYLE_ERROR = "red"
STYLE_MUTED = "dim"
STYLE_PATH = "cyan"

FAMILIES = {
    "MOS": ("MOS", STYLE_MOS),
    "LAYOUT": ("Leiaute", STYLE_LAYOUT),
    "XSD": ("XSD", STYLE_XSD),
}

KIND_LABELS = {
    "MOS_EVENT_SECTION": "Evento",
    "MOS_EVENT_METADATA": "Metadado do evento",
    "MOS_EVENT_TOPIC": "Tópico do evento",
    "MOS_TOPIC": "Tópico",
    "MOS_SUBITEM": "Subitem",
    "LAYOUT_EVENT": "Evento",
    "LAYOUT_GROUP": "Grupo",
    "LAYOUT_FIELD": "Campo",
    "XSD_EVENT_SCHEMA": "Schema do evento",
    "XSD_ELEMENT": "Elemento",
    "XSD_SHARED_TYPE": "Tipo compartilhado",
}

FIELD_LABELS = {
    "Event": "Evento",
    "Title": "Título",
    "Metadata": "Rótulo",
    "Content": "Conteúdo",
    "Body": "Conteúdo",
    "Event topic": "Tópico do evento",
    "Topic": "Tópico",
    "Subitem": "Subitem",
    "Name": "Nome",
    "Group": "Grupo",
    "Description": "Descrição",
    "Type": "Tipo",
    "Occurrence": "Ocorrência",
    "Size": "Tamanho",
    "Decimals": "Decimais",
    "Condition": "Condição",
    "Element": "Elemento",
    "Ref": "Referência",
    "minOccurs": "minOccurs",
    "maxOccurs": "maxOccurs",
    "Documentation": "Documentação",
    "Facets": "Restrições",
    "Enumerations": "Enumerações",
    "Shared type": "Tipo compartilhado",
    "Base": "Base",
    "Schema": "Schema",
    "Namespace": "Namespace",
}

PRIMARY_FIELDS = {
    "MOS_EVENT_SECTION": ("Event", "Title"),
    "MOS_EVENT_METADATA": ("Metadata", "Content"),
    "MOS_EVENT_TOPIC": ("Event topic",),
    "MOS_TOPIC": ("Topic", "Body"),
    "MOS_SUBITEM": ("Subitem",),
    "LAYOUT_EVENT": ("Event", "Title"),
    "LAYOUT_GROUP": ("Group", "Description"),
    "LAYOUT_FIELD": ("Name", "Description"),
    "XSD_EVENT_SCHEMA": ("Schema", "Documentation"),
    "XSD_ELEMENT": ("Element", "Documentation"),
    "XSD_SHARED_TYPE": ("Shared type",),
}


def _value(value: str) -> str:
    cleaned = value.strip()
    return "—" if not cleaned or cleaned == "{}" else cleaned


def _fields(content: str) -> dict[str, str]:
    """Parse the existing structural display format, preserving multiline prose."""
    fields: dict[str, str] = {}
    current = None
    for line in content.splitlines():
        key, separator, value = line.partition(": ")
        if separator and (key in FIELD_LABELS or key == "Path"):
            current = key
            fields[key] = value
        elif current == "Topic":
            fields["Body"] = "\n".join(filter(None, (fields.get("Body"), line)))
        elif current:
            fields[current] += "\n" + line
    return fields


def _grid(rows: list[tuple[str, str]]) -> Table:
    table = Table.grid(padding=(0, 2))
    table.add_column(style=STYLE_MUTED, no_wrap=True, width=13)
    table.add_column(overflow="fold")
    for label, value in rows:
        table.add_row(label, Text(_value(value), overflow="fold"))
    return table


def header(summary: dict | None):
    if not summary:
        return Panel(
            Group(
                Text("Assistente local baseado em fontes oficiais do eSocial."),
                Text("Preparação necessária", style=STYLE_WARNING),
            ),
            title="eSocial RAG",
            title_align="left",
            border_style=STYLE_TITLE,
        )
    rows = [("Sistema", "Pronto"), ("Corpus", "Ativo")]
    rows.extend(
        (label, summary["versions"].get(role) or "Indisponível")
        for role, label in (
            ("MOS_MAIN", "MOS"),
            ("LAYOUT_MAIN", "Leiaute"),
            ("XSD_PACKAGE", "XSD"),
        )
    )
    return Panel(
        Group(
            Text("Assistente local baseado em evidências oficiais do eSocial."),
            _grid(rows),
        ),
        title="eSocial RAG",
        title_align="left",
        border_style=STYLE_TITLE,
    )


def status(summary: dict | None, details: dict | None):
    if not summary or not details:
        return warning(
            "Runtime ainda não preparado", "Importe as fontes oficiais para começar."
        )
    versions = summary["versions"]
    return Group(
        Panel(
            _grid(
                [
                    ("Sistema", "Pronto"),
                    ("Corpus", details["corpus_status"]),
                    ("MOS", versions.get("MOS_MAIN") or "Indisponível"),
                    ("Leiaute", versions.get("LAYOUT_MAIN") or "Indisponível"),
                    ("XSD", versions.get("XSD_PACKAGE") or "Indisponível"),
                ]
            ),
            title="Visão geral",
            border_style=STYLE_TITLE,
        ),
        Panel(
            _grid(
                [
                    ("Build", details["build_id"]),
                    ("Parser", summary["parser_revision"]),
                    ("Busca", details["search_revision"]),
                    ("Geração", str(summary["generation"])),
                ]
            ),
            title="Runtime",
            border_style=STYLE_TITLE,
        ),
        Panel(
            _grid(
                [
                    ("Snapshot", details["snapshot_id"]),
                    ("Estado", details["snapshot_status"]),
                    ("Artefatos", str(details["artifact_count"])),
                ]
            ),
            title="Corpus",
            border_style=STYLE_TITLE,
        ),
    )


def menu():
    items = (
        ("1", "MOS", "Orientações e procedimentos"),
        ("2", "Leiaute", "Eventos, grupos e campos"),
        ("3", "XSD", "Estrutura técnica dos schemas"),
        ("4", "Evidências cross-source", "Evidências separadas por fonte"),
        ("5", "Importar nova versão", "Atualizar o corpus oficial"),
        ("6", "Status", "Diagnóstico do runtime"),
        ("0", "Sair", "Encerrar"),
    )
    table = Table.grid(padding=(0, 2))
    table.add_column(style=STYLE_TITLE, no_wrap=True)
    table.add_column(style="bold", no_wrap=True)
    table.add_column(style=STYLE_MUTED)
    for number, label, description in items:
        table.add_row(f"[{number}]", label, description)
    return Panel(table, title="Menu principal", border_style=STYLE_TITLE)


def query_intro(profile: str):
    family = profile.removesuffix("_ALL")
    if family == "CROSS_SOURCE":
        return Panel(
            "Consulte MOS, Leiaute e XSD. As evidências são exibidas por fonte, "
            "sem conclusão automática.",
            title="Consulta em MOS + Leiaute + XSD",
            border_style=STYLE_TITLE,
        )
    label, style = FAMILIES[family]
    return Panel(
        f"Digite sua pergunta sobre {label}.",
        title=f"Consulta {label}",
        border_style=style,
    )


def evidence(row: dict, content: str, index: int):
    family = row["document_family"]
    label, style = FAMILIES[family]
    kind = row["unit_kind"]
    fields = _fields(content)
    primary = PRIMARY_FIELDS.get(kind, ())
    prominent = [
        Text(_value(fields[key]), style="bold" if pos == 0 else "")
        for pos, key in enumerate(primary)
        if key in fields and _value(fields[key]) != "—"
    ]
    attributes = [
        (FIELD_LABELS[key], value)
        for key, value in fields.items()
        if key not in primary and key != "Path" and _value(value) != "—"
    ]
    parts = prominent[:]
    if attributes:
        parts.append(_grid(attributes))
    path = row["source_local_stable_path"]
    metadata = Table.grid(padding=(0, 2))
    metadata.add_column(style=STYLE_MUTED, no_wrap=True, width=7)
    metadata.add_column(overflow="fold")
    metadata.add_row("Fonte", label)
    metadata.add_row("Path", Text(path, style=STYLE_PATH, overflow="fold"))
    metadata.add_row("Score", f"{row['score']:.4f}")
    parts.append(metadata)
    return Panel(
        Group(*parts),
        title=f"Evidência {index} · {KIND_LABELS.get(kind, kind)}",
        title_align="left",
        border_style=style,
    )


def source_block(family: str, rows: list[tuple[dict, str]]):
    label, style = FAMILIES[family]
    if rows:
        body = Group(
            *(
                evidence(row, content, index)
                for index, (row, content) in enumerate(rows, 1)
            )
        )
    else:
        body = Text(
            f"Nenhuma evidência autorizada encontrada no {label} para esta consulta."
        )
    return Panel(body, title=label.upper(), title_align="left", border_style=style)


def warning(title: str, message: str):
    return Panel(
        Text(message), title=title, title_align="left", border_style=STYLE_WARNING
    )


def error(title: str, message: str):
    return Panel(
        Text(message), title=title, title_align="left", border_style=STYLE_ERROR
    )


def success(message: str):
    return Text(message, style=STYLE_SUCCESS)


def stage(message: str):
    return Text(f"• {message}", style=STYLE_MUTED)
