import re
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass, field
from pathlib import PurePosixPath

XS = "http://www.w3.org/2001/XMLSchema"


def q(local):
    return f"{{{XS}}}{local}"


def _active_xml_declarations(raw: bytes) -> bytes:
    """Remove comments before rejecting declarations that XML parsers may act on."""
    return re.sub(rb"<!--.*?-->", b"", raw, flags=re.DOTALL).upper()


@dataclass
class XsdNode:
    name: str
    path: str
    documentation: str | None = None
    facets: dict = field(default_factory=dict)
    type_qname: str | None = None
    ref_qname: str | None = None
    min_occurs: str | None = None
    max_occurs: str | None = None
    children: list = field(default_factory=list)
    enumerations: list = field(default_factory=list)


@dataclass
class XsdSchemaResult:
    relative_path: str
    kind: str
    target_namespace: str | None
    schema_key: str
    documentation: str | None
    elements: list[XsdNode] = field(default_factory=list)
    shared_types: list[XsdNode] = field(default_factory=list)
    references: list[tuple[str, str, str]] = field(default_factory=list)


def _doc(node):
    texts = [
        "".join(x.itertext()).strip() for x in node.findall(f".//{q('documentation')}")
    ]
    return "\n".join(x for x in texts if x) or None


def _simple(node):
    result = {}
    restriction = node.find(f"{q('restriction')}")
    if restriction is None:
        return result, []
    result["base"] = restriction.get("base")
    enums = []
    for facet in list(restriction):
        local = facet.tag.rsplit("}", 1)[-1]
        if local == "enumeration":
            enums.append((facet.get("value", ""), _doc(facet)))
        elif "value" in facet.attrib:
            result.setdefault(local, []).append(facet.get("value"))
    return result, enums


def _element(node, path):
    facets, enums = {}, []
    inline = node.find(f"{q('simpleType')}")
    if inline is not None:
        facets, enums = _simple(inline)
    item = XsdNode(
        node.get("name") or node.get("ref", ""),
        path,
        _doc(node),
        facets,
        node.get("type"),
        node.get("ref"),
        node.get("minOccurs", "1"),
        node.get("maxOccurs", "1"),
        [],
        enums,
    )
    for child in (
        node.findall(f"{q('complexType')}/{q('sequence')}/{q('element')}")
        + node.findall(f"{q('complexType')}/{q('choice')}/{q('element')}")
        + node.findall(f"{q('complexType')}/{q('all')}/{q('element')}")
    ):
        item.children.append(
            _element(child, f"{path}/{child.get('name') or child.get('ref', '')}")
        )
    if item.type_qname and ":" in item.type_qname:
        pass
    return item


def parse_xsd_package(path):
    results = []
    with zipfile.ZipFile(path) as archive:
        for name in sorted(x for x in archive.namelist() if x.lower().endswith(".xsd")):
            raw = archive.read(name)
            active = _active_xml_declarations(raw)
            if b"<!DOCTYPE" in active or b"<!ENTITY" in active:
                raise ValueError(f"external XML declaration rejected: {name}")
            root = ET.fromstring(raw)
            ns = root.get("targetNamespace")
            stem = PurePosixPath(name).stem
            has_event = any(
                e.get("name", "").startswith("evt") for e in root.findall(q("element"))
            )
            has_types = bool(
                root.findall(q("simpleType")) or root.findall(q("complexType"))
            )
            kind = (
                "EVENT_SCHEMA"
                if has_event
                else "SHARED_TYPES_SCHEMA"
                if has_types and stem.lower() == "tipos"
                else "AUXILIARY_SCHEMA"
            )
            result = XsdSchemaResult(name, kind, ns, stem, _doc(root))
            for inc in root.findall(q("include")):
                result.references.append(
                    ("SCHEMA_INCLUDE", inc.get("schemaLocation", ""), name)
                )
            for imp in root.findall(q("import")):
                result.references.append(
                    (
                        "SCHEMA_IMPORT",
                        imp.get("schemaLocation") or imp.get("namespace", ""),
                        name,
                    )
                )
            for top in root.findall(q("element")):
                result.elements.append(
                    _element(
                        top,
                        "XSD/"
                        f"{ns or 'NO_NAMESPACE'}/schema/{stem}/"
                        f"{top.get('name') or top.get('ref', '')}",
                    )
                )
            for typ in root.findall(q("simpleType")) + root.findall(q("complexType")):
                facets, enums = _simple(
                    typ.find(q("simpleContent")) or typ.find(q("restriction")) or typ
                )
                result.shared_types.append(
                    XsdNode(
                        typ.get("name", ""),
                        f"XSD/{ns or 'NO_NAMESPACE'}/shared-type/{typ.get('name', '')}",
                        _doc(typ),
                        facets,
                        facets.get("base"),
                    )
                )
                result.shared_types[-1].enumerations = enums
            results.append(result)
    return results
