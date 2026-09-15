from dataclasses import dataclass

from sqlalchemy import select

from .models.corpus import SnapshotMember


@dataclass(frozen=True)
class MembershipResult:
    valid: bool
    reason: str | None = None


def snapshot_membership_validity(
    session, document_version_id: str, snapshot_id: str
) -> MembershipResult:
    found = session.scalar(
        select(SnapshotMember.id).where(
            SnapshotMember.snapshot_id == snapshot_id,
            SnapshotMember.document_version_id == document_version_id,
        )
    )
    return (
        MembershipResult(True)
        if found
        else MembershipResult(False, "document version not member of snapshot")
    )
