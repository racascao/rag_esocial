import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select

from .build_service import associate_citation_target
from .corpus import storage_root
from .identity import citation_stable_key
from .models.build import CitationTarget
from .models.corpus import ArtifactRole
from .models.xsd import (
    XsdElement,
    XsdEnumeration,
    XsdEventSchema,
    XsdPackageDocument,
    XsdSharedType,
)


def _target(session, build, version, kind, path, label, locator):
    key = citation_stable_key(version.id, "XSD", path)
    target = session.scalar(
        select(CitationTarget).where(CitationTarget.stable_key == key)
    )
    if not target:
        target = CitationTarget(
            id=str(uuid.uuid4()),
            stable_key=key,
            document_version_id=version.id,
            document_family="XSD",
            target_kind=kind,
            source_local_stable_path=path,
            human_label=label,
            locator_metadata=locator,
            created_at=datetime.now(timezone.utc),
        )
        session.add(target)
        session.flush()
    associate_citation_target(session, build, target)
    return target


def _refs(session, build, target, refs):
    from .models.mos import ExplicitReference

    for kind, raw, source in refs:
        exists = session.scalar(
            select(ExplicitReference).where(
                ExplicitReference.corpus_build_id == build.id,
                ExplicitReference.origin_citation_target_id == target.id,
                ExplicitReference.reference_kind == kind,
                ExplicitReference.raw_value == raw,
            )
        )
        if not exists:
            session.add(
                ExplicitReference(
                    id=str(uuid.uuid4()),
                    corpus_build_id=build.id,
                    origin_citation_target_id=target.id,
                    reference_kind=kind,
                    raw_value=raw,
                    normalized_value=raw,
                    extraction_kind="D2",
                    resolution_status="UNRESOLVED",
                )
            )


def materialize_xsd(session, build, version, artifact, results):
    if not build.snapshot.frozen_at:
        raise ValueError("build requires frozen snapshot")
    if artifact.artifact_role != ArtifactRole.XSD_PACKAGE.value:
        raise ValueError("artifact is not XSD_PACKAGE")
    doc = session.scalar(
        select(XsdPackageDocument).where(
            XsdPackageDocument.corpus_build_id == build.id,
            XsdPackageDocument.artifact_id == artifact.id,
        )
    )
    if doc:
        return doc
    doc = XsdPackageDocument(
        id=str(uuid.uuid4()),
        corpus_build_id=build.id,
        document_version_id=version.id,
        artifact_id=artifact.id,
        created_at=datetime.now(timezone.utc),
    )
    session.add(doc)
    session.flush()
    for result in results:
        path = (
            f"XSD/{result.target_namespace or 'NO_NAMESPACE'}/schema/"
            f"{result.schema_key}"
        )
        schema = XsdEventSchema(
            id=str(uuid.uuid4()),
            package_document_id=doc.id,
            relative_path=result.relative_path,
            schema_kind=result.kind,
            target_namespace=result.target_namespace,
            schema_key=result.schema_key,
            event_code=None,
            root_name=result.elements[0].name if result.elements else None,
            documentation=result.documentation,
            source_local_stable_path=path,
            locator_metadata={"archive_path": result.relative_path},
        )
        session.add(schema)
        session.flush()
        target = _target(
            session,
            build,
            version,
            "XSD_SCHEMA",
            path,
            result.schema_key,
            {"archive_path": result.relative_path},
        )
        _refs(session, build, target, result.references)
        shared_by_name = {}
        for st in result.shared_types:
            session.add(
                shared := XsdSharedType(
                    id=str(uuid.uuid4()),
                    package_document_id=doc.id,
                    name=st.name,
                    kind="SIMPLE_OR_COMPLEX",
                    target_namespace=result.target_namespace,
                    base_qname=st.facets.get("base"),
                    facets=st.facets,
                    documentation=st.documentation,
                    source_local_stable_path=st.path,
                    locator_metadata={"archive_path": result.relative_path},
                )
            )
            session.flush()
            shared_by_name[st.name] = shared
            _target(
                session,
                build,
                version,
                "XSD_SHARED_TYPE",
                st.path,
                st.name,
                {"archive_path": result.relative_path},
            )

        def elements(nodes, parent=None, owner_shared=None):
            for node in nodes:
                e = XsdElement(
                    id=str(uuid.uuid4()),
                    package_document_id=doc.id,
                    owner_schema_id=schema.id if owner_shared is None else None,
                    owner_shared_type_id=owner_shared.id if owner_shared else None,
                    parent_element_id=parent.id if parent else None,
                    name=node.name,
                    type_qname=node.type_qname,
                    ref_qname=node.ref_qname,
                    min_occurs=node.min_occurs,
                    max_occurs=node.max_occurs,
                    nillable=None,
                    default_value=None,
                    fixed_value=None,
                    facets=node.facets,
                    documentation=node.documentation,
                    source_local_stable_path=node.path,
                    locator_metadata={"archive_path": result.relative_path},
                )
                session.add(e)
                session.flush()
                target = _target(
                    session,
                    build,
                    version,
                    "XSD_ELEMENT",
                    node.path,
                    node.name,
                    {"archive_path": result.relative_path},
                )
                if node.type_qname and ":" in node.type_qname:
                    _refs(
                        session,
                        build,
                        target,
                        [
                            (
                                "SHARED_TYPE_REFERENCE",
                                node.type_qname,
                                result.relative_path,
                            )
                        ],
                    )
                for value, doc_text in node.enumerations:
                    ep = f"{node.path}/enum/{value}"
                    en = XsdEnumeration(
                        id=str(uuid.uuid4()),
                        package_document_id=doc.id,
                        owner_element_id=e.id,
                        owner_shared_type_id=None,
                        value=value,
                        documentation=doc_text,
                        source_local_stable_path=ep,
                    )
                    session.add(en)
                    session.flush()
                    _target(
                        session,
                        build,
                        version,
                        "XSD_ENUMERATION",
                        ep,
                        value,
                        {"archive_path": result.relative_path},
                    )
                elements(node.children, e, owner_shared)

        elements(result.elements)
    session.flush()
    return doc


def parse_and_materialize_xsd(session, build, version, artifact):
    from .xsd_parser import parse_xsd_package

    return materialize_xsd(
        session,
        build,
        version,
        artifact,
        parse_xsd_package(Path(storage_root()) / artifact.storage_path),
    )
