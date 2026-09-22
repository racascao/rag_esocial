import hashlib
import json
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from .config import corpus_storage_path_for_environment
from .models.corpus import (
    REQUIRED_ROLES,
    ArchiveMember,
    CorpusSnapshot,
    DocumentArtifact,
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def storage_root() -> Path:
    root = corpus_storage_path_for_environment()
    root.mkdir(parents=True, exist_ok=True)
    return root


def inventory_zip(artifact: DocumentArtifact, session) -> None:
    path = storage_root() / artifact.storage_path
    with zipfile.ZipFile(path) as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            safe = Path(info.filename)
            if safe.is_absolute() or ".." in safe.parts:
                raise ValueError(f"unsafe archive member: {info.filename}")
            data = archive.read(info)
            session.add(
                ArchiveMember(
                    id=str(uuid.uuid4()),
                    artifact_id=artifact.id,
                    relative_path=info.filename,
                    sha256=hashlib.sha256(data).hexdigest(),
                    size_bytes=len(data),
                )
            )


def canonical_manifest(snapshot: CorpusSnapshot) -> bytes:
    members = []
    for member in sorted(snapshot.members, key=lambda item: item.artifact_role):
        version = member.document_version
        artifacts = []
        for artifact in sorted(
            version.artifacts, key=lambda item: (item.artifact_role, item.storage_path)
        ):
            artifacts.append(
                {
                    "role": artifact.artifact_role,
                    "sha256": artifact.sha256,
                    "size_bytes": artifact.size_bytes,
                    "archive_members": [
                        {
                            "path": m.relative_path,
                            "sha256": m.sha256,
                            "size_bytes": m.size_bytes,
                        }
                        for m in sorted(
                            artifact.archive_members,
                            key=lambda item: item.relative_path,
                        )
                    ],
                }
            )
        members.append(
            {
                "artifact_role": member.artifact_role,
                "document_version": {
                    "id": version.id,
                    "family": version.document_family,
                    "version_label": version.version_label,
                    "title": version.title,
                },
                "artifacts": artifacts,
            }
        )
    return (
        json.dumps(
            {"snapshot_slug": snapshot.slug, "members": members},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode()


def verify_snapshot(snapshot: CorpusSnapshot) -> list[str]:
    errors = []
    by_role = {member.artifact_role: member for member in snapshot.members}
    for role in REQUIRED_ROLES:
        member = by_role.get(role.value)
        if not member:
            errors.append(f"missing role: {role.value}")
            continue
        artifacts = [
            a
            for a in member.document_version.artifacts
            if a.artifact_role == role.value
        ]
        if not artifacts:
            errors.append(f"missing artifact: {role.value}")
        for artifact in artifacts:
            path = storage_root() / artifact.storage_path
            if not path.is_file():
                errors.append(f"missing file: {artifact.storage_path}")
            elif not artifact.sha256 or sha256_file(path) != artifact.sha256:
                errors.append(f"hash mismatch: {artifact.storage_path}")
    if (
        not errors
        and snapshot.frozen_at
        and hashlib.sha256(canonical_manifest(snapshot)).hexdigest()
        != snapshot.manifest_sha256
    ):
        errors.append("manifest hash mismatch")
    return errors


def freeze_snapshot(session, snapshot: CorpusSnapshot) -> str:
    if snapshot.frozen_at:
        raise ValueError("snapshot already frozen")
    errors = verify_snapshot(snapshot)
    if errors:
        raise ValueError("; ".join(errors))
    snapshot.manifest_sha256 = hashlib.sha256(canonical_manifest(snapshot)).hexdigest()
    snapshot.frozen_at = datetime.now(timezone.utc)
    session.commit()
    return snapshot.manifest_sha256
