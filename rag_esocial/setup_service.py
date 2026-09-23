"""High-level onboarding/update/resume orchestration.

The service deliberately keeps network and long parsing work outside a single
database transaction.  The only operation that changes the default runtime is
the final short transaction in :func:`activate_runtime`.
"""

from __future__ import annotations

import re
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select

from .acquisition_service import (
    DownloadedSource,
    SourceInput,
    UrlDownloader,
    discover_layout_annexes,
)
from .build_service import create_build
from .corpus import (
    freeze_snapshot,
    inventory_zip,
    sha256_file,
    storage_root,
    verify_snapshot,
)
from .facts_service import build_facts
from .identity import parser_config_digest
from .layout_materializer import materialize_layout
from .layout_parser import parse_layout_html
from .models.build import CorpusBuild
from .models.corpus import (
    ArtifactRole,
    CorpusSnapshot,
    DocumentArtifact,
    DocumentVersion,
    SnapshotMember,
)
from .models.layout import LayoutDocument
from .models.mos import MosDocument
from .models.xsd import XsdPackageDocument
from .mos_materializer import materialize_mos
from .mos_parser import MosStructureError, parse_mos_pages
from .pdf_text import PdfTextExtractor
from .runtime_defaults import (
    DEFAULT_PARSER_CONFIG,
    DEFAULT_PARSER_REVISION,
    DEFAULT_SEARCH_CONFIG,
    DEFAULT_SEARCH_PROFILE,
    DEFAULT_SEARCH_REVISION,
    ROLE_METADATA,
)
from .runtime_service import (
    activate_runtime,
    get_active_runtime,
    is_build_ready,
    ready_projection,
    required_materialization_counts,
)
from .search_service import PROFILES, materialize_projection
from .xsd_materializer import parse_and_materialize_xsd


class SetupError(ValueError):
    pass


def _version_label(filename: str, sha256: str) -> str:
    stem = Path(filename).stem.replace("_", " ").replace("-", " ")
    stem = re.sub(r"\s+", " ", stem).strip()
    return stem[:180] or f"source-{sha256[:12]}"


def _copy_to_storage(source: DownloadedSource) -> Path:
    root = storage_root()
    target = root / source.path.name
    if source.path.resolve() != target.resolve():
        shutil.copyfile(source.path, target)
    return target


def _valid_frozen_snapshots(session):
    for snapshot in session.scalars(
        select(CorpusSnapshot).where(CorpusSnapshot.frozen_at.is_not(None))
    ).all():
        if not verify_snapshot(snapshot):
            yield snapshot


def _snapshot_hashes(snapshot: CorpusSnapshot) -> dict[str, str]:
    return {
        artifact.artifact_role: artifact.sha256
        for member in snapshot.members
        for artifact in member.document_version.artifacts
        if artifact.artifact_role == member.artifact_role
    }


def _same_snapshot(session, hashes: dict[str, str]) -> CorpusSnapshot | None:
    for snapshot in _valid_frozen_snapshots(session):
        if _snapshot_hashes(snapshot) == hashes:
            return snapshot
    return None


def _new_slug(hashes: dict[str, str]) -> str:
    digest = "".join(hashes[role] for role in sorted(hashes))
    return f"esocial-snapshot-{digest[:16]}"


