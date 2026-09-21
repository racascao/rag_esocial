import json
from pathlib import Path

from rag_esocial.mvp_validation_service import (
    MANIFEST_SCHEMA_VERSION,
    manifest_digest,
    validate_mvp_artifacts,
)


def test_final_mvp_artifact_validation_is_read_only_and_complete():
    manifest = validate_mvp_artifacts(Path("."))
    assert manifest["schema_version"] == MANIFEST_SCHEMA_VERSION
    assert manifest["status"] == "COMPLETE"
    assert all(manifest["gates"].values())
    assert manifest["human_review"] == "NOT_REVIEWED"
    assert manifest_digest(manifest)


def test_final_manifest_is_machine_readable():
    path = Path("evaluation/mvp/mvp_v1_manifest.json")
    if path.exists():
        manifest = json.loads(path.read_text(encoding="utf-8"))
        assert manifest["schema_version"] == MANIFEST_SCHEMA_VERSION
        assert manifest["status"] == "COMPLETE"
