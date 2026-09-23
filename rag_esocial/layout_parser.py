import re
from dataclasses import dataclass, field
from html.parser import HTMLParser


@dataclass
class LayoutReference:
    kind: str
    raw_value: str
    owner_path: str
    normalized_value: str | None = None


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
            # Text outside a parsed event has no structural owner and cannot
            # become authorized evidence. Do not manufacture a root target.
            if owner == "LAYOUT":
                self.text_parts = []
                return
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
    if 'data-kind="event"' not in html and "data-kind='event'" not in html:
        return _parse_official_html(html)
    parser = _LayoutHTMLParser()
    parser.feed(html)
    return parser.result


class LayoutStructureError(ValueError):
    """The official tables cannot be mapped to unique structural identities."""


class _OfficialTables(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables = []
        self.heading = None
        self.heading_parts = None
        self.table = None
        self.row = None
        self.cell = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "h3":
            self.heading_parts = []
        elif tag == "table":
            classes = set(attrs.get("class", "").split())
            if classes & {"resumo", "completo"}:
                self.table = {"classes": classes, "heading": self.heading, "rows": []}
        elif tag == "tr" and self.table is not None:
            self.row = []
        elif tag in {"td", "th"} and self.row is not None:
            self.cell = {"text": [], "attrs": attrs, "hrefs": []}
        elif tag == "a" and self.cell is not None and attrs.get("href"):
            self.cell["hrefs"].append(attrs["href"])
        elif tag == "br" and self.cell is not None:
            self.cell["text"].append(" ")

    def handle_data(self, data):
        if self.heading_parts is not None:
            self.heading_parts.append(data)
        if self.cell is not None:
            self.cell["text"].append(data)

    def handle_endtag(self, tag):
        if tag == "h3" and self.heading_parts is not None:
            self.heading = " ".join("".join(self.heading_parts).split())
            self.heading_parts = None
        elif tag in {"td", "th"} and self.cell is not None:
            self.cell["text"] = " ".join("".join(self.cell["text"]).split())
            self.row.append(self.cell)
            self.cell = None
        elif tag == "tr" and self.row is not None:
            self.table["rows"].append(self.row)
            self.row = None
        elif tag == "table" and self.table is not None:
            self.tables.append(self.table)
            self.table = None


def _references(text, owner, hrefs=()):
    result = []
    for pattern, kind in (
        (r"\bREGRA_[A-Z0-9_]+\b", "RULE_REFERENCE"),
        (r"\bTabela\s+\d+\b", "DOMAIN_TABLE_REFERENCE"),
        (r"\bS-\d{4}\b", "EVENT_CODE"),
        (r"\bVer:\s*[^.]+", "LOCAL_REUSE_REFERENCE"),
    ):
        for match in re.finditer(pattern, text, re.I):
            raw = match.group(0).strip()
            fragment = next(
                (
                    h
                    for h in reversed(hrefs)
                    if re.fullmatch(r"#(?:r_)?\d{4}(?:_[A-Za-z0-9_]+)?", h)
                ),
                None,
            )
            result.append(
                LayoutReference(
                    kind,
                    raw,
                    owner,
                    fragment if kind == "LOCAL_REUSE_REFERENCE" else None,
                )
            )
    return result


def _table_code(table, kind):
    ids = []
    for row in table["rows"]:
        if not row:
            continue
        selector = row[0]["attrs"].get("id") or row[0]["attrs"].get("title", "")
        match = re.fullmatch(r"(?:r_)?(\d{4})(?:_.*)?", selector)
        if match:
            ids.append(match.group(1))
    codes = set(ids)
    heading = re.search(r"\bS-(\d{4})\b", table["heading"] or "")
    if len(codes) != 1 or (heading and heading.group(1) not in codes):
        raise LayoutStructureError(f"{kind}: heading/row event code ambiguous: {codes}")
    return codes.pop()


def _parse_official_html(html):
    collector = _OfficialTables()
    collector.feed(html)
    pairs = {}
    for table in collector.tables:
        header_rows = [
            [cell["text"].casefold() for cell in row] for row in table["rows"]
        ]
        headers = next((row for row in header_rows if "grupo pai" in row), [])
        if {"grupo", "grupo pai", "nível", "chave"} <= set(
            headers
        ) and "resumo" in table["classes"]:
            kind = "resumo"
        elif {"grupo/campo", "grupo pai", "elem.", "tipo"} <= set(
            headers
        ) and "completo" in table["classes"]:
            kind = "completo"
        else:
            raise LayoutStructureError(f"unrecognized official layout table: {headers}")
        table["rows"] = table["rows"][header_rows.index(headers) :]
        code = _table_code(table, kind)
        if kind in pairs.setdefault(code, {}):
            raise LayoutStructureError(f"duplicate {kind} table for S-{code}")
        pairs[code][kind] = table
    if not pairs:
        raise LayoutStructureError("official layout has no event tables")
    result = LayoutParseResult()
    for code, tables in pairs.items():
        if set(tables) != {"resumo", "completo"}:
            raise LayoutStructureError(f"unpaired layout tables for S-{code}")
        heading = tables["resumo"]["heading"] or tables["completo"]["heading"] or ""
        title = re.sub(r"^S-\d{4}\s*[-–]\s*", "", heading).strip() or f"S-{code}"
        event = ParsedLayoutEvent(f"S-{code}", title, f"LAYOUT/S-{code}")
        result.events.append(event)
        summary = {}
        for row in tables["resumo"]["rows"][1:]:
            if len(row) < 7:
                continue
            selector = row[0]["attrs"].get("id", "")
            if row[0]["text"] == "..." or row[0]["text"].startswith("..."):
                continue
            if selector:
                if not selector.startswith(f"r_{code}") or selector in summary:
                    raise LayoutStructureError(
                        f"invalid/duplicate summary identity: {selector}"
                    )
                summary[selector] = row
        nodes = {}
        pending = []
        reuse_rows = []
        last_selector = None
        for row in tables["completo"]["rows"][1:]:
            if len(row) < 9:
                continue
            if row[0]["text"] == "...":
                reuse_rows.append((last_selector, row[8]))
                continue
            selector = row[0]["attrs"].get("id") or row[0]["attrs"].get("title", "")
            if not selector or not re.fullmatch(
                rf"{code}(?:_[A-Za-z0-9_]+)?", selector
            ):
                raise LayoutStructureError(f"invalid complete identity: {selector}")
            if selector in nodes:
                raise LayoutStructureError(f"duplicate complete identity: {selector}")
            last_selector = selector
            kind = row[3]["text"]
            if kind not in {"G", "CG", "E", "A"}:
                raise LayoutStructureError(f"unknown element kind {kind} at {selector}")
            parent_links = [h for h in row[2]["hrefs"] if h.startswith("#r_")]
            parent_id = parent_links[0][3:] if len(parent_links) == 1 else None
            if row[2]["text"] and not parent_id:
                raise LayoutStructureError(
                    f"missing structural parent link at {selector}"
                )
            summary_row = summary.get(f"r_{selector}")
            attrs = {
                "type": row[4]["text"],
                "occurrence": row[5]["text"],
                "size": row[6]["text"],
                "decimals": row[7]["text"],
            }
            if summary_row:
                attrs.update(
                    {
                        "occurrence": summary_row[4]["text"] or attrs["occurrence"],
                        "key": summary_row[5]["text"],
                        "condition": summary_row[6]["text"],
                    }
                )
            attrs = {k: v for k, v in attrs.items() if v and v != "-"}
            nodes[selector] = (kind, row, parent_id, summary_row, attrs)
            pending.append(selector)
        if set(summary) - {f"r_{selector}" for selector in nodes}:
            raise LayoutStructureError(f"summary/complete mismatch in S-{code}")
        for selector, (_, _, parent_id, summary_row, _) in nodes.items():
            if summary_row and summary_row[1]["hrefs"]:
                summary_parents = [
                    href[3:]
                    for href in summary_row[1]["hrefs"]
                    if href.startswith("#r_")
                ]
                if summary_parents and summary_parents != [parent_id]:
                    raise LayoutStructureError(
                        f"summary/complete parent mismatch: {selector}"
                    )

        def path_for(selector, visiting=None):
            visiting = visiting or set()
            if selector in visiting or selector not in nodes:
                raise LayoutStructureError(f"cyclic/orphan layout identity: {selector}")
            kind, row, parent_id, _, _ = nodes[selector]
            if selector == code + "_eSocial":
                return event.path + "/eSocial"
            if selector == code:
                return event.path + "/" + row[1]["text"]
            if not parent_id:
                raise LayoutStructureError(f"orphan layout node: {selector}")
            parent = nodes.get(parent_id)
            if parent is None or parent[0] not in {"G", "CG"}:
                raise LayoutStructureError(f"invalid group owner: {selector}")
            prefix = (
                event.path
                if parent_id == code and kind in {"G", "CG"}
                else path_for(parent_id, visiting | {selector})
            )
            return prefix + "/" + row[1]["text"]

        groups = {}
        paths = {event.path}
        for selector in pending:
            kind, row, parent_id, summary_row, attrs = nodes[selector]
            path = path_for(selector)
            if path in paths:
                raise LayoutStructureError(f"colliding layout path: {path}")
            paths.add(path)
            description = row[8]["text"]
            if kind in {"G", "CG"}:
                level = (
                    int(summary_row[2]["text"])
                    if summary_row and summary_row[2]["text"].isdigit()
                    else len(path.split("/")) - 2
                )
                groups[selector] = ParsedLayoutGroup(
                    row[1]["text"], path, level, attrs, description
                )
            else:
                if not parent_id or parent_id not in groups:
                    # Parent can occur later in an out-of-order table.
                    continue
            result.references.extend(_references(description, path, row[8]["hrefs"]))
        for selector in pending:
            kind, row, parent_id, summary_row, attrs = nodes[selector]
            path = path_for(selector)
            if kind in {"G", "CG"}:
                if parent_id in groups and parent_id not in {code, code + "_eSocial"}:
                    groups[parent_id].children.append(groups[selector])
                else:
                    event.groups.append(groups[selector])
                if summary_row:
                    result.references.extend(
                        _references(
                            " ".join(c["text"] for c in summary_row[3:]),
                            path,
                            [h for c in summary_row for h in c["hrefs"]],
                        )
                    )
            else:
                if parent_id not in groups:
                    raise LayoutStructureError(f"field without group: {selector}")
                groups[parent_id].fields.append(
                    ParsedLayoutField(row[1]["text"], path, attrs, row[8]["text"])
                )
        for owner_id, cell in reuse_rows:
            if not owner_id:
                raise LayoutStructureError(f"reuse reference without owner in S-{code}")
            refs = _references(cell["text"], path_for(owner_id), cell["hrefs"])
            fragment = next(
                (href for href in reversed(cell["hrefs"]) if href.startswith("#")), None
            )
            for ref in refs:
                if ref.kind == "LOCAL_REUSE_REFERENCE":
                    ref.normalized_value = fragment
            result.references.extend(refs)
        if not groups or not any(k in {"E", "A"} for k, *_ in nodes.values()):
            raise LayoutStructureError(f"empty layout structure: S-{code}")
    seen_refs = set()
    unique_refs = []
    for ref in result.references:
        key = (ref.kind, ref.raw_value, ref.owner_path, ref.normalized_value)
        if key not in seen_refs:
            seen_refs.add(key)
            unique_refs.append(ref)
    result.references = unique_refs
    return result
