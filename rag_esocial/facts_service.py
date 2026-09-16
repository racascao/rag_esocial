import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from .build_service import associate_citation_target
from .identity import citation_stable_key, entity_stable_key
from .models.build import CanonicalEntity, CitationTarget
from .models.facts import EntityRelation, ReferenceResolution, SourceFact
from .models.layout import LayoutDocument, LayoutEvent, LayoutField, LayoutGroup
from .models.mos import (
    EventMetadataBlock,
    ExplicitReference,
    MosDocument,
    MosEventSection,
)
from .models.xsd import XsdElement, XsdPackageDocument


def _entity(session, kind, key):
    stable = entity_stable_key(kind, key)
    item = session.scalar(
        select(CanonicalEntity).where(CanonicalEntity.stable_key == stable)
    )
    if not item:
        item = CanonicalEntity(
            id=str(uuid.uuid4()),
            stable_key=stable,
            entity_kind=kind,
            canonical_key=key,
            display_name=key,
            created_at=datetime.now(timezone.utc),
        )
        session.add(item)
        session.flush()
    return item


def _fact(session, build, target, typ, kind, discriminator, value, subject=None):
    key = f"{target.id}|{typ}|{discriminator}"
    item = session.scalar(
        select(SourceFact).where(
            SourceFact.corpus_build_id == build.id, SourceFact.fact_key == key
        )
    )
    if not item:
        item = SourceFact(
            id=str(uuid.uuid4()),
            corpus_build_id=build.id,
            citation_target_id=target.id,
            subject_entity_id=subject.id if subject else None,
            fact_type=typ,
            extraction_kind=kind,
            fact_key=key,
            string_value=value if isinstance(value, str) else None,
            structured_value=value if isinstance(value, dict) else None,
            created_at=datetime.now(timezone.utc),
        )
        session.add(item)
    return item


def _target(session, build, version_id, family, path):
    target = session.scalar(
        select(CitationTarget).where(
            CitationTarget.stable_key == citation_stable_key(version_id, family, path)
        )
    )
    if target:
        return target
    target = CitationTarget(
        id=str(uuid.uuid4()),
        stable_key=citation_stable_key(version_id, family, path),
        document_version_id=version_id,
        document_family=family,
        target_kind="STRUCTURAL",
        source_local_stable_path=path,
        created_at=datetime.now(timezone.utc),
    )
    session.add(target)
    session.flush()
    associate_citation_target(session, build, target)
    return target


