import pytest
from sqlalchemy import delete, func, select
from test_layout_official_hotfix import _event, _s1005
from test_mos_integration import build_fixture, cleanup, materialize_phase4_fixture

from rag_esocial.build_service import create_build
from rag_esocial.layout_materializer import materialize_layout
from rag_esocial.layout_parser import LayoutParseResult, LayoutStructureError
from rag_esocial.models.build import CitationTarget
from rag_esocial.models.corpus import (
    ArtifactRole,
    DocumentArtifact,
    DocumentVersion,
    SnapshotMember,
)
from rag_esocial.models.layout import (
    LayoutDocument,
    LayoutEvent,
    LayoutField,
    LayoutGroup,
)
from rag_esocial.models.runtime import ActiveRuntime
from rag_esocial.models.search import SearchUnit, SearchUnitCitationTarget
from rag_esocial.runtime_service import (
    activate_runtime,
    get_active_runtime,
    is_build_ready,
)
from rag_esocial.search_service import (
    materialize_projection,
    projection_complete,
    search,
)
from rag_esocial.setup_service import prepare_runtime


def test_dev_mos_001_and_operational_family_profiles(tmp_path):
    session, snapshot, build, _, _, ids = build_fixture(
        tmp_path,
        event_code="S-1000",
        layout_html=_event("S-1000", "evtInfoEmpregador", "inclusao") + _s1005(),
    )
    ids["builds"].append(build.id)
    try:
        materialize_phase4_fixture(session, build, snapshot)
        session.commit()
        profile, _ = materialize_projection(
            session, build, "MOS_ALL", "fts-baseline-v2"
        )
        session.commit()
        expected = "MOS/CapIII/S-1000/metadata/conceito"
        assert session.scalar(
            select(CitationTarget.id).where(
                CitationTarget.source_local_stable_path == expected
            )
        )
        for question in ("qual é o conceito do evento S-1000?", "conceito S-1000"):
            paths = [
                r["source_local_stable_path"]
                for r in search(session, profile, question)
            ]
            assert expected in paths
        assert projection_complete(session, build, profile)
        assert {r["unit_kind"] for r in search(session, profile, "S-1000")} >= {
            "MOS_EVENT_SECTION",
            "MOS_EVENT_METADATA",
        }
        for family in ("LAYOUT_ALL", "XSD_ALL"):
            projection, _ = materialize_projection(
                session, build, family, "fts-baseline-v2"
            )
            assert projection_complete(session, build, projection)
            if family == "LAYOUT_ALL":
                for question, expected_path in (
                    ("ideEmpregador S-1000", "LAYOUT/S-1000/ideEmpregador"),
                    (
                        "tpInsc ideEmpregador S-1000",
                        "LAYOUT/S-1000/ideEmpregador/tpInsc",
                    ),
                    (
                        "classTrib S-1000",
                        "LAYOUT/S-1000/infoEmpregador/inclusao/infoCadastro/classTrib",
                    ),
                    (
                        "aliqRat S-1005",
                        "LAYOUT/S-1005/dadosEstab/aliqGilrat/aliqRat",
                    ),
                ):
                    assert expected_path in {
                        row["source_local_stable_path"]
                        for row in search(session, projection, question)
                    }
    finally:
        session.rollback()
        cleanup(session, ids)
        session.close()


def test_empty_layout_rejected_without_persisting_document(tmp_path):
    session, snapshot, build, _, _, ids = build_fixture(tmp_path)
    ids["builds"].append(build.id)
    try:
        member = session.scalar(
            select(SnapshotMember).where(
                SnapshotMember.snapshot_id == snapshot.id,
                SnapshotMember.artifact_role == ArtifactRole.LAYOUT_MAIN.value,
            )
        )
        version = session.get(DocumentVersion, member.document_version_id)
        artifact = session.scalar(
            select(DocumentArtifact).where(
                DocumentArtifact.document_version_id == version.id,
                DocumentArtifact.artifact_role == ArtifactRole.LAYOUT_MAIN.value,
            )
        )
        with pytest.raises(LayoutStructureError, match="no events"):
            materialize_layout(session, build, version, artifact, LayoutParseResult())
        assert not session.scalar(
            select(LayoutDocument.id).where(LayoutDocument.corpus_build_id == build.id)
        )
    finally:
        session.rollback()
        cleanup(session, ids)
        session.close()


