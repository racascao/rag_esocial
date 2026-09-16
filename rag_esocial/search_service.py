import re
import uuid
from datetime import datetime, timezone

from sqlalchemy import select, text

from .identity import parser_config_digest
from .models.build import CitationTarget, CorpusBuildCitationTarget
from .models.layout import LayoutDocument, LayoutEvent, LayoutField, LayoutGroup
from .models.mos import MosDocument, MosEventSection, MosEventSubitem, MosTopic
from .models.search import SearchProjection, SearchUnit, SearchUnitCitationTarget
from .models.xsd import XsdElement, XsdEventSchema, XsdPackageDocument, XsdSharedType

PROFILES = (
    "MOS_EVENT_SECTION",
    "MOS_TOPIC",
    "MOS_SUBITEM",
    "LAYOUT_EVENT",
    "LAYOUT_GROUP",
    "LAYOUT_FIELD",
    "XSD_EVENT_SCHEMA",
    "XSD_ELEMENT",
    "XSD_SHARED_TYPE",
)


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


def _rows(session, build, profile):
    if profile == "MOS_EVENT_SECTION":
        return [
            ("MOS", x.source_local_stable_path, f"{x.event_code} {x.title}")
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
            ("MOS", x.source_local_stable_path, f"{x.number} {x.title or ''}")
            for x in session.scalars(
                select(MosEventSubitem)
                .join(MosEventSection)
                .join(MosDocument)
                .where(MosDocument.corpus_build_id == build.id)
            ).all()
        ]
    if profile == "LAYOUT_EVENT":
        return [
            ("LAYOUT", x.source_local_stable_path, f"{x.event_code} {x.title or ''}")
            for x in session.scalars(
                select(LayoutEvent)
                .join(LayoutDocument)
                .where(LayoutDocument.corpus_build_id == build.id)
            ).all()
        ]
    if profile == "LAYOUT_GROUP":
        return [
            (
                "LAYOUT",
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
        return [
            (
                "LAYOUT",
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
        return [
            (
                "XSD",
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
            x.source_local_stable_path,
            f"{x.name} {x.base_qname or ''} {x.documentation or ''}",
        )
        for x in session.scalars(
            select(XsdSharedType)
            .join(XsdPackageDocument)
            .where(XsdPackageDocument.corpus_build_id == build.id)
        ).all()
    ]


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
        return projection, False
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
    for family, path, body in _rows(session, build, profile):
        target = _target(session, build, path)
        if not target:
            continue
        terms = technical_tokens(f"{path} {body}")
        unit = SearchUnit(
            id=str(uuid.uuid4()),
            search_projection_id=projection.id,
            document_family=family,
            unit_kind=profile,
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
    return projection, True


def search(session, projection, query, limit=20):
    if not query.strip():
        return []
    stmt = text(
        "SELECT id, source_local_stable_path, title, "
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
