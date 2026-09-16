from datetime import datetime

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class LayoutDocument(Base):
    __tablename__ = "layout_documents"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    corpus_build_id: Mapped[str] = mapped_column(
        ForeignKey("corpus_builds.id"), nullable=False
    )
    document_version_id: Mapped[str] = mapped_column(
        ForeignKey("document_versions.id"), nullable=False
    )
    artifact_id: Mapped[str] = mapped_column(
        ForeignKey("document_artifacts.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class LayoutEvent(Base):
    __tablename__ = "layout_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    layout_document_id: Mapped[str] = mapped_column(
        ForeignKey("layout_documents.id"), nullable=False
    )
    event_code: Mapped[str] = mapped_column(String(10), nullable=False)
    title: Mapped[str | None] = mapped_column(String(500))
    source_local_stable_path: Mapped[str] = mapped_column(Text, nullable=False)
    locator_metadata: Mapped[dict | None] = mapped_column(JSON)
    __table_args__ = (
        UniqueConstraint("layout_document_id", "source_local_stable_path"),
    )


class LayoutGroup(Base):
    __tablename__ = "layout_groups"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    layout_event_id: Mapped[str] = mapped_column(
        ForeignKey("layout_events.id"), nullable=False
    )
    parent_group_id: Mapped[str | None] = mapped_column(ForeignKey("layout_groups.id"))
    technical_name: Mapped[str] = mapped_column(String(300), nullable=False)
    level: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    occurrence: Mapped[str | None] = mapped_column(String(100))
    condition: Mapped[str | None] = mapped_column(Text)
    source_local_stable_path: Mapped[str] = mapped_column(Text, nullable=False)
    locator_metadata: Mapped[dict | None] = mapped_column(JSON)
    __table_args__ = (UniqueConstraint("layout_event_id", "source_local_stable_path"),)


class LayoutField(Base):
    __tablename__ = "layout_fields"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    layout_group_id: Mapped[str] = mapped_column(
        ForeignKey("layout_groups.id"), nullable=False
    )
    technical_name: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    field_type: Mapped[str | None] = mapped_column(String(100))
    occurrence: Mapped[str | None] = mapped_column(String(100))
    size: Mapped[str | None] = mapped_column(String(100))
    decimals: Mapped[str | None] = mapped_column(String(100))
    condition: Mapped[str | None] = mapped_column(Text)
    source_local_stable_path: Mapped[str] = mapped_column(Text, nullable=False)
    locator_metadata: Mapped[dict | None] = mapped_column(JSON)
    __table_args__ = (UniqueConstraint("layout_group_id", "source_local_stable_path"),)
