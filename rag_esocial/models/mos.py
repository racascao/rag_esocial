from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class MosDocument(Base):
    __tablename__ = "mos_documents"
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
    topics: Mapped[list["MosTopic"]] = relationship(cascade="all, delete-orphan")
    event_sections: Mapped[list["MosEventSection"]] = relationship(
        cascade="all, delete-orphan"
    )


class MosTopic(Base):
    __tablename__ = "mos_topics"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    mos_document_id: Mapped[str] = mapped_column(
        ForeignKey("mos_documents.id"), nullable=False
    )
    chapter: Mapped[str] = mapped_column(String(20), nullable=False)
    number: Mapped[str] = mapped_column(String(100), nullable=False)
    title: Mapped[str | None] = mapped_column(String(500))
    parent_topic_id: Mapped[str | None] = mapped_column(ForeignKey("mos_topics.id"))
    source_local_stable_path: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str | None] = mapped_column(Text)
    display_order: Mapped[int | None] = mapped_column(Integer)
    parent: Mapped["MosTopic | None"] = relationship(remote_side="MosTopic.id")
    __table_args__ = (UniqueConstraint("mos_document_id", "source_local_stable_path"),)


class MosEventSection(Base):
    __tablename__ = "mos_event_sections"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    mos_document_id: Mapped[str] = mapped_column(
        ForeignKey("mos_documents.id"), nullable=False
    )
    event_code: Mapped[str] = mapped_column(String(10), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    source_local_stable_path: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_blocks: Mapped[list["EventMetadataBlock"]] = relationship(
        cascade="all, delete-orphan"
    )
    topics: Mapped[list["MosEventTopic"]] = relationship(cascade="all, delete-orphan")
    __table_args__ = (UniqueConstraint("mos_document_id", "source_local_stable_path"),)


class EventMetadataBlock(Base):
    __tablename__ = "mos_event_metadata_blocks"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    event_section_id: Mapped[str] = mapped_column(
        ForeignKey("mos_event_sections.id"), nullable=False
    )
    block_kind: Mapped[str] = mapped_column(String(80), nullable=False)
    original_label: Mapped[str] = mapped_column(String(200), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source_local_stable_path: Mapped[str] = mapped_column(Text, nullable=False)


class MosEventTopic(Base):
    __tablename__ = "mos_event_topics"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    event_section_id: Mapped[str] = mapped_column(
        ForeignKey("mos_event_sections.id"), nullable=False
    )
    number: Mapped[str] = mapped_column(String(100), nullable=False)
    title: Mapped[str | None] = mapped_column(String(500))
    source_local_stable_path: Mapped[str] = mapped_column(Text, nullable=False)


class MosEventSubitem(Base):
    __tablename__ = "mos_event_subitems"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    event_section_id: Mapped[str] = mapped_column(
        ForeignKey("mos_event_sections.id"), nullable=False
    )
    number: Mapped[str] = mapped_column(String(100), nullable=False)
    parent_number: Mapped[str | None] = mapped_column(String(100))
    title: Mapped[str | None] = mapped_column(String(500))
    source_local_stable_path: Mapped[str] = mapped_column(Text, nullable=False)


class ContentBlock(Base):
    __tablename__ = "mos_content_blocks"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    mos_document_id: Mapped[str] = mapped_column(
        ForeignKey("mos_documents.id"), nullable=False
    )
    source_local_stable_path: Mapped[str] = mapped_column(Text, nullable=False)
    block_type: Mapped[str] = mapped_column(String(80), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    extraction_kind: Mapped[str] = mapped_column(
        String(80), nullable=False, default="STRUCTURAL"
    )


class ExplicitReference(Base):
    __tablename__ = "mos_explicit_references"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    corpus_build_id: Mapped[str] = mapped_column(
        ForeignKey("corpus_builds.id"), nullable=False
    )
    origin_citation_target_id: Mapped[str] = mapped_column(
        ForeignKey("citation_targets.id"), nullable=False
    )
    reference_kind: Mapped[str] = mapped_column(String(80), nullable=False)
    raw_value: Mapped[str] = mapped_column(String(300), nullable=False)
    normalized_value: Mapped[str | None] = mapped_column(String(300))
    extraction_kind: Mapped[str] = mapped_column(
        String(80), nullable=False, default="D2"
    )
    resolution_status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="UNRESOLVED"
    )