def _create_snapshot(session, sources: list[DownloadedSource]) -> CorpusSnapshot:
    hashes = {source.role: source.sha256 for source in sources}
    existing = _same_snapshot(session, hashes)
    if existing:
        return existing
    slug = _new_slug(hashes)
    if session.scalar(select(CorpusSnapshot).where(CorpusSnapshot.slug == slug)):
        slug = f"{slug}-{uuid.uuid4().hex[:8]}"
    snapshot = CorpusSnapshot(
        id=str(uuid.uuid4()), slug=slug, created_at=datetime.now(timezone.utc)
    )
    session.add(snapshot)
    session.flush()
    for source in sources:
        family, title = ROLE_METADATA[source.role]
        path = _copy_to_storage(source)
        version = DocumentVersion(
            id=str(uuid.uuid4()),
            document_family=family,
            version_label=_version_label(source.filename, source.sha256),
            title=title,
            publisher="gov.br",
        )
        artifact = DocumentArtifact(
            id=str(uuid.uuid4()),
            document_version=version,
            artifact_role=source.role,
            official_url=source.url,
            original_filename=source.filename,
            media_type=source.media_type,
            storage_path=path.name,
            sha256=sha256_file(path),
            size_bytes=path.stat().st_size,
            retrieved_at=datetime.now(timezone.utc),
            capture_method="automatic_url_import",
        )
        session.add(version)
        session.flush()
        if source.role == ArtifactRole.XSD_PACKAGE.value:
            inventory_zip(artifact, session)
        session.add(
            SnapshotMember(
                id=str(uuid.uuid4()),
                snapshot_id=snapshot.id,
                artifact_role=source.role,
                document_version_id=version.id,
            )
        )
    session.commit()
    return snapshot


def _sources_from_urls(urls: SourceInput, downloader) -> list[DownloadedSource]:
    mos = downloader.download(ArtifactRole.MOS_MAIN.value, urls.mos_url)
    xsd = downloader.download(ArtifactRole.XSD_PACKAGE.value, urls.xsd_url)
    layout = downloader.download(ArtifactRole.LAYOUT_MAIN.value, urls.layout_url)
    html = layout.path.read_text(encoding="utf-8")
    annex_urls = discover_layout_annexes(html, layout.url)
    annex_i = downloader.download(
        ArtifactRole.LAYOUT_ANNEX_I_DOMAIN_TABLES.value,
        annex_urls[ArtifactRole.LAYOUT_ANNEX_I_DOMAIN_TABLES.value],
    )
    annex_ii = downloader.download(
        ArtifactRole.LAYOUT_ANNEX_II_VALIDATION_RULES.value,
        annex_urls[ArtifactRole.LAYOUT_ANNEX_II_VALIDATION_RULES.value],
    )
    return [mos, layout, annex_i, annex_ii, xsd]


def _snapshot_build(session, snapshot: CorpusSnapshot) -> CorpusBuild:
    canonical = session.scalar(
        select(CorpusBuild).where(
            CorpusBuild.corpus_snapshot_id == snapshot.id,
            CorpusBuild.parser_revision == DEFAULT_PARSER_REVISION,
            CorpusBuild.parser_config_digest
            == parser_config_digest(DEFAULT_PARSER_CONFIG),
        )
    )
    if canonical:
        return canonical
    return create_build(
        session,
        snapshot.slug,
        DEFAULT_PARSER_REVISION,
        dict(DEFAULT_PARSER_CONFIG),
    )


def _artifact_for(session, snapshot, role: str):
    member = session.scalar(
        select(SnapshotMember).where(
            SnapshotMember.snapshot_id == snapshot.id,
            SnapshotMember.artifact_role == role,
        )
    )
    if not member:
        raise SetupError(f"snapshot sem o artefato obrigatório {role}")
    artifact = session.scalar(
        select(DocumentArtifact).where(
            DocumentArtifact.document_version_id == member.document_version_id,
            DocumentArtifact.artifact_role == role,
        )
    )
    if not artifact:
        raise SetupError(f"artefato ausente para {role}")
    return member.document_version, artifact


