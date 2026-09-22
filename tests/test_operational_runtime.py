import os
import subprocess
import zipfile
from io import BytesIO
from pathlib import Path

import pytest
from sqlalchemy import delete, func, select, text
from test_mos_integration import build_fixture, cleanup

from rag_esocial.acquisition_service import AcquisitionError, SourceInput, UrlDownloader
from rag_esocial.corpus import freeze_snapshot, verify_snapshot
from rag_esocial.db import assert_test_session, session_factory
from rag_esocial.models.build import CorpusBuild
from rag_esocial.models.corpus import (
    CorpusSnapshot,
    DocumentArtifact,
    DocumentVersion,
    SnapshotMember,
)
from rag_esocial.models.runtime import ActiveRuntime
from rag_esocial.runtime_service import active_runtime_summary, get_active_runtime
from rag_esocial.setup_service import (
    _create_snapshot,
    _sources_from_urls,
    prepare_runtime,
)


class _Response:
    headers = {"Content-Type": "text/html"}

    def __init__(self, payload: bytes):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self):
        return self.payload


def _xsd_package() -> bytes:
    output = BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr(
            "event.xsd", "<xs:schema xmlns:xs='http://www.w3.org/2001/XMLSchema'/>"
        )
    return output.getvalue()


def _onboarding_downloader(
    tmp_path, annex_ii: bytes | None = None, layout_html: bytes | None = None
):
    layout_url = "https://example.test/v1/index.html"
    responses = {
        "https://example.test/mos.pdf": b"%PDF-1.7\n",
        "https://example.test/schema.zip": _xsd_package(),
        layout_url: layout_html
        or (
            b"<html><a href='tabelas.html#05'>Tabela 05</a>"
            b"<a href='regras.html#REGRA_X'>REGRA_X</a></html>"
        ),
        "https://example.test/v1/tabelas.html": (
            b"<html>ANEXO I DOS LEIAUTES DO eSOCIAL TABELAS</html>"
        ),
        "https://example.test/v1/regras.html": annex_ii
        or b"<html>ANEXO II DOS LEIAUTES DO eSOCIAL REGRAS DE VALIDACAO</html>",
    }
    return SourceInput(
        mos_url="https://example.test/mos.pdf",
        xsd_url="https://example.test/schema.zip",
        layout_url=layout_url,
    ), UrlDownloader(
        tmp_path,
        opener=lambda url, **_kwargs: _Response(responses[url]),
    )


def _empty_onboarding_counts(session) -> dict[str, int]:
    return {
        "snapshots": session.scalar(select(func.count()).select_from(CorpusSnapshot)),
        "members": session.scalar(select(func.count()).select_from(SnapshotMember)),
        "versions": session.scalar(select(func.count()).select_from(DocumentVersion)),
        "artifacts": session.scalar(select(func.count()).select_from(DocumentArtifact)),
        "builds": session.scalar(select(func.count()).select_from(CorpusBuild)),
        "active_runtimes": session.scalar(
            select(func.count()).select_from(ActiveRuntime)
        ),
    }


def test_onboarding_discovers_annexes_and_persists_verified_frozen_snapshot(tmp_path):
    urls, downloader = _onboarding_downloader(tmp_path)
    session = session_factory()()
    try:
        assert_test_session(session)
        sources = _sources_from_urls(urls, downloader)
        assert [source.role for source in sources] == [
            "MOS_MAIN",
            "LAYOUT_MAIN",
            "LAYOUT_ANNEX_I_DOMAIN_TABLES",
            "LAYOUT_ANNEX_II_VALIDATION_RULES",
            "XSD_PACKAGE",
        ]
        assert sources[2].url == "https://example.test/v1/tabelas.html"
        assert sources[3].url == "https://example.test/v1/regras.html"

        snapshot = _create_snapshot(session, sources)
        assert verify_snapshot(snapshot) == []
        freeze_snapshot(session, snapshot)
        session.commit()
        assert snapshot.frozen_at is not None
        assert len(snapshot.members) == 5
        ids = {
            "snapshots": [snapshot.id],
            "versions": [member.document_version_id for member in snapshot.members],
            "artifacts": [
                artifact.id
                for member in snapshot.members
                for artifact in member.document_version.artifacts
            ],
            "builds": [],
        }
        cleanup(session, ids)
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def test_onboarding_invalid_annex_leaves_no_partial_database_state(tmp_path):
    urls, downloader = _onboarding_downloader(
        tmp_path,
        annex_ii=b"<html>ANEXO I DOS LEIAUTES DO eSOCIAL TABELAS</html>",
    )
    session = session_factory()()
    try:
        assert_test_session(session)
        assert _empty_onboarding_counts(session) == {
            "snapshots": 0,
            "members": 0,
            "versions": 0,
            "artifacts": 0,
            "builds": 0,
            "active_runtimes": 0,
        }
        with pytest.raises(AcquisitionError, match="Anexo II"):
            _sources_from_urls(urls, downloader)
        assert _empty_onboarding_counts(session) == {
            "snapshots": 0,
            "members": 0,
            "versions": 0,
            "artifacts": 0,
            "builds": 0,
            "active_runtimes": 0,
        }
    finally:
        session.close()


def test_onboarding_missing_annex_i_leaves_no_partial_database_state(tmp_path):
    urls, downloader = _onboarding_downloader(
        tmp_path,
        layout_html=b"<html><a href='regras.html#REGRA_X'>REGRA_X</a></html>",
    )
    session = session_factory()()
    try:
        assert_test_session(session)
        expected = {
            "snapshots": 0,
            "members": 0,
            "versions": 0,
            "artifacts": 0,
            "builds": 0,
            "active_runtimes": 0,
        }
        assert _empty_onboarding_counts(session) == expected
        with pytest.raises(AcquisitionError, match="Anexo I"):
            _sources_from_urls(urls, downloader)
        assert _empty_onboarding_counts(session) == expected
    finally:
        session.close()


def test_launcher_is_executable_and_has_safe_shell_syntax():
    launcher = Path("esocial")
    assert os.access(launcher, os.X_OK)
    assert "docker compose up -d --build" in launcher.read_text()
    result = subprocess.run(["sh", "-n", str(launcher)], check=False)
    assert result.returncode == 0


def test_setup_activates_runtime_and_survives_new_session(tmp_path):
    session, snapshot, _build, _version, _artifact, ids = build_fixture(tmp_path)
    try:
        database = session.execute(text("SELECT current_database()")).scalar_one()
        assert database == "esocial_test"
        result = prepare_runtime(session)
        assert result["runtime"].runtime_key == "default"
        first_build_id = result["build"].id
        second = prepare_runtime(session)
        assert second["same_version"] is True
        assert second["runtime"].generation == result["runtime"].generation
        session.close()

        from rag_esocial.db import session_factory

        fresh = session_factory()()
        try:
            database = fresh.execute(text("SELECT current_database()")).scalar_one()
            assert database == "esocial_test"
            runtime = get_active_runtime(fresh)
            assert runtime is not None
            assert runtime.corpus_build_id == first_build_id
            assert active_runtime_summary(fresh)["snapshot_slug"] == snapshot.slug
        finally:
            fresh.execute(delete(ActiveRuntime))
            fresh.commit()
            cleanup(fresh, ids)
            fresh.close()
    except Exception:
        session.rollback()
        session.close()
        raise
