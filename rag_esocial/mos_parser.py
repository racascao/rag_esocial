import hashlib
import re
import unicodedata
import uuid
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Iterable

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


class MosStructureError(ValueError):
    """The extracted MOS structure is not safe to persist."""


class NumericCandidateKind(StrEnum):
    """Classification of a numeric line found inside an event.

    A number is only a candidate.  The MOS uses the same typography for
    headings, prose enumerations, procedures and table rows.
    """

    STRUCTURAL_TOPIC = "STRUCTURAL_TOPIC"
    STRUCTURAL_SUBITEM = "STRUCTURAL_SUBITEM"
    CONTENT_ENUMERATION = "CONTENT_ENUMERATION"
    CONTENT_TABLE_ROW = "CONTENT_TABLE_ROW"
    CONTENT_OTHER = "CONTENT_OTHER"


@dataclass(frozen=True)
class NumericCandidate:
    page_number: int
    line_index: int
    raw: str
    number: str
    terminal_dot: bool
    title: str


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


CHAPTER_PATTERN = re.compile(r"CAP(?:[ÍI]TULO)?\s*([IVX]+)\b", re.I)


def _chapter_heading(line: str) -> re.Match[str] | None:
    """Recognize printed chapter headings, not prose such as ``Capítulo I``."""
    match = CHAPTER_PATTERN.match(line)
    return match if match and line == line.upper() else None


def _body_lines(lines: list[str]):
    """Exclude a table of contents until its first non-leader chapter heading."""
    in_toc = False
    for line in lines:
        normalized = line.casefold().replace("á", "a")
        if normalized == "sumario":
            in_toc = True
            continue
        chapter = _chapter_heading(line)
        if in_toc:
            if chapter and not re.search(r"\.{3,}", line):
                in_toc = False
            else:
                continue
        yield line


def _body_page_lines(
    lines: Iterable[tuple[int, int, str]],
) -> Iterable[tuple[int, int, str]]:
    """Page-aware counterpart of :func:`_body_lines` without losing repeats."""
    in_toc = False
    for page_number, line_index, line in lines:
        normalized = line.casefold().replace("á", "a")
        if normalized == "sumario":
            in_toc = True
            continue
        chapter = _chapter_heading(line)
        if in_toc:
            if chapter and not re.search(r"\.{3,}", line):
                in_toc = False
            else:
                continue
        yield page_number, line_index, line


def _is_page_furniture(line: str) -> bool:
    """Ignore page numbers and repeated PDF furniture, never body content."""
    return bool(re.fullmatch(r"\d+", line)) or line.casefold().startswith(
        "manual de orienta"
    )


def _metadata_label(line: str) -> tuple[str, str, str] | None:
    """Return metadata kind, original label and inline content when present."""
    label_text, separator, inline_content = line.partition(":")
    normalized_label = _fold(label_text)
    for label, kind in METADATA.items():
        aliases = {_fold(label)}
        if kind == "CONCEITO":
            aliases.add("conceito do evento")
        if normalized_label in aliases:
            return kind, label, inline_content.strip() if separator else ""
    return None


def _is_additional_information(line: str) -> bool:
    return _fold(line.rstrip(": ")) == "informacoes adicionais"


def _fold(value: str) -> str:
    return "".join(
        char
        for char in unicodedata.normalize("NFD", value.casefold())
        if unicodedata.category(char) != "Mn"
    ).strip()


def classify_event_numeric_candidate(
    candidate: NumericCandidate,
    *,
    region: str,
    metadata_open: bool,
    accepted_numbers: set[str] | None = None,
    last_number_at_depth: str | None = None,
) -> NumericCandidateKind:
    """Classify one event-local numeric candidate from structural evidence.

    The real MOS reserves its numbered heading hierarchy for ``Informações
    adicionais`` and prints it with a terminal dot (``1.`` / ``1.1.``).
    Enumerations and procedures use a dash or other non-heading form, while
    metadata has precedence regardless of typography.  This intentionally
    does not inspect an event code, page number, or topic wording.
    """
    if metadata_open or region == "METADATA":
        return NumericCandidateKind.CONTENT_OTHER
    if re.match(r"^\d+(?:[./-]\d+){1,}\s+", candidate.raw):
        return NumericCandidateKind.CONTENT_TABLE_ROW
    if region != "ADDITIONAL" or not candidate.terminal_dot:
        return NumericCandidateKind.CONTENT_ENUMERATION
    if not candidate.title or candidate.title.startswith(("-", "–", ")")):
        return NumericCandidateKind.CONTENT_ENUMERATION
    accepted_numbers = accepted_numbers or set()
    parent = ".".join(candidate.number.split(".")[:-1])
    if parent and parent not in accepted_numbers:
        return NumericCandidateKind.CONTENT_OTHER
    if last_number_at_depth:
        previous_tail = int(last_number_at_depth.rsplit(".", 1)[-1])
        candidate_tail = int(candidate.number.rsplit(".", 1)[-1])
        if candidate_tail <= previous_tail:
            return NumericCandidateKind.CONTENT_OTHER
    return (
        NumericCandidateKind.STRUCTURAL_SUBITEM
        if "." in candidate.number
        else NumericCandidateKind.STRUCTURAL_TOPIC
    )