def materialize_build(session, build: CorpusBuild, progress=None) -> CorpusBuild:
    """Resume every deterministic pre-computable stage for a frozen snapshot."""
    snapshot = session.get(CorpusSnapshot, build.corpus_snapshot_id)
    if not snapshot or not snapshot.frozen_at:
        raise SetupError("o build exige um snapshot congelado")

    if build.status == "COMPLETE" and all(
        required_materialization_counts(session, build).values()
    ):
        if progress:
            progress("Atualizando índice de busca")
        for profile in PROFILES:
            materialize_projection(
                session,
                build,
                profile,
                revision=DEFAULT_SEARCH_REVISION,
                config=dict(DEFAULT_SEARCH_CONFIG),
            )
            session.commit()
        return build

    def step(label):
        if progress:
            progress(label)

    version, artifact = _artifact_for(session, snapshot, ArtifactRole.MOS_MAIN.value)
    if not session.scalar(
        select(MosDocument).where(MosDocument.corpus_build_id == build.id)
    ):
        step("Processando MOS")
        pages = PdfTextExtractor().extract(storage_root() / artifact.storage_path).pages
        try:
            materialize_mos(
                session,
                build,
                version,
                artifact,
                parse_mos_pages(pages),
            )
            session.commit()
        except MosStructureError as error:
            session.rollback()
            raise SetupError(f"estrutura do MOS inválida: {error}") from error
        except Exception:
            session.rollback()
            raise

    version, artifact = _artifact_for(session, snapshot, ArtifactRole.LAYOUT_MAIN.value)
    if not session.scalar(
        select(LayoutDocument).where(LayoutDocument.corpus_build_id == build.id)
    ):
        step("Processando Leiaute")
        html = (storage_root() / artifact.storage_path).read_text(encoding="utf-8")
        materialize_layout(session, build, version, artifact, parse_layout_html(html))
        session.commit()

    version, artifact = _artifact_for(session, snapshot, ArtifactRole.XSD_PACKAGE.value)
    if not session.scalar(
        select(XsdPackageDocument).where(XsdPackageDocument.corpus_build_id == build.id)
    ):
        step("Processando XSD")
        parse_and_materialize_xsd(session, build, version, artifact)
        session.commit()

    step("Construindo fatos")
    build_facts(session, build)
    session.commit()
    step("Construindo índice de busca")
    for profile in PROFILES:
        materialize_projection(
            session,
            build,
            profile,
            revision=DEFAULT_SEARCH_REVISION,
            config=dict(DEFAULT_SEARCH_CONFIG),
        )
        session.commit()
    build.status = "COMPLETE"
    build.completed_at = datetime.now(timezone.utc)
    session.commit()
    return build


def _candidate_snapshot(session) -> CorpusSnapshot | None:
    active = get_active_runtime(session)
    if (
        active
        and active.build.snapshot.frozen_at
        and not verify_snapshot(active.build.snapshot)
    ):
        return active.build.snapshot
    snapshots = list(_valid_frozen_snapshots(session))
    snapshots.sort(key=lambda item: item.created_at, reverse=True)
    for snapshot in snapshots:
        builds = session.scalars(
            select(CorpusBuild).where(CorpusBuild.corpus_snapshot_id == snapshot.id)
        ).all()
        if any(build.parser_revision == DEFAULT_PARSER_REVISION for build in builds):
            return snapshot
    return snapshots[0] if snapshots else None


def prepare_runtime(
    session,
    urls: SourceInput | None = None,
    downloader=None,
    progress=None,
) -> dict:
    """Prepare and atomically activate a runtime, or resume an existing chain."""
    snapshot = None
    if urls is not None:
        downloader = downloader or UrlDownloader(storage_root())
        sources = _sources_from_urls(urls, downloader)
        snapshot = _create_snapshot(session, sources)
        if not snapshot.frozen_at:
            errors = verify_snapshot(snapshot)
            if errors:
                raise SetupError("corpus inválido: " + "; ".join(errors))
            freeze_snapshot(session, snapshot)
    else:
        snapshot = _candidate_snapshot(session)
        if snapshot is None:
            raise SetupError("nenhum corpus oficial válido; são necessárias três URLs")
    build = _snapshot_build(session, snapshot)
    materialize_build(session, build, progress)
    if not is_build_ready(session, build, tuple(PROFILES)):
        raise SetupError("o pipeline terminou sem produzir um runtime READY")
    projection = ready_projection(session, build, DEFAULT_SEARCH_PROFILE)
    if projection is None:
        raise SetupError("projeção padrão não encontrada")
    current = get_active_runtime(session)
    if (
        current
        and current.corpus_build_id == build.id
        and current.search_projection_id == projection.id
    ):
        session.commit()
        return {
            "snapshot": snapshot,
            "build": build,
            "runtime": current,
            "same_version": True,
        }
    runtime = activate_runtime(session, build, projection)
    session.commit()
    return {
        "snapshot": snapshot,
        "build": build,
        "runtime": runtime,
        "same_version": False,
    }
