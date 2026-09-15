import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from .identity import build_digest, parser_config_digest
from .models.build import CitationTarget, CorpusBuild, CorpusBuildCitationTarget
from .models.corpus import CorpusSnapshot
from .validators import snapshot_membership_validity


def create_build(
    session, snapshot_slug: str, parser_revision: str, parser_config: dict | None = None
) -> CorpusBuild:
    if not parser_revision.strip():
        raise ValueError("parser_revision is required")
    snapshot = session.scalar(
        select(CorpusSnapshot).where(CorpusSnapshot.slug == snapshot_slug)
    )
    if not snapshot:
        raise ValueError("snapshot not found")
    if not snapshot.frozen_at or not snapshot.manifest_sha256:
        raise ValueError("build requires a frozen snapshot")
    config = parser_config or {}
    config_digest = parser_config_digest(config)
    digest = build_digest(snapshot.manifest_sha256, parser_revision, config_digest)
    existing = session.scalar(
        select(CorpusBuild).where(CorpusBuild.build_digest == digest)
    )
    if existing:
        return existing
    build = CorpusBuild(
        id=str(uuid.uuid4()),
        corpus_snapshot_id=snapshot.id,
        parser_revision=parser_revision,
        parser_config=config,
        parser_config_digest=config_digest,
        build_digest=digest,
        status="DRAFT",
        created_at=datetime.now(timezone.utc),
    )
    session.add(build)
    session.commit()
    return build


def associate_citation_target(
    session, build: CorpusBuild, target: CitationTarget
) -> CorpusBuildCitationTarget:
    result = snapshot_membership_validity(
        session, target.document_version_id, build.corpus_snapshot_id
    )
    if not result.valid:
        raise ValueError(result.reason or "snapshot membership invalid")
    existing = session.get(CorpusBuildCitationTarget, (build.id, target.id))
    if existing:
        return existing
    association = CorpusBuildCitationTarget(
        build_id=build.id, citation_target_id=target.id
    )
    session.add(association)
    session.commit()
    return association
