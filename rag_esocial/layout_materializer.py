import re
import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from .build_service import associate_citation_target
from .identity import citation_stable_key
from .layout_parser import LayoutStructureError
from .models.build import CitationTarget
from .models.corpus import DocumentArtifact, DocumentVersion
from .models.layout import LayoutDocument, LayoutEvent, LayoutField, LayoutGroup
from .models.mos import ExplicitReference
from .validators import snapshot_membership_validity


def materialize_layout(
    session, build, version: DocumentVersion, artifact: DocumentArtifact, result
):
    if not build.snapshot.frozen_at:
        raise ValueError("build requires a frozen snapshot")
    if (
        artifact.artifact_role != "LAYOUT_MAIN"
        or artifact.document_version_id != version.id
    ):
        raise ValueError("artifact is not the authorized LAYOUT_MAIN")
    membership = snapshot_membership_validity(
        session, version.id, build.corpus_snapshot_id
    )
    if not membership.valid:
        raise ValueError(membership.reason)
    if not result.events:
        raise LayoutStructureError("layout contains no events")
    paths = set()
    owners = set()
    group_count = field_count = 0
    for event in result.events:
        if (
            not re.fullmatch(r"S-\d{4}", event.code)
            or event.path != f"LAYOUT/{event.code}"
        ):
            raise LayoutStructureError(f"invalid layout event: {event.code}")
        if event.path in paths:
            raise LayoutStructureError(f"duplicate layout path: {event.path}")
        paths.add(event.path)
        owners.add(event.path)

        def check_group(group, parent_path):
            nonlocal group_count, field_count
            if (
                not group.name
                or group.path != f"{parent_path}/{group.name}"
                or group.path in paths
            ):
                raise LayoutStructureError(
                    f"invalid/duplicate group path: {group.path}"
                )
            paths.add(group.path)
            owners.add(group.path)
            group_count += 1
            for item in group.fields:
                if (
                    not item.name
                    or item.path != f"{group.path}/{item.name}"
                    or item.path in paths
                ):
                    raise LayoutStructureError(
                        f"invalid/duplicate field path: {item.path}"
                    )
                paths.add(item.path)
                owners.add(item.path)
                field_count += 1
            for child in group.children:
                check_group(child, group.path)

        for group in event.groups:
            check_group(group, event.path)
    if not group_count or not field_count:
        raise LayoutStructureError("layout has no groups or fields")
    if any(ref.owner_path not in owners for ref in result.references):
        raise LayoutStructureError("layout reference has no structural owner")
    existing = session.scalar(
        select(LayoutDocument).where(
            LayoutDocument.corpus_build_id == build.id,
            LayoutDocument.artifact_id == artifact.id,
        )
    )
    if existing:
        return existing, False
    document = LayoutDocument(
        id=str(uuid.uuid4()),
        corpus_build_id=build.id,
        document_version_id=version.id,
        artifact_id=artifact.id,
        created_at=datetime.now(timezone.utc),
    )
    session.add(document)
    targets = {}

    def target(path, kind, label):
        key = citation_stable_key(version.id, "LAYOUT", path)
        found = session.scalar(
            select(CitationTarget).where(CitationTarget.stable_key == key)
        )
        if not found:
            found = CitationTarget(
                id=str(uuid.uuid4()),
                stable_key=key,
                document_version_id=version.id,
                document_family="LAYOUT",
                target_kind=kind,
                source_local_stable_path=path,
                human_label=label,
                locator_metadata={"source": "html"},
                created_at=datetime.now(timezone.utc),
            )
            session.add(found)
            session.flush()
        associate_citation_target(session, build, found)
        targets[path] = found
        return found

    for event in result.events:
        event_row = LayoutEvent(
            id=str(uuid.uuid4()),
            layout_document_id=document.id,
            event_code=event.code,
            title=event.title,
            source_local_stable_path=event.path,
            locator_metadata={"source": "html"},
        )
        session.add(event_row)
        target(event.path, "layout_event", event.title)

        def persist_group(group, parent_id=None):
            row = LayoutGroup(
                id=str(uuid.uuid4()),
                layout_event_id=event_row.id,
                parent_group_id=parent_id,
                technical_name=group.name,
                level=group.level,
                description=group.description,
                occurrence=group.attrs.get("occurrence"),
                condition=group.attrs.get("condition"),
                source_local_stable_path=group.path,
                locator_metadata={"source": "html"},
            )
            session.add(row)
            target(group.path, "layout_group", group.name)
            for field in group.fields:
                session.add(
                    LayoutField(
                        id=str(uuid.uuid4()),
                        layout_group_id=row.id,
                        technical_name=field.name,
                        description=field.description,
                        field_type=field.attrs.get("type"),
                        occurrence=field.attrs.get("occurrence"),
                        size=field.attrs.get("size"),
                        decimals=field.attrs.get("decimals"),
                        condition=field.attrs.get("condition"),
                        source_local_stable_path=field.path,
                        locator_metadata={"source": "html"},
                    )
                )
                target(field.path, "layout_field", field.name)
            session.flush()
            for child in group.children:
                persist_group(child, row.id)

        for group in event.groups:
            persist_group(group)
    for reference in result.references:
        origin = targets.get(reference.owner_path)
        if origin is None:
            raise ValueError(
                f"reference owner has no CitationTarget: {reference.owner_path}"
            )
        session.add(
            ExplicitReference(
                id=str(uuid.uuid4()),
                corpus_build_id=build.id,
                origin_citation_target_id=origin.id,
                reference_kind=reference.kind,
                raw_value=reference.raw_value,
                normalized_value=reference.normalized_value or reference.raw_value,
                extraction_kind="D2",
                resolution_status="UNRESOLVED",
            )
        )
    session.flush()
    return document, True
