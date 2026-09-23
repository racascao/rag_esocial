import re
import uuid
from datetime import datetime, timezone

from sqlalchemy import delete, select, text

from .identity import canonical_json, parser_config_digest
from .models.build import CitationTarget, CorpusBuildCitationTarget
from .models.layout import LayoutDocument, LayoutEvent, LayoutField, LayoutGroup
from .models.mos import (
    EventMetadataBlock,
    MosDocument,
    MosEventSection,
    MosEventSubitem,
    MosEventTopic,
    MosTopic,
)
from .models.search import SearchProjection, SearchUnit, SearchUnitCitationTarget
from .models.xsd import XsdElement, XsdEventSchema, XsdPackageDocument, XsdSharedType
from .runtime_defaults import DEFAULT_SEARCH_REVISION

PROFILES = (
    "MOS_EVENT_SECTION",
    "MOS_EVENT_METADATA",
    "MOS_EVENT_TOPIC",
    "MOS_TOPIC",
    "MOS_SUBITEM",
    "LAYOUT_EVENT",
    "LAYOUT_GROUP",
    "LAYOUT_FIELD",
    "XSD_EVENT_SCHEMA",
    "XSD_ELEMENT",
    "XSD_SHARED_TYPE",
    "MOS_ALL",
    "LAYOUT_ALL",
    "XSD_ALL",
)

FAMILY_PROFILES = {
    "MOS_ALL": (
        "MOS_EVENT_SECTION",
        "MOS_EVENT_METADATA",
        "MOS_EVENT_TOPIC",
        "MOS_TOPIC",
        "MOS_SUBITEM",
    ),
    "LAYOUT_ALL": ("LAYOUT_EVENT", "LAYOUT_GROUP", "LAYOUT_FIELD"),
    "XSD_ALL": ("XSD_EVENT_SCHEMA", "XSD_ELEMENT", "XSD_SHARED_TYPE"),
}


def technical_tokens(value):
    words = re.findall(r"[A-Za-z0-9_:-]+", value or "")
    expanded = []
    for word in words:
        expanded += [word, word.replace("-", ""), word.split(":")[-1]]
    return " ".join(dict.fromkeys(x for x in expanded if x))


def _target(session, build, path):
    return session.scalar(
        select(CitationTarget)
        .join(CorpusBuildCitationTarget)
        .where(
            CorpusBuildCitationTarget.build_id == build.id,
            CitationTarget.source_local_stable_path == path,
        )
    )


