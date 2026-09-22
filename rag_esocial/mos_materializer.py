import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from .build_service import associate_citation_target
from .identity import citation_stable_key
from .models.build import CitationTarget
from .models.corpus import DocumentArtifact, DocumentVersion
from .models.mos import (
    ContentBlock,
    EventMetadataBlock,
    ExplicitReference,
    MosDocument,
    MosEventSection,
    MosEventSubitem,
    MosEventTopic,
    MosTopic,
)
from .mos_parser import validate_mos_structure
from .validators import snapshot_membership_validity


def materialize_mos(
    session, build, version: DocumentVersion, artifact: DocumentArtifact, result
):
    if not build.snapshot.frozen_at:
        raise ValueError("build requires a frozen snapshot")
    membership = snapshot_membership_validity(
        session, version.id, build.corpus_snapshot_id
    )
    if not membership.valid:
        raise ValueError(membership.reason)
    if (
        artifact.document_version_id != version.id
        or artifact.artifact_role != "MOS_MAIN"
    ):
        raise ValueError("artifact is not the MOS_MAIN for the document version")
    existing = session.scalar(
        select(MosDocument).where(
            MosDocument.corpus_build_id == build.id,
            MosDocument.artifact_id == artifact.id,
        )
    )
    if existing:
        return existing, False
    validate_mos_structure(result)
    document = MosDocument(
        id=str(uuid.uuid4()),
        corpus_build_id=build.id,
        document_version_id=version.id,
        artifact_id=artifact.id,
        created_at=datetime.now(timezone.utc),
    )
    session.add(document)
    target_cache = {}

    def target(path: str, kind: str, label: str | None = None):
        key = citation_stable_key(version.id, "MOS", path)
        found = session.scalar(
            select(CitationTarget).where(CitationTarget.stable_key == key)
        )
        if not found:
            found = CitationTarget(
                id=str(uuid.uuid4()),
                stable_key=key,
                document_version_id=version.id,
                document_family="MOS",
                target_kind=kind,
                source_local_stable_path=path,
                human_label=label,
                locator_metadata={"page": 1},
                created_at=datetime.now(timezone.utc),
            )
            session.add(found)
            session.flush()
        associate_citation_target(session, build, found)
        target_cache[path] = found
        return found

    for node in result.topics:
        session.add(
            MosTopic(
                id=str(uuid.uuid4()),
                mos_document_id=document.id,
                chapter="I/II",
                number=node.number,
                title=node.title,
                source_local_stable_path=node.path,
                content=node.content,
            )
        )
        target(node.path, "topic", node.title)
    for event in result.events:
        section = MosEventSection(
            id=str(uuid.uuid4()),
            mos_document_id=document.id,
            event_code=event.code,
            title=event.title,
            source_local_stable_path=event.path,
        )
        session.add(section)
        target(event.path, "event_section", event.title)
        for kind, label, content in event.metadata:
            path = f"{event.path}/metadata/{kind.lower()}"
            session.add(
                EventMetadataBlock(
                    id=str(uuid.uuid4()),
                    event_section_id=section.id,
                    block_kind=kind,
                    original_label=label,
                    content=content,
                    source_local_stable_path=path,
                )
            )
            target(path, "metadata_block", label)
        for node in event.topics:
            session.add(
                MosEventTopic(
                    id=str(uuid.uuid4()),
                    event_section_id=section.id,
                    number=node.number,
                    title=node.title,
                    source_local_stable_path=node.path,
                )
            )
            target(node.path, "event_topic", node.title)
        for node in event.subitems:
            session.add(
                MosEventSubitem(
                    id=str(uuid.uuid4()),
                    event_section_id=section.id,
                    number=node.number,
                    parent_number=node.parent_number,
                    title=node.title,
                    source_local_stable_path=node.path,
                )
            )
            target(node.path, "event_subitem", node.title)
    for path, block_type, content in result.content_blocks:
        session.add(
            ContentBlock(
                id=str(uuid.uuid4()),
                mos_document_id=document.id,
                source_local_stable_path=path,
                block_type=block_type,
                content=content,
                extraction_kind="STRUCTURAL",
            )
        )
    for kind, raw, extraction_kind, owner_path in result.references:
        origin = target_cache.get(owner_path)
        if origin is None:
            raise ValueError(f"reference owner has no CitationTarget: {owner_path}")
        session.add(
            ExplicitReference(
                id=str(uuid.uuid4()),
                corpus_build_id=build.id,
                origin_citation_target_id=origin.id,
                reference_kind=kind,
                raw_value=raw,
                normalized_value=raw,
                extraction_kind=extraction_kind,
                resolution_status="UNRESOLVED",
            )
        )
    session.flush()
    return document, True
