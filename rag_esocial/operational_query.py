"""Deterministic analysis of public, lexical corpus questions."""

import re
import unicodedata
from dataclasses import dataclass


def _fold(value: str) -> str:
    return "".join(
        char
        for char in unicodedata.normalize("NFKD", value.casefold())
        if not unicodedata.combining(char)
    )


# These are names of persisted schema attributes/relations, not question templates.
ATTRIBUTE_ALIASES = {
    "occurrence": {"ocorrencia", "ocorre", "cardinalidade", "minoccurs", "maxoccurs"},
    "condition": {"condicao"},
    "description": {"descricao"},
    "type": {"tipo"},
    "size": {"tamanho"},
    "decimals": {"decimais"},
    "pattern": {"padrao", "pattern"},
    "enum": {"enum", "enumeracao", "enumeracoes", "valores"},
    "parent": {"pai"},
    "children": {"filho", "filhos", "campo", "campos", "elemento", "elementos"},
}
_STOPWORDS = frozenset(
    "qual quais quem que o a os as um uma de do da dos das e em no na nos nas "
    "ao aos para por como pertence pertencem existe existem dentro disponivel "
    "disponiveis sobre evento eventos grupo grupos".split()
)
_ORCHESTRATION = frozenset(
    (
        "compare comparar comparacao evidencias evidencia fontes fonte "
        "mos leiaute layout xsd"
    ).split()
)
_EVENT = re.compile(r"S-\d{4}\b", re.I)
_TOKEN = re.compile(r"[\w:-]+", re.UNICODE)


@dataclass(frozen=True)
class QueryIntent:
    normalized_text: str
    event_codes: tuple[str, ...]
    technical_tokens: tuple[str, ...]
    requested_attributes: tuple[str, ...]
    relationship: str | None
    requested_families: tuple[str, ...]
    factual_terms: tuple[str, ...]
    object_kind: str | None


def analyze_query(question: str, known_names=()) -> QueryIntent:
    tokens = _TOKEN.findall(question)
    folded = [_fold(token) for token in tokens]
    events = tuple(
        dict.fromkeys(match.group(0).upper() for match in _EVENT.finditer(question))
    )
    known = {_fold(name): name for name in known_names}
    technical = tuple(
        dict.fromkeys(
            known[t]
            for t in folded
            if t in known
            and t not in _STOPWORDS
            and t not in _ORCHESTRATION
            and not _EVENT.fullmatch(t.upper())
            and not any(t in aliases for aliases in ATTRIBUTE_ALIASES.values())
        )
    )
    attributes = tuple(
        key
        for key, aliases in ATTRIBUTE_ALIASES.items()
        if key not in {"children", "parent"}
        if any(token in aliases for token in folded)
    )
    families = tuple(
        family
        for family, aliases in (
            ("MOS", {"mos"}),
            ("LAYOUT", {"leiaute", "layout"}),
            ("XSD", {"xsd"}),
        )
        if any(token in aliases for token in folded)
    )
    children_words = {"filho", "filhos"}
    plural_objects = {"campos", "elementos"}
    relationship = (
        "CHILDREN"
        if any(token in children_words for token in folded)
        or (
            any(token in plural_objects for token in folded)
            and any(
                token in {"grupo", "grupos", "pertencem", "dentro"} for token in folded
            )
        )
        else "PARENT"
        if "pai" in folded
        else None
    )
    if relationship:
        attributes += (relationship.casefold(),)
    object_kind = (
        "FIELD"
        if any(t in {"campo", "campos"} for t in folded)
        else "ELEMENT"
        if any(t in {"elemento", "elementos"} for t in folded)
        else "GROUP"
        if any(t in {"grupo", "grupos"} for t in folded)
        else None
    )
    factual = tuple(
        token
        for token, fold in zip(tokens, folded)
        if fold not in _STOPWORDS
        and fold not in _ORCHESTRATION
        and not any(fold in aliases for aliases in ATTRIBUTE_ALIASES.values())
    )
    return QueryIntent(
        normalized_text=" ".join(factual),
        event_codes=events,
        technical_tokens=technical,
        requested_attributes=attributes,
        relationship=relationship,
        requested_families=families,
        factual_terms=factual,
        object_kind=object_kind,
    )
