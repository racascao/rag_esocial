import re
from dataclasses import dataclass, field
from html.parser import HTMLParser


@dataclass
class LayoutReference:
    kind: str
    raw_value: str
    owner_path: str


@dataclass
class ParsedLayoutField:
    name: str
    path: str
    attrs: dict[str, str]
    description: str


@dataclass
class ParsedLayoutGroup:
    name: str
    path: str
    level: int
    attrs: dict[str, str]
    description: str
    fields: list[ParsedLayoutField] = field(default_factory=list)
    children: list["ParsedLayoutGroup"] = field(default_factory=list)


@dataclass
class ParsedLayoutEvent:
    code: str
    title: str
    path: str
    groups: list[ParsedLayoutGroup] = field(default_factory=list)


@dataclass
class LayoutParseResult:
    events: list[ParsedLayoutEvent] = field(default_factory=list)
    references: list[LayoutReference] = field(default_factory=list)
    diagnostics: list[str] = field(default_factory=list)


class _LayoutHTMLParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.result = LayoutParseResult()
        self.current_event = None
        self.group_stack: list[ParsedLayoutGroup] = []
        self.current_field = None
        self.text_parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        kind = values.get("data-kind")
        if kind == "event":
            code = values.get("code", "")
            if not re.fullmatch(r"S-\d{4}", code):
                self.result.diagnostics.append(f"invalid event code: {code}")
                return
            self.current_event = ParsedLayoutEvent(
                code, values.get("title", code), f"LAYOUT/{code}"
            )
            self.result.events.append(self.current_event)
        elif kind == "group" and self.current_event:
            name = values.get("name", "")
            level = int(values.get("level", str(len(self.group_stack) + 1)))
            parent = (
                self.group_stack[-1]
                if self.group_stack and level > self.group_stack[-1].level
                else None
            )
            while self.group_stack and self.group_stack[-1].level >= level:
                self.group_stack.pop()
            parent = self.group_stack[-1] if self.group_stack else None
            path = (
                f"{parent.path}/{name}"
                if parent
                else f"{self.current_event.path}/{name}"
            )
            group = ParsedLayoutGroup(
                name, path, level, values, values.get("description", "")
            )
            (parent.children if parent else self.current_event.groups).append(group)
            self.group_stack.append(group)
        elif kind == "field" and self.group_stack:
            name = values.get("name", "")
            group = self.group_stack[-1]
            self.current_field = ParsedLayoutField(
                name, f"{group.path}/{name}", values, values.get("description", "")
            )
            group.fields.append(self.current_field)

    def handle_data(self, data):
        self.text_parts.append(data)

    def handle_endtag(self, tag):
        if tag in {"p", "td", "div"} and self.text_parts:
            text = " ".join("".join(self.text_parts).split())
            owner = (
                self.current_field.path
                if self.current_field
                else self.group_stack[-1].path
                if self.group_stack
                else self.current_event.path
                if self.current_event
                else "LAYOUT"
            )
            for pattern, kind in [
                (r"\bREGRA_[A-Z0-9_]+\b", "RULE_REFERENCE"),
                (r"\bTabela\s+\d+\b", "DOMAIN_TABLE_REFERENCE"),
                (r"\bS-\d{4}\b", "EVENT_CODE"),
                (r"\bVer:\s*[^.]+", "LOCAL_REUSE_REFERENCE"),
            ]:
                for match in re.finditer(pattern, text, re.I):
                    self.result.references.append(
                        LayoutReference(kind, match.group(0), owner)
                    )
            self.text_parts = []


def parse_layout_html(html: str) -> LayoutParseResult:
    parser = _LayoutHTMLParser()
    parser.feed(html)
    return parser.result