def _rows(session, build, profile, revision=None):
    if profile in FAMILY_PROFILES:
        return [
            (family, kind, path, body)
            for kind in FAMILY_PROFILES[profile]
            for family, _, path, body in _rows(session, build, kind, revision)
        ]
    if profile == "MOS_EVENT_METADATA":
        return [
            (
                "MOS",
                profile,
                x.source_local_stable_path,
                f"{section.event_code} {x.original_label} {x.content}",
            )
            for x, section in session.execute(
                select(EventMetadataBlock, MosEventSection)
                .join(MosEventSection)
                .join(MosDocument)
                .where(MosDocument.corpus_build_id == build.id)
            ).all()
        ]
    if profile == "MOS_EVENT_TOPIC":
        return [
            (
                "MOS",
                profile,
                x.source_local_stable_path,
                f"{section.event_code} {x.number} {x.title or ''}",
            )
            for x, section in session.execute(
                select(MosEventTopic, MosEventSection)
                .join(MosEventSection)
                .join(MosDocument)
                .where(MosDocument.corpus_build_id == build.id)
            ).all()
        ]
    if profile == "MOS_EVENT_SECTION":
        return [
            ("MOS", profile, x.source_local_stable_path, f"{x.event_code} {x.title}")
            for x in session.scalars(
                select(MosEventSection)
                .join(MosDocument)
                .where(MosDocument.corpus_build_id == build.id)
            ).all()
        ]
    if profile == "MOS_TOPIC":
        return [
            (
                "MOS",
                profile,
                x.source_local_stable_path,
                f"{x.number} {x.title or ''} {x.content or ''}",
            )
            for x in session.scalars(
                select(MosTopic)
                .join(MosDocument)
                .where(MosDocument.corpus_build_id == build.id)
            ).all()
        ]
    if profile == "MOS_SUBITEM":
        return [
            ("MOS", profile, x.source_local_stable_path, f"{x.number} {x.title or ''}")
            for x in session.scalars(
                select(MosEventSubitem)
                .join(MosEventSection)
                .join(MosDocument)
                .where(MosDocument.corpus_build_id == build.id)
            ).all()
        ]
    if profile == "LAYOUT_EVENT":
        return [
            (
                "LAYOUT",
                profile,
                x.source_local_stable_path,
                f"{x.event_code} {x.title or ''}",
            )
            for x in session.scalars(
                select(LayoutEvent)
                .join(LayoutDocument)
                .where(LayoutDocument.corpus_build_id == build.id)
            ).all()
        ]
    if profile == "LAYOUT_GROUP":
        if revision == "fts-baseline-v3":
            return [
                (
                    "LAYOUT",
                    profile,
                    group.source_local_stable_path,
                    " ".join(
                        (
                            f"evento {event.event_code}",
                            f"grupo {group.technical_name}",
                            f"caminho {group.source_local_stable_path}",
                            f"nivel {group.level}",
                            f"descricao {group.description or ''}",
                            f"ocorrencia {group.occurrence or ''}",
                            f"condicao {group.condition or ''}",
                        )
                    ),
                )
                for group, event in session.execute(
                    select(LayoutGroup, LayoutEvent)
                    .select_from(LayoutGroup)
                    .join(LayoutEvent, LayoutGroup.layout_event_id == LayoutEvent.id)
                    .join(LayoutDocument)
                    .where(LayoutDocument.corpus_build_id == build.id)
                ).all()
            ]
        return [
            (
                "LAYOUT",
                profile,
                x.source_local_stable_path,
                f"{x.technical_name} {x.description or ''} {x.condition or ''}",
            )
            for x in session.scalars(
                select(LayoutGroup)
                .join(LayoutEvent)
                .join(LayoutDocument)
                .where(LayoutDocument.corpus_build_id == build.id)
            ).all()
        ]
    if profile == "LAYOUT_FIELD":
        if revision == "fts-baseline-v3":
            return [
                (
                    "LAYOUT",
                    profile,
                    item.source_local_stable_path,
                    " ".join(
                        (
                            f"evento {event.event_code}",
                            f"campo {item.technical_name}",
                            f"grupo_pai {group.technical_name}",
                            f"caminho {item.source_local_stable_path}",
                            f"tipo {item.field_type or ''}",
                            f"ocorrencia {item.occurrence or ''}",
                            f"tamanho {item.size or ''}",
                            f"decimais {item.decimals or ''}",
                            f"descricao {item.description or ''}",
                        )
                    ),
                )
                for item, group, event in session.execute(
                    select(LayoutField, LayoutGroup, LayoutEvent)
                    .select_from(LayoutField)
                    .join(LayoutGroup, LayoutField.layout_group_id == LayoutGroup.id)
                    .join(LayoutEvent, LayoutGroup.layout_event_id == LayoutEvent.id)
                    .join(LayoutDocument)
                    .where(LayoutDocument.corpus_build_id == build.id)
                ).all()
            ]
        return [
            (
                "LAYOUT",
                profile,
                x.source_local_stable_path,
                f"{x.technical_name} {x.description or ''} "
                f"{x.field_type or ''} {x.condition or ''}",
            )
            for x in session.scalars(
                select(LayoutField)
                .join(LayoutGroup)
                .join(LayoutEvent)
                .join(LayoutDocument)
                .where(LayoutDocument.corpus_build_id == build.id)
            ).all()
        ]
    if profile == "XSD_EVENT_SCHEMA":
        return [
            (
                "XSD",
                profile,
                x.source_local_stable_path,
                f"{x.schema_key} {x.target_namespace or ''} {x.documentation or ''}",
            )
            for x in session.scalars(
                select(XsdEventSchema)
                .join(XsdPackageDocument)
                .where(XsdPackageDocument.corpus_build_id == build.id)
            ).all()
        ]
    if profile == "XSD_ELEMENT":
        if revision == "fts-baseline-v3":
            return [
                (
                    "XSD",
                    profile,
                    x.source_local_stable_path,
                    " ".join(
                        (
                            f"elemento {x.name}",
                            f"caminho {x.source_local_stable_path}",
                            f"tipo {x.type_qname or ''}",
                            f"referencia {x.ref_qname or ''}",
                            f"minOccurs {x.min_occurs or ''}",
                            f"maxOccurs {x.max_occurs or ''}",
                            f"facets {canonical_json(x.facets or {})}",
                            f"descricao {x.documentation or ''}",
                        )
                    ),
                )
                for x in session.scalars(
                    select(XsdElement)
                    .join(XsdPackageDocument)
                    .where(XsdPackageDocument.corpus_build_id == build.id)
                ).all()
            ]
        return [
            (
                "XSD",
                profile,
                x.source_local_stable_path,
                f"{x.name} {x.type_qname or ''} {x.documentation or ''}",
            )
            for x in session.scalars(
                select(XsdElement)
                .join(XsdPackageDocument)
                .where(XsdPackageDocument.corpus_build_id == build.id)
            ).all()
        ]
    return [
        (
            "XSD",
            profile,
            x.source_local_stable_path,
            f"{x.name} {x.base_qname or ''} {x.documentation or ''}",
        )
        for x in session.scalars(
            select(XsdSharedType)
            .join(XsdPackageDocument)
            .where(XsdPackageDocument.corpus_build_id == build.id)
        ).all()
    ]


