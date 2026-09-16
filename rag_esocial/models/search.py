from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class SearchProjection(Base):
    __tablename__ = "search_projections"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    corpus_build_id: Mapped[str] = mapped_column(
        ForeignKey("corpus_builds.id"), nullable=False
    )
    profile: Mapped[str] = mapped_column(String(80), nullable=False)
    projection_revision: Mapped[str] = mapped_column(String(100), nullable=False)
    projection_config: Mapped[dict] = mapped_column(JSON, nullable=False)
    projection_config_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    text_search_config: Mapped[str] = mapped_column(String(80), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    __table_args__ = (
        UniqueConstraint(
            "corpus_build_id",
            "profile",
            "projection_revision",
            "projection_config_digest",
        ),
    )


class SearchUnit(Base):
    __tablename__ = "search_units"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    search_projection_id: Mapped[str] = mapped_column(
        ForeignKey("search_projections.id"), nullable=False
    )
    document_family: Mapped[str] = mapped_column(String(20), nullable=False)
    unit_kind: Mapped[str] = mapped_column(String(80), nullable=False)
    root_citation_target_id: Mapped[str] = mapped_column(
        ForeignKey("citation_targets.id"), nullable=False
    )
    canonical_entity_id: Mapped[str | None] = mapped_column(
        ForeignKey("canonical_entities.id")
    )
    source_local_stable_path: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str | None] = mapped_column(String(500))
    search_text: Mapped[str] = mapped_column(Text, nullable=False)
    technical_terms: Mapped[str] = mapped_column(Text, nullable=False)
    deterministic_key: Mapped[str] = mapped_column(String(600), nullable=False)
    search_vector: Mapped[object] = mapped_column(TSVECTOR, nullable=False)
    __table_args__ = (UniqueConstraint("search_projection_id", "deterministic_key"),)


class SearchUnitCitationTarget(Base):
    __tablename__ = "search_unit_citation_targets"
    search_unit_id: Mapped[str] = mapped_column(
        ForeignKey("search_units.id"), primary_key=True
    )
    citation_target_id: Mapped[str] = mapped_column(
        ForeignKey("citation_targets.id"), primary_key=True
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)