def build_facts(session, build):
    if not build.snapshot.frozen_at:
        raise ValueError("build requires frozen snapshot")
    for event, document in session.execute(
        select(MosEventSection, MosDocument)
        .join(MosDocument, MosDocument.id == MosEventSection.mos_document_id)
        .where(MosDocument.corpus_build_id == build.id)
    ).all():
        entity = _entity(session, "EVENT", event.event_code)
        target = _target(
            session,
            build,
            document.document_version_id,
            "MOS",
            event.source_local_stable_path,
        )
        for block in session.scalars(
            select(EventMetadataBlock).where(
                EventMetadataBlock.event_section_id == event.id
            )
        ).all():
            _fact(
                session,
                build,
                target,
                f"EVENT_{block.block_kind.upper()}",
                "D2",
                block.id,
                block.content,
                entity,
            )
    for event, document in session.execute(
        select(LayoutEvent, LayoutDocument)
        .join(LayoutDocument, LayoutDocument.id == LayoutEvent.layout_document_id)
        .where(LayoutDocument.corpus_build_id == build.id)
    ).all():
        entity = _entity(session, "EVENT", event.event_code)
        target = _target(
            session,
            build,
            document.document_version_id,
            "LAYOUT",
            event.source_local_stable_path,
        )
        for group in session.scalars(
            select(LayoutGroup).where(LayoutGroup.layout_event_id == event.id)
        ).all():
            _fact(
                session,
                build,
                target,
                "LAYOUT_DESCRIPTION",
                "D1",
                group.source_local_stable_path,
                group.description,
                entity,
            )
        for field in session.scalars(
            select(LayoutField)
            .join(LayoutGroup)
            .where(LayoutGroup.layout_event_id == event.id)
        ).all():
            ft = _target(
                session,
                build,
                document.document_version_id,
                "LAYOUT",
                field.source_local_stable_path,
            )
            for typ, value in (
                ("LAYOUT_OCCURRENCE", field.occurrence),
                ("LAYOUT_TYPE", field.field_type),
                ("LAYOUT_SIZE", field.size),
                ("LAYOUT_CONDITION", field.condition),
                ("LAYOUT_DESCRIPTION", field.description),
            ):
                if value:
                    _fact(
                        session,
                        build,
                        ft,
                        typ,
                        "D1",
                        field.source_local_stable_path,
                        value,
                        entity,
                    )
    for element, package in session.execute(
        select(XsdElement, XsdPackageDocument)
        .join(
            XsdPackageDocument, XsdPackageDocument.id == XsdElement.package_document_id
        )
        .where(XsdPackageDocument.corpus_build_id == build.id)
    ).all():
        target = _target(
            session,
            build,
            package.document_version_id,
            "XSD",
            element.source_local_stable_path,
        )
        for typ, value in (
            ("XSD_MIN_OCCURS", element.min_occurs),
            ("XSD_MAX_OCCURS", element.max_occurs),
            ("XSD_TYPE_QNAME", element.type_qname),
            ("XSD_REF_QNAME", element.ref_qname),
        ):
            if value:
                _fact(
                    session,
                    build,
                    target,
                    typ,
                    "D1",
                    element.source_local_stable_path,
                    value,
                )
    for ref in session.scalars(
        select(ExplicitReference).where(ExplicitReference.corpus_build_id == build.id)
    ).all():
        if session.scalar(
            select(ReferenceResolution).where(
                ReferenceResolution.corpus_build_id == build.id,
                ReferenceResolution.explicit_reference_id == ref.id,
            )
        ):
            continue
        if ref.reference_kind == "RULE_REFERENCE":
            key = "RULE:" + ref.raw_value
            strategy = "D3_CANONICAL_KEY"
            entity = None
            outcome = "UNRESOLVED"
        elif ref.reference_kind == "DOMAIN_TABLE_REFERENCE":
            key = "DOMAIN_TABLE:" + ref.raw_value.removeprefix("Tabela ")
            strategy = "D3_CANONICAL_KEY"
            entity = None
            outcome = "UNRESOLVED"
        elif ref.reference_kind == "SHARED_TYPE_REFERENCE":
            key = "SHARED_TYPE:" + ref.raw_value
            entity = _entity(session, "SHARED_TYPE", ref.raw_value)
            strategy = "D3_QNAME"
            outcome = "RESOLVED"
        else:
            key = ref.raw_value
            strategy = "D3_CANONICAL_KEY"
            entity = (
                _entity(session, "EVENT", ref.raw_value)
                if ref.reference_kind == "EVENT_CODE"
                else None
            )
            outcome = "RESOLVED" if entity else "UNRESOLVED"
        resolution = ReferenceResolution(
            id=str(uuid.uuid4()),
            corpus_build_id=build.id,
            explicit_reference_id=ref.id,
            outcome=outcome,
            strategy=strategy,
            normalized_target_key=key,
            target_entity_id=entity.id if entity else None,
            diagnostic={"raw": ref.raw_value},
        )
        session.add(resolution)
        if entity and outcome == "RESOLVED":
            source = session.get(CitationTarget, ref.origin_citation_target_id)
            existing = session.scalar(
                select(EntityRelation).where(
                    EntityRelation.corpus_build_id == build.id,
                    EntityRelation.source_entity_id == entity.id,
                    EntityRelation.target_entity_id == entity.id,
                    EntityRelation.relation_type == "REFERENCES_EVENT",
                )
            )
            if not existing and ref.reference_kind == "EVENT_CODE":
                session.add(
                    EntityRelation(
                        id=str(uuid.uuid4()),
                        corpus_build_id=build.id,
                        source_entity_id=entity.id,
                        target_entity_id=entity.id,
                        relation_type="REFERENCES_EVENT",
                        strategy=strategy,
                        origin_citation_target_id=source.id if source else None,
                        explicit_reference_id=ref.id,
                        provenance={
                            "raw": ref.raw_value,
                            "normalized": key,
                            "outcome": outcome,
                        },
                    )
                )
        session.flush()
    session.flush()
