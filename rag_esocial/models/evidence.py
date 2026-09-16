from datetime import datetime

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class EvidenceSet(Base):
    __tablename__ = "evidence_sets"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    corpus_build_id: Mapped[str] = mapped_column(
        ForeignKey("corpus_builds.id"), nullable=False
    )
    search_projection_id: Mapped[str] = mapped_column(
        ForeignKey("search_projections.id"), nullable=False
    )
    query: Mapped[str] = mapped_column(Text, nullable=False)
    query_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    retrieval_revision: Mapped[str] = mapped_column(String(100), nullable=False)
    retrieval_config: Mapped[dict] = mapped_column(JSON, nullable=False)
    retrieval_config_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    assembly_revision: Mapped[str] = mapped_column(String(100), nullable=False)
    assembly_config: Mapped[dict] = mapped_column(JSON, nullable=False)
    assembly_config_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    __table_args__ = (
        UniqueConstraint(
            "corpus_build_id",
            "search_projection_id",
            "query_digest",
            "retrieval_config_digest",
            "assembly_config_digest",
        ),
    )


class EvidenceUnit(Base):
    __tablename__ = "evidence_units"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    corpus_build_id: Mapped[str] = mapped_column(
        ForeignKey("corpus_builds.id"), nullable=False
    )
    citation_target_id: Mapped[str] = mapped_column(
        ForeignKey("citation_targets.id"), nullable=False
    )
    canonical_entity_id: Mapped[str | None] = mapped_column(
        ForeignKey("canonical_entities.id")
    )
    document_family: Mapped[str] = mapped_column(String(20), nullable=False)
    source_local_stable_path: Mapped[str] = mapped_column(Text, nullable=False)
    renderer_revision: Mapped[str] = mapped_column(String(100), nullable=False)
    rendered_content: Mapped[str] = mapped_column(Text, nullable=False)
    rendered_content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    renderer_metadata: Mapped[dict] = mapped_column("metadata", JSON, nullable=False)
    __table_args__ = (
        UniqueConstraint("corpus_build_id", "citation_target_id", "renderer_revision"),
    )


class EvidenceSetItem(Base):
    __tablename__ = "evidence_set_items"
    evidence_set_id: Mapped[str] = mapped_column(
        ForeignKey("evidence_sets.id"), primary_key=True
    )
    evidence_unit_id: Mapped[str] = mapped_column(
        ForeignKey("evidence_units.id"), nullable=False
    )
    source_search_unit_id: Mapped[str] = mapped_column(
        ForeignKey("search_units.id"), nullable=False
    )
    retrieval_rank: Mapped[int] = mapped_column(Integer, nullable=False)
    retrieval_score: Mapped[float] = mapped_column(Float, nullable=False)
    evidence_order: Mapped[int] = mapped_column(Integer, nullable=False)
    inclusion_role: Mapped[str] = mapped_column(String(20), nullable=False)
    __table_args__ = (UniqueConstraint("evidence_set_id", "evidence_unit_id"),)
