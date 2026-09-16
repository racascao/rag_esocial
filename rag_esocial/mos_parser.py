import re
import uuid
from dataclasses import dataclass, field

METADATA = {
    "Conceito": "CONCEITO",
    "Quem está obrigado": "QUEM_ESTA_OBRIGADO",
    "Prazo de envio": "PRAZO_DE_ENVIO",
    "Pré-requisitos": "PRE_REQUISITOS",
}
REFERENCE_PATTERNS = (
    ("FIELD_REFERENCE", re.compile(r"\{[A-Za-z][\w]*\}")),
    ("GROUP_REFERENCE", re.compile(r"\[[A-Za-z][\w]*\]")),
    ("RULE_REFERENCE", re.compile(r"\bREGRA_[A-Z0-9_]+\b")),
    ("DOMAIN_TABLE_REFERENCE", re.compile(r"\bTabela\s+\d+\b", re.I)),
    ("EVENT_CODE", re.compile(r"\bS-\d{4}\b")),
)


@dataclass
class MosDiagnostic:
    severity: str
    code: str
    message: str
    path: str | None = None


@dataclass
class ParsedNode:
    kind: str
    number: str
    title: str
    path: str
    parent_number: str | None = None
    content: str = ""


@dataclass
class ParsedEvent:
    code: str
    title: str
    path: str
    metadata: list[tuple[str, str, str]] = field(default_factory=list)
    topics: list[ParsedNode] = field(default_factory=list)
    subitems: list[ParsedNode] = field(default_factory=list)


@dataclass
class MosParseResult:
    topics: list[ParsedNode] = field(default_factory=list)
    events: list[ParsedEvent] = field(default_factory=list)
    content_blocks: list[tuple[str, str, str]] = field(default_factory=list)
    references: list[tuple[str, str, str, str]] = field(default_factory=list)
    diagnostics: list[MosDiagnostic] = field(default_factory=list)

    @property
    def metadata_coverage(self) -> dict[str, int]:
        return {
            kind: sum(
                1
                for event in self.events
                if any(block[0] == kind for block in event.metadata)
            )
            for kind in METADATA.values()
        }


def normalize_text(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n").replace("\u00a0", " ")


def parse_mos_text(text: str) -> MosParseResult:
    lines = [line.strip() for line in normalize_text(text).splitlines()]
    result = MosParseResult()
    chapter = "I"
    current_event: ParsedEvent | None = None
    current_block: tuple[str, list[str], str] | None = None
    current_owner = "MOS/CapI"
    current_parent: dict[int, str] = {}
    for line in lines:
        if not line:
            continue
        chapter_match = re.match(r"CAP\s*([IVX]+)\b", line, re.I)
        if chapter_match:
            chapter = chapter_match.group(1).upper()
            current_event = None
            continue
        event_match = re.match(r"^(S-\d{4})\b(?:\s*[-–:]?\s*(.*))?$", line)
        if chapter == "III" and event_match:
            current_event = ParsedEvent(
                event_match.group(1),
                event_match.group(2) or event_match.group(1),
                f"MOS/CapIII/{event_match.group(1)}",
            )
            result.events.append(current_event)
            current_block = None
            current_owner = current_event.path
            continue
        metadata_match = next(
            (
                item
                for label, item in METADATA.items()
                if line.casefold() == label.casefold()
            ),
            None,
        )
        if current_event and metadata_match:
            if current_block:
                current_event.metadata.append(
                    (
                        current_block[0],
                        current_block[2],
                        "\n".join(current_block[1]).strip(),
                    )
                )
            current_block = (metadata_match, [], line)
            current_owner = f"{current_event.path}/metadata/{metadata_match.lower()}"
            continue
        if current_event and line.casefold() == "informações adicionais":
            if current_block:
                current_event.metadata.append(
                    (
                        current_block[0],
                        current_block[2],
                        "\n".join(current_block[1]).strip(),
                    )
                )
                current_block = None
            current_owner = current_event.path
            continue
        number_match = re.match(r"^(\d+(?:\.\d+)*)\.?\s*(.*)$", line)
        if number_match:
            number, title = number_match.groups()
            depth = number.count(".") + 1
            parent = ".".join(number.split(".")[:-1]) or None
            node = ParsedNode(
                "SUBITEM" if depth > 1 else "TOPIC", number, title, "", parent
            )
            if current_event:
                node.path = f"{current_event.path}/{number}"
                (current_event.subitems if depth > 1 else current_event.topics).append(
                    node
                )
                current_owner = node.path
            else:
                node.path = f"MOS/Cap{chapter}/{number}"
                result.topics.append(node)
                current_owner = node.path
            current_parent[depth] = number
            continue
        if current_block:
            current_block[1].append(line)
        elif current_event:
            result.content_blocks.append(
                (
                    f"{current_event.path}/content/{len(result.content_blocks) + 1}",
                    "PARAGRAPH",
                    line,
                )
            )
        else:
            result.content_blocks.append(
                (
                    f"MOS/Cap{chapter}/content/{len(result.content_blocks) + 1}",
                    "PARAGRAPH",
                    line,
                )
            )
        for kind, pattern in REFERENCE_PATTERNS:
            for match in pattern.finditer(line):
                result.references.append((kind, match.group(0), "D2", current_owner))
    if current_event and current_block:
        current_event.metadata.append(
            (current_block[0], current_block[2], "\n".join(current_block[1]).strip())
        )
    for event in result.events:
        for label in METADATA.values():
            if not any(block[0] == label for block in event.metadata):
                result.diagnostics.append(
                    MosDiagnostic(
                        "WARNING", "MISSING_METADATA", f"{label} ausente", event.path
                    )
                )
    return result


def new_id() -> str:
    return str(uuid.uuid4())