def test_projection_repairs_zero_and_partial_units_idempotently(tmp_path, monkeypatch):
    import rag_esocial.search_service as search_module

    session, snapshot, build, _, _, ids = build_fixture(tmp_path)
    ids["builds"].append(build.id)
    try:
        materialize_phase4_fixture(session, build, snapshot)
        profile, _ = materialize_projection(
            session, build, "LAYOUT_ALL", "fts-baseline-v2"
        )
        session.commit()
        original = session.scalar(
            select(func.count(SearchUnit.id)).where(
                SearchUnit.search_projection_id == profile.id
            )
        )
        assert original >= 3
        units = session.scalars(
            select(SearchUnit).where(SearchUnit.search_projection_id == profile.id)
        ).all()
        for unit in units[:1]:
            session.execute(
                delete(SearchUnitCitationTarget).where(
                    SearchUnitCitationTarget.search_unit_id == unit.id
                )
            )
            session.delete(unit)
        session.commit()
        assert not projection_complete(session, build, profile)
        original_target = search_module._target

        def broken_target(*_args):
            raise RuntimeError("projection repair interrupted")

        monkeypatch.setattr(search_module, "_target", broken_target)
        with pytest.raises(RuntimeError, match="repair interrupted"):
            materialize_projection(session, build, "LAYOUT_ALL", "fts-baseline-v2")
        assert (
            session.scalar(
                select(func.count(SearchUnit.id)).where(
                    SearchUnit.search_projection_id == profile.id
                )
            )
            == original - 1
        )
        monkeypatch.setattr(search_module, "_target", original_target)
        repaired, created = materialize_projection(
            session, build, "LAYOUT_ALL", "fts-baseline-v2"
        )
        session.commit()
        assert (
            created
            and repaired.id == profile.id
            and projection_complete(session, build, repaired)
        )
        same, created = materialize_projection(
            session, build, "LAYOUT_ALL", "fts-baseline-v2"
        )
        assert not created and same.id == profile.id
        one_unit = session.scalar(
            select(SearchUnit.id).where(SearchUnit.search_projection_id == profile.id)
        )
        session.execute(
            delete(SearchUnitCitationTarget).where(
                SearchUnitCitationTarget.search_unit_id == one_unit
            )
        )
        session.commit()
        assert not projection_complete(session, build, profile)
        materialize_projection(session, build, "LAYOUT_ALL", "fts-baseline-v2")
        assert projection_complete(session, build, profile)
        session.execute(
            delete(SearchUnitCitationTarget).where(
                SearchUnitCitationTarget.search_unit_id.in_(
                    select(SearchUnit.id).where(
                        SearchUnit.search_projection_id == profile.id
                    )
                )
            )
        )
        session.execute(
            delete(SearchUnit).where(SearchUnit.search_projection_id == profile.id)
        )
        session.commit()
        assert not projection_complete(session, build, profile)
        materialize_projection(session, build, "LAYOUT_ALL", "fts-baseline-v2")
        assert projection_complete(session, build, profile)
    finally:
        session.rollback()
        cleanup(session, ids)
        session.close()


