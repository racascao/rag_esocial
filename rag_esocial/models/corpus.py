from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class DocumentFamily(StrEnum):
    MOS = "MOS"
    LAYOUT = "LAYOUT"
    XSD = "XSD"


class ArtifactRole(StrEnum):
    MOS_MAIN = "MOS_MAIN"
    LAYOUT_MAIN = "LAYOUT_MAIN"
    LAYOUT_ANNEX_I_DOMAIN_TABLES = "LAYOUT_ANNEX_I_DOMAIN_TABLES"
    LAYOUT_ANNEX_II_VALIDATION_RULES = "LAYOUT_ANNEX_II_VALIDATION_RULES"
    XSD_PACKAGE = "XSD_PACKAGE"


REQUIRED_ROLES = tuple(ArtifactRole)


class DocumentVersion(Base):
    __tablename__ = "document_versions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    document_family: Mapped[str] = mapped_column(String(20), nullable=False)
    version_label: Mapped[str] = mapped_column(String(200), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    publisher: Mapped[str | None] = mapped_column(String(300))
    official_published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    effective_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )
    artifacts: Mapped[list["DocumentArtifact"]] = relationship(
        back_populates="document_version"
    )


class DocumentArtifact(Base):
    __tablename__ = "document_artifacts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    document_version_id: Mapped[str] = mapped_column(
        ForeignKey("document_versions.id"), nullable=False
    )
    artifact_role: Mapped[str] = mapped_column(String(80), nullable=False)
    official_url: Mapped[str] = mapped_column(Text, nullable=False)
    original_filename: Mapped[str] = mapped_column(String(500), nullable=False)
    media_type: Mapped[str | None] = mapped_column(String(200))
    storage_path: Mapped[str] = mapped_column(Text, nullable=False)
    sha256: Mapped[str | None] = mapped_column(String(64))
    size_bytes: Mapped[int | None] = mapped_column(Integer)
    retrieved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    capture_method: Mapped[str] = mapped_column(String(50), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )
    document_version: Mapped[DocumentVersion] = relationship(back_populates="artifacts")
    archive_members: Mapped[list["ArchiveMember"]] = relationship(
        back_populates="artifact", cascade="all, delete-orphan"
    )


class ArchiveMember(Base):
    __tablename__ = "archive_members"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    artifact_id: Mapped[str] = mapped_column(
        ForeignKey("document_artifacts.id"), nullable=False
    )
    relative_path: Mapped[str] = mapped_column(Text, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    artifact: Mapped[DocumentArtifact] = relationship(back_populates="archive_members")
    __table_args__ = (UniqueConstraint("artifact_id", "relative_path"),)


class CorpusSnapshot(Base):
    __tablename__ = "corpus_snapshots"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    slug: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )
    frozen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    manifest_sha256: Mapped[str | None] = mapped_column(String(64))
    members: Mapped[list["SnapshotMember"]] = relationship(
        back_populates="snapshot", cascade="all, delete-orphan"
    )


class SnapshotMember(Base):
    __tablename__ = "snapshot_members"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    snapshot_id: Mapped[str] = mapped_column(
        ForeignKey("corpus_snapshots.id"), nullable=False
    )
    artifact_role: Mapped[str] = mapped_column(String(80), nullable=False)
    document_version_id: Mapped[str] = mapped_column(
        ForeignKey("document_versions.id"), nullable=False
    )
    snapshot: Mapped[CorpusSnapshot] = relationship(back_populates="members")
    document_version: Mapped[DocumentVersion] = relationship()
    __table_args__ = (UniqueConstraint("snapshot_id", "artifact_role"),)