def projection_complete(session, build, projection):
    expected = {
        (kind, path): body
        for _, kind, path, body in _rows(
            session, build, projection.profile, projection.projection_revision
        )
    }
    if not expected and projection.profile in FAMILY_PROFILES:
        return False
    actual = session.execute(
        select(
            SearchUnit.id,
            SearchUnit.unit_kind,
            SearchUnit.source_local_stable_path,
            SearchUnit.root_citation_target_id,
            SearchUnit.search_text,
            SearchUnit.technical_terms,
        ).where(SearchUnit.search_projection_id == projection.id)
    ).all()
    if len(actual) != len(expected) or {
        (kind, path) for _, kind, path, _, _, _ in actual
    } != set(expected):
        return False
    targets = dict(
        session.execute(
            select(CitationTarget.source_local_stable_path, CitationTarget.id)
            .join(CorpusBuildCitationTarget)
            .where(CorpusBuildCitationTarget.build_id == build.id)
        ).all()
    )
    links = set(
        session.execute(
            select(
                SearchUnitCitationTarget.search_unit_id,
                SearchUnitCitationTarget.citation_target_id,
            ).where(
                SearchUnitCitationTarget.search_unit_id.in_(
                    select(SearchUnit.id).where(
                        SearchUnit.search_projection_id == projection.id
                    )
                ),
                SearchUnitCitationTarget.role == "ROOT",
            )
        ).all()
    )
    return all(
        targets.get(path) == target_id
        and (unit_id, target_id) in links
        and body == expected[(kind, path)]
        and terms == technical_tokens(f"{path} {body}")
        for unit_id, kind, path, target_id, body, terms in actual
    )


