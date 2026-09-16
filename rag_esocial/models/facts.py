from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class SourceFact(Base):
    __tablename__ = "source_facts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    corpus_build_id: Mapped[str] = mapped_column(
        ForeignKey("corpus_builds.id"), nullable=False
    )
    citation_target_id: Mapped[str] = mapped_column(
        ForeignKey("citation_targets.id"), nullable=False
    )
    subject_entity_id: Mapped[str | None] = mapped_column(
        ForeignKey("canonical_entities.id")
    )
    fact_type: Mapped[str] = mapped_column(String(100), nullable=False)
    extraction_kind: Mapped[str] = mapped_column(String(30), nullable=False)
    fact_key: Mapped[str] = mapped_column(String(500), nullable=False)
    string_value: Mapped[str | None] = mapped_column(Text)
    structured_value: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    __table_args__ = (UniqueConstraint("corpus_build_id", "fact_key"),)


class ReferenceResolution(Base):
    __tablename__ = "reference_resolutions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    corpus_build_id: Mapped[str] = mapped_column(
        ForeignKey("corpus_builds.id"), nullable=False
    )
    explicit_reference_id: Mapped[str] = mapped_column(
        ForeignKey("mos_explicit_references.id"), nullable=False
    )
    outcome: Mapped[str] = mapped_column(String(30), nullable=False)
    strategy: Mapped[str] = mapped_column(String(100), nullable=False)
    normalized_target_key: Mapped[str | None] = mapped_column(String(500))
    target_entity_id: Mapped[str | None] = mapped_column(
        ForeignKey("canonical_entities.id")
    )
    target_citation_target_id: Mapped[str | None] = mapped_column(
        ForeignKey("citation_targets.id")
    )
    diagnostic: Mapped[dict | None] = mapped_column(JSON)
    __table_args__ = (UniqueConstraint("corpus_build_id", "explicit_reference_id"),)


class EntityRelation(Base):
    __tablename__ = "entity_relations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    corpus_build_id: Mapped[str] = mapped_column(
        ForeignKey("corpus_builds.id"), nullable=False
    )
    source_entity_id: Mapped[str] = mapped_column(
        ForeignKey("canonical_entities.id"), nullable=False
    )
    target_entity_id: Mapped[str] = mapped_column(
        ForeignKey("canonical_entities.id"), nullable=False
    )
    relation_type: Mapped[str] = mapped_column(String(100), nullable=False)
    strategy: Mapped[str] = mapped_column(String(100), nullable=False)
    origin_citation_target_id: Mapped[str | None] = mapped_column(
        ForeignKey("citation_targets.id")
    )
    explicit_reference_id: Mapped[str | None] = mapped_column(
        ForeignKey("mos_explicit_references.id")
    )
    provenance: Mapped[dict | None] = mapped_column(JSON)
    __table_args__ = (
        UniqueConstraint(
            "corpus_build_id", "source_entity_id", "target_entity_id", "relation_type"
        ),
    )


class ResolvedFact(Base):
    __tablename__ = "resolved_facts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    corpus_build_id: Mapped[str] = mapped_column(
        ForeignKey("corpus_builds.id"), nullable=False
    )
    subject_entity_id: Mapped[str] = mapped_column(
        ForeignKey("canonical_entities.id"), nullable=False
    )
    fact_type: Mapped[str] = mapped_column(String(100), nullable=False)
    fact_key: Mapped[str] = mapped_column(String(500), nullable=False)
    value: Mapped[dict] = mapped_column(JSON, nullable=False)
    resolution_strategy: Mapped[str] = mapped_column(String(100), nullable=False)
    provenance: Mapped[dict] = mapped_column(JSON, nullable=False)
    __table_args__ = (UniqueConstraint("corpus_build_id", "fact_key"),)
