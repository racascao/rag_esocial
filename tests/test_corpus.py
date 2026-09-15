import hashlib
from types import SimpleNamespace

from rag_esocial.corpus import canonical_manifest, sha256_file


def test_sha256_detects_one_byte_change(tmp_path) -> None:
    path = tmp_path / "raw.bin"
    path.write_bytes(b"raw payload")
    original = sha256_file(path)
    assert original == hashlib.sha256(b"raw payload").hexdigest()
    path.write_bytes(b"raw payloaD")
    assert sha256_file(path) != original


def test_manifest_is_deterministic_and_ignores_insertion_order() -> None:
    def artifact(role: str, digest: str) -> SimpleNamespace:
        return SimpleNamespace(
            artifact_role=role,
            storage_path=f"{role}.bin",
            sha256=digest,
            size_bytes=1,
            archive_members=[],
        )

    version = SimpleNamespace(
        id="v1",
        document_family="MOS",
        version_label="1",
        title="MOS",
        artifacts=[artifact("MOS_MAIN", "a" * 64)],
    )
    first = SimpleNamespace(
        slug="snapshot",
        members=[SimpleNamespace(artifact_role="MOS_MAIN", document_version=version)],
    )
    second = SimpleNamespace(slug="snapshot", members=list(reversed(first.members)))
    assert canonical_manifest(first) == canonical_manifest(second)
