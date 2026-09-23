# ruff: noqa: E501
import hashlib
import uuid
from datetime import datetime, timezone

from sqlalchemy import select, text

from .identity import parser_config_digest
from .models.build import CitationTarget, CorpusBuildCitationTarget
from .models.evidence import EvidenceSet, EvidenceSetItem, EvidenceUnit
from .models.layout import LayoutDocument, LayoutEvent, LayoutField, LayoutGroup
from .models.mos import (
    EventMetadataBlock,
    MosDocument,
    MosEventSection,
    MosEventSubitem,
    MosEventTopic,
    MosTopic,
)
from .models.xsd import (
    XsdElement,
    XsdEnumeration,
    XsdEventSchema,
    XsdPackageDocument,
    XsdSharedType,
)


def _digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def _render(session, build, target):
    path = target.source_local_stable_path
    if target.document_family == "LAYOUT":
        field = session.scalar(
            select(LayoutField)
            .join(LayoutGroup)
            .join(LayoutEvent)
            .join(LayoutDocument)
            .where(
                LayoutDocument.corpus_build_id == build.id,
                LayoutField.source_local_stable_path == path,
            )
        )
        if field:
            return f"Path: {path}\nName: {field.technical_name}\nDescription: {field.description or ''}\nType: {field.field_type or ''}\nOccurrence: {field.occurrence or ''}\nSize: {field.size or ''}\nDecimals: {field.decimals or ''}\nCondition: {field.condition or ''}"
        group = session.scalar(
            select(LayoutGroup)
            .join(LayoutEvent)
            .join(LayoutDocument)
            .where(
                LayoutDocument.corpus_build_id == build.id,
                LayoutGroup.source_local_stable_path == path,
            )
        )
        if group:
            return f"Path: {path}\nGroup: {group.technical_name}\nDescription: {group.description or ''}\nOccurrence: {group.occurrence or ''}\nCondition: {group.condition or ''}"
        event = session.scalar(
            select(LayoutEvent)
            .join(LayoutDocument)
            .where(
                LayoutDocument.corpus_build_id == build.id,
                LayoutEvent.source_local_stable_path == path,
            )
        )
        if event:
            return f"Event: {event.event_code}\nTitle: {event.title or ''}"
    if target.document_family == "XSD":
        element = session.scalar(
            select(XsdElement)
            .join(XsdPackageDocument)
            .where(
                XsdPackageDocument.corpus_build_id == build.id,
                XsdElement.source_local_stable_path == path,
            )
        )
        if element:
            enumerations = session.scalars(
                select(XsdEnumeration.value).where(
                    XsdEnumeration.owner_element_id == element.id
                )
            ).all()
            return f"Path: {path}\nElement: {element.name}\nType: {element.type_qname or ''}\nRef: {element.ref_qname or ''}\nminOccurs: {element.min_occurs or ''}\nmaxOccurs: {element.max_occurs or ''}\nDocumentation: {element.documentation or ''}\nFacets: {element.facets or {}}\nEnumerations: {', '.join(enumerations)}"
        shared = session.scalar(
            select(XsdSharedType)
            .join(XsdPackageDocument)
            .where(
                XsdPackageDocument.corpus_build_id == build.id,
                XsdSharedType.source_local_stable_path == path,
            )
        )
        if shared:
            return f"Path: {path}\nShared type: {shared.name}\nBase: {shared.base_qname or ''}\nFacets: {shared.facets or {}}"
        schema = session.scalar(
            select(XsdEventSchema)
            .join(XsdPackageDocument)
            .where(
                XsdPackageDocument.corpus_build_id == build.id,
                XsdEventSchema.source_local_stable_path == path,
            )
        )
        if schema:
            return f"Schema: {schema.schema_key}\nNamespace: {schema.target_namespace or ''}\nDocumentation: {schema.documentation or ''}"
    event = session.scalar(
        select(MosEventSection)
        .join(MosDocument)
        .where(
            MosDocument.corpus_build_id == build.id,
            MosEventSection.source_local_stable_path == path,
        )
    )
    if event:
        return f"Event: {event.event_code}\nTitle: {event.title}"
    metadata = session.scalar(
        select(EventMetadataBlock)
        .join(MosEventSection)
        .join(MosDocument)
        .where(
            MosDocument.corpus_build_id == build.id,
            EventMetadataBlock.source_local_stable_path == path,
        )
    )
    if metadata:
        return f"Metadata: {metadata.original_label}\nContent: {metadata.content}"
    event_topic = session.scalar(
        select(MosEventTopic)
        .join(MosEventSection)
        .join(MosDocument)
        .where(
            MosDocument.corpus_build_id == build.id,
            MosEventTopic.source_local_stable_path == path,
        )
    )
    if event_topic:
        return f"Event topic: {event_topic.number} {event_topic.title or ''}"
    topic = session.scalar(
        select(MosTopic)
        .join(MosDocument)
        .where(
            MosDocument.corpus_build_id == build.id,
            MosTopic.source_local_stable_path == path,
        )
    )
    if topic:
        return f"Topic: {topic.number} {topic.title or ''}\n{topic.content or ''}"
    subitem = session.scalar(
        select(MosEventSubitem)
        .join(MosEventSection)
        .join(MosDocument)
        .where(
            MosDocument.corpus_build_id == build.id,
            MosEventSubitem.source_local_stable_path == path,
        )
    )
    if subitem:
        return f"Subitem: {subitem.number} {subitem.title or ''}"
    raise ValueError("authorized structural content not found")


