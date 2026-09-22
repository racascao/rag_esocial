"""Active-runtime selection and readiness checks."""

from datetime import datetime, timezone

from sqlalchemy import select

from .identity import parser_config_digest
from .models.build import CorpusBuild
from .models.corpus import CorpusSnapshot
from .models.layout import LayoutDocument
from .models.mos import MosDocument
from .models.runtime import ActiveRuntime
from .models.search import SearchProjection
from .models.xsd import XsdPackageDocument
from .runtime_defaults import (
    DEFAULT_PARSER_REVISION,
    DEFAULT_SEARCH_CONFIG,
    DEFAULT_SEARCH_REVISION,
    RUNTIME_KEY,
)


def required_materialization_counts(session, build: CorpusBuild) -> dict[str, int]:
    return {
        "mos": session.scalar(
            select(MosDocument.id)
            .where(MosDocument.corpus_build_id == build.id)
            .limit(1)
        )
        is not None,
        "layout": session.scalar(
            select(LayoutDocument.id)
            .where(LayoutDocument.corpus_build_id == build.id)
            .limit(1)
        )
        is not None,
        "xsd": session.scalar(
            select(XsdPackageDocument.id)
            .where(XsdPackageDocument.corpus_build_id == build.id)
            .limit(1)
        )
        is not None,
    }


def ready_projection(session, build: CorpusBuild, profile: str):
    return session.scalar(
        select(SearchProjection).where(
            SearchProjection.corpus_build_id == build.id,
            SearchProjection.profile == profile,
            SearchProjection.projection_revision == DEFAULT_SEARCH_REVISION,
            SearchProjection.projection_config_digest
            == parser_config_digest(DEFAULT_SEARCH_CONFIG),
        )
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