def _toc_topic_keys(lines: list[str]) -> set[tuple[str, str, str]]:
    """Use the document's own table of contents as a closed heading catalogue."""
    keys: set[tuple[str, str, str]] = set()
    in_toc = False
    chapter = "I"
    for line in lines:
        normalized = line.casefold().replace("á", "a")
        if normalized == "sumario":
            in_toc = True
            continue
        if not in_toc:
            continue
        chapter_match = _chapter_heading(line)
        if chapter_match:
            if not re.search(r"\.{3,}", line):
                break
            chapter = chapter_match.group(1).upper()
            continue
        match = re.match(r"^(\d+(?:\.\d+)*)\.\s*(.+?)\s*\.{3,}.*$", line)
        if match:
            number, title = match.groups()
            keys.add((chapter, number, re.sub(r"\s+", " ", title).casefold()))
    return keys


def _toc_event_keys(lines: list[str]) -> set[tuple[str, str]]:
    keys: set[tuple[str, str]] = set()
    in_toc = False
    for line in lines:
        if line.casefold().replace("á", "a") == "sumario":
            in_toc = True
            continue
        if not in_toc:
            continue
        match = re.match(r"^(S-\d{4})\s*[–-]\s*(.+?)\s*\.{3,}.*$", line)
        if match:
            code, title = match.groups()
            keys.add((code, re.sub(r"\s+", " ", title).casefold()))
    return keys


def _toc_event_codes(lines: list[str]) -> set[str]:
    """Read event codes even when a long title wraps before its page leader."""
    codes: set[str] = set()
    in_toc = False
    for line in lines:
        if line.casefold().replace("á", "a") == "sumario":
            in_toc = True
            continue
        if not in_toc:
            continue
        chapter = _chapter_heading(line)
        if chapter and not re.search(r"\.{3,}", line):
            break
        match = re.match(r"^(S-\d{4})\b", line)
        if match:
            codes.add(match.group(1))
    return codes


def _looks_like_event_heading(
    body_lines: list[tuple[int, int, str]], index: int
) -> bool:
    """Require the event-title-to-``Conceito`` transition seen in the MOS.

    A line beginning with ``S-####`` also occurs in wrapped prose.  The
    document's event heading is an isolated transition into the first metadata
    region, so the following short page-local neighbourhood is stronger
    evidence than the code token alone.
    """
    page_number = body_lines[index][0]
    nearby_lines = body_lines[index + 1 : index + 9]
    for candidate_page, _line_index, candidate_line in nearby_lines:
        if candidate_page != page_number:
            break
        metadata = _metadata_label(candidate_line)
        if metadata:
            return metadata[0] == "CONCEITO"
    return False


def _event_path(code: str, title: str, known_titles: dict[str, set[str]]) -> str:
    """Build a non-positional path for a code with documentary variants."""
    base_path = f"MOS/CapIII/{code}"
    normalized_title = _fold(title)
    titles = known_titles.setdefault(code, set())
    if not titles:
        titles.add(normalized_title)
        return base_path
    if normalized_title in titles:
        raise MosStructureError(f"duplicate event heading: {code} ({title})")
    titles.add(normalized_title)
    digest = hashlib.sha256(normalized_title.encode()).hexdigest()[:16]
    return f"{base_path}/variant/{digest}"


def validate_mos_structure(result: MosParseResult) -> None:
    """Reject stable-path collisions before any ORM row is created."""
    seen: dict[str, str] = {}

    def add(path: str, kind: str) -> None:
        previous = seen.get(path)
        if previous is not None:
            raise MosStructureError(
                f"duplicate source_local_stable_path: {path} ({previous}, {kind})"
            )
        seen[path] = kind

    for node in result.topics:
        add(node.path, "topic")
    for event in result.events:
        add(event.path, "event")
        for kind, _label, _content in event.metadata:
            add(f"{event.path}/metadata/{kind.lower()}", "metadata")
        for node in event.topics:
            add(node.path, "event_topic")
        for node in event.subitems:
            add(node.path, "event_subitem")
    for path, _block_type, _content in result.content_blocks:
        add(path, "content_block")