def assemble_evidence(session, build, projection, query, top_k=5):
    if projection.corpus_build_id != build.id:
        raise ValueError("projection belongs to another build")
    normalized = query.strip()
    if not normalized:
        raise ValueError("query is empty")
    config = {"top_k": top_k}
    digest = parser_config_digest(config)
    query_digest = _digest(normalized)
    evidence_set = session.scalar(
        select(EvidenceSet).where(
            EvidenceSet.corpus_build_id == build.id,
            EvidenceSet.search_projection_id == projection.id,
            EvidenceSet.query_digest == query_digest,
            EvidenceSet.retrieval_config_digest == digest,
            EvidenceSet.assembly_config_digest == digest,
        )
    )
    if evidence_set:
        return evidence_set, False
    evidence_set = EvidenceSet(
        id=str(uuid.uuid4()),
        corpus_build_id=build.id,
        search_projection_id=projection.id,
        query=normalized,
        query_digest=query_digest,
        retrieval_revision="fts-retrieval-v1",
        retrieval_config=config,
        retrieval_config_digest=digest,
        assembly_revision="evidence-assembly-v1",
        assembly_config=config,
        assembly_config_digest=digest,
        created_at=datetime.now(timezone.utc),
    )
    session.add(evidence_set)
    session.flush()
    hits = (
        session.execute(
            text(
                "SELECT id, root_citation_target_id, ts_rank_cd(search_vector, websearch_to_tsquery('simple', :q)) score FROM search_units WHERE search_projection_id=:p AND search_vector @@ websearch_to_tsquery('simple', :q) ORDER BY score DESC, source_local_stable_path ASC LIMIT :k"
            ),
            {"q": normalized, "p": projection.id, "k": top_k},
        )
        .mappings()
        .all()
    )
    seen = set()
    for rank, hit in enumerate(hits, 1):
        target = session.get(CitationTarget, hit["root_citation_target_id"])
        if target.id in seen:
            continue
        if not session.get(CorpusBuildCitationTarget, (build.id, target.id)):
            raise ValueError("retrieved target is not authorized by build")
        content = _render(session, build, target)
        seen.add(target.id)
        unit = session.scalar(
            select(EvidenceUnit).where(
                EvidenceUnit.corpus_build_id == build.id,
                EvidenceUnit.citation_target_id == target.id,
                EvidenceUnit.renderer_revision == "evidence-renderer-v1",
            )
        )
        if not unit:
            unit = EvidenceUnit(
                id=str(uuid.uuid4()),
                corpus_build_id=build.id,
                citation_target_id=target.id,
                canonical_entity_id=None,
                document_family=target.document_family,
                source_local_stable_path=target.source_local_stable_path,
                renderer_revision="evidence-renderer-v1",
                rendered_content=content,
                rendered_content_sha256=_digest(content),
                renderer_metadata={"rendered_from": "structural-build-content"},
            )
            session.add(unit)
            session.flush()
        session.add(
            EvidenceSetItem(
                evidence_set_id=evidence_set.id,
                evidence_unit_id=unit.id,
                source_search_unit_id=hit["id"],
                retrieval_rank=rank,
                retrieval_score=float(hit["score"]),
                evidence_order=len(seen),
                inclusion_role="ROOT",
            )
        )
    session.flush()
    return evidence_set, True