def test_build_revision_is_distinct_and_citation_target_transversal(tmp_path):
    session, snapshot, build, _, _, ids = build_fixture(tmp_path)
    ids["builds"].append(build.id)
    try:
        materialize_phase4_fixture(session, build, snapshot)
        session.commit()
        first, _ = materialize_projection(
            session, build, "LAYOUT_FIELD", "fts-baseline-v2"
        )
        build2 = create_build(
            session, snapshot.slug, "parser-suite-v2", {"suite": "test"}
        )
        ids["builds"].append(build2.id)
        materialize_phase4_fixture(session, build2, snapshot)
        second, _ = materialize_projection(
            session, build2, "LAYOUT_FIELD", "fts-baseline-v2"
        )
        session.commit()
        assert build.corpus_snapshot_id == build2.corpus_snapshot_id == snapshot.id
        assert build.build_digest != build2.build_digest
        assert first.id != second.id
        left = session.scalar(
            select(SearchUnit.root_citation_target_id).where(
                SearchUnit.search_projection_id == first.id
            )
        )
        right = session.scalar(
            select(SearchUnit.root_citation_target_id).where(
                SearchUnit.search_projection_id == second.id
            )
        )
        assert left == right
    finally:
        session.rollback()
        cleanup(session, ids)
        session.close()


def test_local_rebuild_preserves_active_runtime_on_failure_then_switches_once(
    tmp_path, monkeypatch
):
    import rag_esocial.setup_service as setup_module

    session, snapshot, old_build, _, _, ids = build_fixture(tmp_path)
    ids["builds"].append(old_build.id)
    old_build_id = old_build.id
    snapshot_id = snapshot.id
    try:
        materialize_phase4_fixture(session, old_build, snapshot)
        old_build.status = "COMPLETE"
        old_projection, _ = materialize_projection(
            session, old_build, "LAYOUT_FIELD", "fts-baseline-v1"
        )
        old_unit_ids = select(SearchUnit.id).where(
            SearchUnit.search_projection_id == old_projection.id
        )
        session.execute(
            delete(SearchUnitCitationTarget).where(
                SearchUnitCitationTarget.search_unit_id.in_(old_unit_ids)
            )
        )
        session.execute(
            delete(SearchUnit).where(
                SearchUnit.search_projection_id == old_projection.id
            )
        )
        session.execute(delete(LayoutField))
        session.execute(delete(LayoutGroup))
        session.execute(delete(LayoutEvent))
        assert not session.scalar(
            select(SearchUnit.id).where(
                SearchUnit.search_projection_id == old_projection.id
            )
        )
        assert session.scalar(
            select(LayoutDocument.id).where(
                LayoutDocument.corpus_build_id == old_build.id
            )
        )
        old_runtime = activate_runtime(session, old_build, old_projection)
        session.commit()
        original_generation = old_runtime.generation
        hashes = {
            artifact.id: artifact.sha256
            for member in snapshot.members
            for artifact in member.document_version.artifacts
        }
        original_parser = setup_module.parse_layout_html

        def broken_parser(_html):
            raise RuntimeError("parser failure")

        monkeypatch.setattr(setup_module, "parse_layout_html", broken_parser)

        class NoNetwork:
            def download(self, *_args, **_kwargs):
                raise AssertionError("internal rebuild must not use HTTP")

        with pytest.raises(RuntimeError, match="parser failure"):
            prepare_runtime(session, downloader=NoNetwork())
        session.rollback()
        session.close()
        from rag_esocial.db import session_factory

        session = session_factory()()
        assert get_active_runtime(session).corpus_build_id == old_build_id
        assert get_active_runtime(session).generation == original_generation
        monkeypatch.setattr(setup_module, "parse_layout_html", original_parser)
        result = prepare_runtime(session, downloader=NoNetwork())
        assert result["build"].id != old_build_id
        assert result["build"].corpus_snapshot_id == snapshot_id
        assert result["runtime"].generation == original_generation + 1
        assert is_build_ready(session, result["build"], tuple(setup_module.PROFILES))
        assert {
            artifact.id: artifact.sha256
            for member in result["snapshot"].members
            for artifact in member.document_version.artifacts
        } == hashes
        again = prepare_runtime(session, downloader=NoNetwork())
        assert again["same_version"]
        assert again["runtime"].generation == original_generation + 1
        ids["builds"].append(result["build"].id)
    finally:
        session.rollback()
        session.execute(delete(ActiveRuntime))
        session.commit()
        cleanup(session, ids)
        session.close()
