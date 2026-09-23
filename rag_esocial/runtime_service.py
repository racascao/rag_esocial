"""Active-runtime selection and readiness checks."""

from datetime import datetime, timezone

from sqlalchemy import func, select

from .identity import parser_config_digest
from .models.build import CorpusBuild
from .models.corpus import CorpusSnapshot
from .models.layout import LayoutDocument, LayoutEvent, LayoutField, LayoutGroup
from .models.mos import MosDocument, MosEventSection
from .models.runtime import ActiveRuntime
from .models.search import SearchProjection
from .models.xsd import XsdEventSchema, XsdPackageDocument
from .runtime_defaults import (
    DEFAULT_PARSER_REVISION,
    DEFAULT_SEARCH_CONFIG,
    DEFAULT_SEARCH_REVISION,
    RUNTIME_KEY,
)
from .search_service import projection_complete


def required_materialization_counts(session, build: CorpusBuild) -> dict[str, int]:
    layout = session.scalar(
        select(func.count(LayoutField.id))
        .join(LayoutGroup)
        .join(LayoutEvent)
        .join(LayoutDocument)
        .where(LayoutDocument.corpus_build_id == build.id)
    )
    layout_groups = session.scalar(
        select(func.count(LayoutGroup.id))
        .join(LayoutEvent)
        .join(LayoutDocument)
        .where(LayoutDocument.corpus_build_id == build.id)
    )
    layout_events = session.scalar(
        select(func.count(LayoutEvent.id))
        .join(LayoutDocument)
        .where(LayoutDocument.corpus_build_id == build.id)
    )
    mos_events = session.scalar(
        select(func.count(MosEventSection.id))
        .join(MosDocument)
        .where(MosDocument.corpus_build_id == build.id)
    )
    xsd_events = session.scalar(
        select(func.count(XsdEventSchema.id))
        .join(XsdPackageDocument)
        .where(XsdPackageDocument.corpus_build_id == build.id)
    )
    return {
        "mos": bool(mos_events)
        and session.scalar(
            select(MosDocument.id)
            .where(MosDocument.corpus_build_id == build.id)
            .limit(1)
        )
        is not None,
        "layout": bool(layout and layout_groups and layout_events)
        and session.scalar(
            select(LayoutDocument.id)
            .where(LayoutDocument.corpus_build_id == build.id)
            .limit(1)
        )
        is not None,
        "xsd": bool(xsd_events)
        and session.scalar(
            select(XsdPackageDocument.id)
            .where(XsdPackageDocument.corpus_build_id == build.id)
            .limit(1)
        )
        is not None,
    }


def ready_projection(session, build: CorpusBuild, profile: str):
    projection = session.scalar(
        select(SearchProjection).where(
            SearchProjection.corpus_build_id == build.id,
            SearchProjection.profile == profile,
            SearchProjection.projection_revision == DEFAULT_SEARCH_REVISION,
            SearchProjection.projection_config_digest
            == parser_config_digest(DEFAULT_SEARCH_CONFIG),
        )
    )
    return (
        projection
        if projection and projection_complete(session, build, projection)
        else None
    )


def is_build_ready(session, build: CorpusBuild, profiles: tuple[str, ...]) -> bool:
    snapshot = session.get(CorpusSnapshot, build.corpus_snapshot_id)
    if (
        not snapshot
        or not snapshot.frozen_at
        or not snapshot.manifest_sha256
        or build.parser_revision != DEFAULT_PARSER_REVISION
        or build.status != "COMPLETE"
    ):
        return False
    counts = required_materialization_counts(session, build)
    if not all(counts.values()):
        return False
    return all(ready_projection(session, build, profile) for profile in profiles)


def get_active_runtime(session) -> ActiveRuntime | None:
    return session.get(ActiveRuntime, RUNTIME_KEY)


def activate_runtime(
    session, build: CorpusBuild, projection: SearchProjection
) -> ActiveRuntime:
    current = session.get(ActiveRuntime, RUNTIME_KEY)
    generation = current.generation + 1 if current else 1
    if current:
        current.corpus_build_id = build.id
        current.search_projection_id = projection.id
        current.activated_at = datetime.now(timezone.utc)
        current.generation = generation
        runtime = current
    else:
        runtime = ActiveRuntime(
            runtime_key=RUNTIME_KEY,
            corpus_build_id=build.id,
            search_projection_id=projection.id,
            activated_at=datetime.now(timezone.utc),
            generation=generation,
        )
        session.add(runtime)
    session.flush()
    return runtime


def active_runtime_summary(session) -> dict | None:
    runtime = get_active_runtime(session)
    if not runtime:
        return None
    build = runtime.build
    snapshot = build.snapshot
    members = {
        member.artifact_role: member.document_version for member in snapshot.members
    }
    return {
        "snapshot_slug": snapshot.slug,
        "build_digest": build.build_digest,
        "parser_revision": build.parser_revision,
        "generation": runtime.generation,
        "versions": {role: version.version_label for role, version in members.items()},
    }
