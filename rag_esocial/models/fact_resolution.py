from datetime import datetime
from enum import StrEnum

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class RuntimeStatus(StrEnum):
    RESOLVED = "RESOLVED"
    SOURCE_NOT_APPLICABLE = "SOURCE_NOT_APPLICABLE"
    ASPECT_NOT_COVERED = "ASPECT_NOT_COVERED"
    NO_RELEVANT_EVIDENCE = "NO_RELEVANT_EVIDENCE"
    UNSUPPORTED = "UNSUPPORTED"


class RequestedFact(Base):
    __tablename__ = "requested_facts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    corpus_build_id: Mapped[str] = mapped_column(
        ForeignKey("corpus_builds.id"), nullable=False
    )
    request_revision: Mapped[str] = mapped_column(String(100), nullable=False)
    fact_type: Mapped[str] = mapped_column(String(100), nullable=False)
    subject_kind: Mapped[str] = mapped_column(String(100), nullable=False)
    subject_key: Mapped[str] = mapped_column(String(500), nullable=False)
    canonical_entity_id: Mapped[str | None] = mapped_column(
        ForeignKey("canonical_entities.id")
    )
    qualifiers: Mapped[dict] = mapped_column(JSON, nullable=False)
    request_payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    request_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    __table_args__ = (UniqueConstraint("corpus_build_id", "request_digest"),)


class FactResolution(Base):
    __tablename__ = "fact_resolutions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    requested_fact_id: Mapped[str] = mapped_column(
        ForeignKey("requested_facts.id"), nullable=False
    )
    document_family: Mapped[str] = mapped_column(String(20), nullable=False)
    evidence_set_id: Mapped[str | None] = mapped_column(ForeignKey("evidence_sets.id"))
    resolver_revision: Mapped[str] = mapped_column(String(100), nullable=False)
    resolver_config: Mapped[dict] = mapped_column(JSON, nullable=False)
    resolver_config_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    runtime_status: Mapped[str] = mapped_column(String(40), nullable=False)
    reason_code: Mapped[str | None] = mapped_column(String(100))
    resolved_value: Mapped[dict | None] = mapped_column(JSON)
    resolution_strategy: Mapped[str] = mapped_column(String(100), nullable=False)
    provenance: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    __table_args__ = (
        UniqueConstraint(
            "requested_fact_id",
            "document_family",
            "evidence_set_id",
            "resolver_config_digest",
        ),
    )


class FactResolutionSupport(Base):
    __tablename__ = "fact_resolution_supports"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    fact_resolution_id: Mapped[str] = mapped_column(
        ForeignKey("fact_resolutions.id"), nullable=False
    )
    evidence_unit_id: Mapped[str] = mapped_column(
        ForeignKey("evidence_units.id"), nullable=False
    )
    source_fact_id: Mapped[str | None] = mapped_column(ForeignKey("source_facts.id"))
    resolved_fact_id: Mapped[str | None] = mapped_column(
        ForeignKey("resolved_facts.id")
    )
    support_role: Mapped[str] = mapped_column(String(50), nullable=False)
    support_order: Mapped[int] = mapped_column(Integer, nullable=False)
    provenance: Mapped[dict] = mapped_column(JSON, nullable=False)
    __table_args__ = (
        UniqueConstraint(
            "fact_resolution_id",
            "evidence_unit_id",
            "source_fact_id",
            "resolved_fact_id",
        ),
    )