def materialize_projection(
    session, build, profile, revision="fts-baseline-v1", config=None
):
    if profile not in PROFILES:
        raise ValueError("unknown search profile")
    config = config or {}
    digest = parser_config_digest(config)
    projection = session.scalar(
        select(SearchProjection).where(
            SearchProjection.corpus_build_id == build.id,
            SearchProjection.profile == profile,
            SearchProjection.projection_revision == revision,
            SearchProjection.projection_config_digest == digest,
        )
    )
    if projection:
        if projection_complete(session, build, projection):
            return projection, False
        if (
            build.status != "DRAFT"
            and projection.projection_revision != DEFAULT_SEARCH_REVISION
        ):
            raise ValueError("incomplete projection in non-DRAFT build")
    with session.begin_nested():
        projection = _rebuild_projection(
            session, build, profile, revision, config, digest, projection
        )
        if not projection_complete(session, build, projection):
            raise ValueError(f"incomplete projection for {profile}")
    return projection, True


def _rebuild_projection(session, build, profile, revision, config, digest, projection):
    if projection:
        unit_ids = select(SearchUnit.id).where(
            SearchUnit.search_projection_id == projection.id
        )
        session.execute(
            delete(SearchUnitCitationTarget).where(
                SearchUnitCitationTarget.search_unit_id.in_(unit_ids)
            )
        )
        session.execute(
            delete(SearchUnit).where(SearchUnit.search_projection_id == projection.id)
        )
        session.flush()
    if not projection:
        projection = SearchProjection(
            id=str(uuid.uuid4()),
            corpus_build_id=build.id,
            profile=profile,
            projection_revision=revision,
            projection_config=config,
            projection_config_digest=digest,
            text_search_config="simple",
            created_at=datetime.now(timezone.utc),
        )
        session.add(projection)
        session.flush()
    rows = _rows(session, build, profile, revision)
    for family, kind, path, body in rows:
        target = _target(session, build, path)
        if not target:
            raise ValueError(f"missing CitationTarget for {path}")
        terms = technical_tokens(f"{path} {body}")
        unit = SearchUnit(
            id=str(uuid.uuid4()),
            search_projection_id=projection.id,
            document_family=family,
            unit_kind=kind,
            root_citation_target_id=target.id,
            canonical_entity_id=None,
            source_local_stable_path=path,
            title=body[:500],
            search_text=body,
            technical_terms=terms,
            deterministic_key=path,
            search_vector="",
        )
        session.add(unit)
        session.flush()
        session.execute(
            text(
                "UPDATE search_units SET search_vector = "
                "setweight(to_tsvector('simple', :terms), 'A') || "
                "setweight(to_tsvector('simple', :body), 'B') WHERE id = :id"
            ),
            {"terms": terms, "body": body, "id": unit.id},
        )
        session.add(
            SearchUnitCitationTarget(
                search_unit_id=unit.id, citation_target_id=target.id, role="ROOT"
            )
        )
    session.flush()
    return projection


def search(session, projection, query, limit=20):
    if (
        projection.projection_revision == "fts-baseline-v3"
        and projection.profile in FAMILY_PROFILES
    ):
        from .operational_retrieval import operational_search

        return operational_search(session, projection, query, limit)
    query = normalize_query(query)
    if not query:
        return []
    stmt = text(
        "SELECT id, source_local_stable_path, title, document_family, "
        "unit_kind, search_text, "
        "ts_rank_cd(search_vector, websearch_to_tsquery('simple', :query)) AS score "
        "FROM search_units WHERE search_projection_id=:projection "
        "AND search_vector @@ websearch_to_tsquery('simple', :query) "
        "ORDER BY score DESC, source_local_stable_path ASC LIMIT :limit"
    )
    return (
        session.execute(
            stmt, {"query": query, "projection": projection.id, "limit": limit}
        )
        .mappings()
        .all()
    )


_QUESTION_STOPWORDS = frozenset(
    (
        "qual quais quem que o a os as um uma de do da dos das é e em "
        "no na nos nas ao aos para por como evento eventos campo campos "
        "grupo grupos elemento elementos filho filhos pertence pertencem "
        "existe existem xsd"
    ).split()
)


def normalize_query(query):
    tokens = re.findall(r"[\w:-]+", query, re.UNICODE)
    return " ".join(
        token for token in tokens if token.casefold() not in _QUESTION_STOPWORDS
    )
