from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .corpus import CorpusSnapshot


class CorpusBuild(Base):
    __tablename__ = "corpus_builds"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    corpus_snapshot_id: Mapped[str] = mapped_column(
        ForeignKey("corpus_snapshots.id"), nullable=False
    )
    parser_revision: Mapped[str] = mapped_column(String(200), nullable=False)
    parser_config: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    parser_config_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    build_digest: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="DRAFT")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    snapshot: Mapped["CorpusSnapshot"] = relationship()
    citations: Mapped[list["CorpusBuildCitationTarget"]] = relationship(
        "CorpusBuildCitationTarget",
        cascade="all, delete-orphan",
        back_populates="build",
    )


class CitationTarget(Base):
    __tablename__ = "citation_targets"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    stable_key: Mapped[str] = mapped_column(String(500), unique=True, nullable=False)
    document_version_id: Mapped[str] = mapped_column(
        ForeignKey("document_versions.id"), nullable=False
    )
    document_family: Mapped[str] = mapped_column(String(20), nullable=False)
    target_kind: Mapped[str] = mapped_column(String(80), nullable=False)
    source_local_stable_path: Mapped[str] = mapped_column(Text, nullable=False)
    human_label: Mapped[str | None] = mapped_column(String(500))
    locator_metadata: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    __table_args__ = (
        UniqueConstraint("document_version_id", "source_local_stable_path"),
    )


class CorpusBuildCitationTarget(Base):
    __tablename__ = "corpus_build_citation_targets"
    build_id: Mapped[str] = mapped_column(
        ForeignKey("corpus_builds.id"), primary_key=True
    )
    citation_target_id: Mapped[str] = mapped_column(
        ForeignKey("citation_targets.id"), primary_key=True
    )
    build: Mapped[CorpusBuild] = relationship(back_populates="citations")
    citation_target: Mapped[CitationTarget] = relationship()


class CanonicalEntity(Base):
    __tablename__ = "canonical_entities"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    stable_key: Mapped[str] = mapped_column(String(500), unique=True, nullable=False)
    entity_kind: Mapped[str] = mapped_column(String(80), nullable=False)
    canonical_key: Mapped[str] = mapped_column(String(300), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    __table_args__ = (UniqueConstraint("entity_kind", "canonical_key"),)