def parse_mos_pages(pages: Iterable[object]) -> MosParseResult:
    """Parse extracted PDF pages while retaining page boundaries and context."""
    page_lines: list[tuple[int, int, str]] = []
    for page in pages:
        page_number = int(getattr(page, "page_number"))
        normalized_page = normalize_text(getattr(page, "text"))
        for line_index, raw_line in enumerate(normalized_page.splitlines()):
            line = raw_line.strip()
            if line and not _is_page_furniture(line):
                page_lines.append((page_number, line_index, line))
    lines = [line for _page, _index, line in page_lines]
    toc_topic_keys = _toc_topic_keys(lines)
    toc_event_keys = _toc_event_keys(lines)
    toc_event_codes = _toc_event_codes(lines) | {
        code for code, _title in toc_event_keys
    }
    result = MosParseResult()
    chapter = "I"
    current_event: ParsedEvent | None = None
    current_block: tuple[str, list[str], str] | None = None
    current_owner = "MOS/CapI"
    event_region = "BODY"
    event_numbers: set[str] = set()
    event_last_at_depth: dict[int, str] = {}
    event_titles: dict[str, set[str]] = {}

    def append_content(path_owner: str, content: str) -> None:
        result.content_blocks.append(
            (
                f"{path_owner}/content/{len(result.content_blocks) + 1}",
                "PARAGRAPH",
                content,
            )
        )

    def extract_references(content: str, owner: str) -> None:
        for kind, pattern in REFERENCE_PATTERNS:
            for match in pattern.finditer(content):
                result.references.append((kind, match.group(0), "D2", owner))

    body_lines = list(_body_page_lines(page_lines))
    for body_index, (page_number, line_index, line) in enumerate(body_lines):
        if not line:
            continue
        chapter_match = _chapter_heading(line)
        if chapter_match:
            chapter = chapter_match.group(1).upper()
            current_event = None
            current_block = None
            current_owner = f"MOS/Cap{chapter}"
            event_region = "BODY"
            continue
        event_match = re.match(r"^(S-\d{4})\b(?:\s*[-–:]?\s*(.*))?$", line)
        if (
            chapter == "III"
            and event_match
            and (not toc_event_codes or event_match.group(1) in toc_event_codes)
            and _looks_like_event_heading(body_lines, body_index)
        ):
            event_title = event_match.group(2) or event_match.group(1)
            current_event = ParsedEvent(
                event_match.group(1),
                event_title,
                _event_path(event_match.group(1), event_title, event_titles),
            )
            result.events.append(current_event)
            current_block = None
            current_owner = current_event.path
            event_region = "BODY"
            event_numbers = set()
            event_last_at_depth = {}
            continue
        metadata = _metadata_label(line) if current_event else None
        if metadata:
            if current_block:
                current_event.metadata.append(
                    (
                        current_block[0],
                        current_block[2],
                        "\n".join(current_block[1]).strip(),
                    )
                )
            kind, label, inline_content = metadata
            current_block = (kind, [inline_content] if inline_content else [], label)
            current_owner = f"{current_event.path}/metadata/{kind.lower()}"
            event_region = "METADATA"
            if inline_content:
                extract_references(inline_content, current_owner)
            continue
        if current_event and _is_additional_information(line):
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
            event_region = "ADDITIONAL"
            continue
        # Metadata owns every line until an explicit region marker closes it.
        # In particular, a numeric list must not steal ownership as a topic.
        if current_block:
            current_block[1].append(line)
            extract_references(line, current_owner)
            continue
        number_match = re.match(r"^(\d+(?:\.\d+)*)(\.)?\s*(.*)$", line)
        if number_match:
            number, terminal_dot, title = number_match.groups()
            if current_event:
                depth = number.count(".") + 1
                candidate_kind = classify_event_numeric_candidate(
                    NumericCandidate(
                        page_number, line_index, line, number, bool(terminal_dot), title
                    ),
                    region=event_region,
                    metadata_open=False,
                    accepted_numbers=event_numbers,
                    last_number_at_depth=event_last_at_depth.get(depth),
                )
                if candidate_kind not in {
                    NumericCandidateKind.STRUCTURAL_TOPIC,
                    NumericCandidateKind.STRUCTURAL_SUBITEM,
                }:
                    append_content(current_owner, line)
                    extract_references(line, current_owner)
                    continue
            topic_key = (chapter, number, re.sub(r"\s+", " ", title).casefold())
            if not current_event and (
                not terminal_dot or (toc_topic_keys and topic_key not in toc_topic_keys)
            ):
                result.content_blocks.append(
                    (
                        f"MOS/Cap{chapter}/content/{len(result.content_blocks) + 1}",
                        "PARAGRAPH",
                        line,
                    )
                )
                continue
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
                event_numbers.add(number)
                event_last_at_depth[depth] = number
                for child_depth in tuple(event_last_at_depth):
                    if child_depth > depth:
                        del event_last_at_depth[child_depth]
            else:
                node.path = f"MOS/Cap{chapter}/{number}"
                result.topics.append(node)
                current_owner = node.path
            extract_references(line, current_owner)
            continue
        append_content(current_owner if current_event else f"MOS/Cap{chapter}", line)
        extract_references(line, current_owner)
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
    validate_mos_structure(result)
    return result


def parse_mos_text(text: str) -> MosParseResult:
    """Compatibility wrapper for unit fixtures without PDF page objects."""

    @dataclass(frozen=True)
    class _TextPage:
        page_number: int
        text: str

    return parse_mos_pages([_TextPage(1, text)])


def new_id() -> str:
    return str(uuid.uuid4())
