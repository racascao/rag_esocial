from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .answer import AnswerRequest, AnswerRun
    from .build import CanonicalEntity, CorpusBuild
    from .fact_resolution import RequestedFact


class CompleteRunExecutionState(StrEnum):
    RUNNING = "RUNNING"
    FINALIZED = "FINALIZED"
    FAILED = "FAILED"


class CompleteAnswerStatus(StrEnum):
    ANSWERED = "ANSWERED"
    PARTIAL = "PARTIAL"
    ABSTAINED = "ABSTAINED"
    MODEL_ERROR = "MODEL_ERROR"
    VALIDATION_FAILED = "VALIDATION_FAILED"


class CompleteSourceAvailability(StrEnum):
    AVAILABLE = "AVAILABLE"
    ARTIFACT_ROLE_UNAVAILABLE = "ARTIFACT_ROLE_UNAVAILABLE"
    SOURCE_MATERIALIZATION_UNAVAILABLE = "SOURCE_MATERIALIZATION_UNAVAILABLE"


class CompleteAnswerRequest(Base):
    __tablename__ = "complete_answer_requests"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    corpus_build_id: Mapped[str] = mapped_column(
        ForeignKey("corpus_builds.id"), nullable=False
    )
    question: Mapped[str] = mapped_column(Text, nullable=False)
    question_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    contract_revision: Mapped[str] = mapped_column(String(100), nullable=False)
    orchestration_revision: Mapped[str] = mapped_column(String(100), nullable=False)
    orchestration_config: Mapped[dict] = mapped_column(JSON, nullable=False)
    orchestration_config_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    request_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    sources: Mapped[list["CompleteAnswerRequestSource"]] = relationship(
        back_populates="request"
    )
    aspects: Mapped[list["CompleteAnswerRequestedAspect"]] = relationship(
        back_populates="request"
    )
    runs: Mapped[list["CompleteAnswerRun"]] = relationship(back_populates="request")
    build: Mapped["CorpusBuild"] = relationship()

    __table_args__ = (
        UniqueConstraint("corpus_build_id", "request_digest"),
        UniqueConstraint("id", "corpus_build_id"),
        Index(
            "ix_complete_answer_requests_build_created",
            "corpus_build_id",
            "created_at",
        ),
    )


class CompleteAnswerRequestSource(Base):
    __tablename__ = "complete_answer_request_sources"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    complete_answer_request_id: Mapped[str] = mapped_column(
        ForeignKey("complete_answer_requests.id"), nullable=False
    )
    document_family: Mapped[str] = mapped_column(String(20), nullable=False)
    source_order: Mapped[int] = mapped_column(Integer, nullable=False)
    source_config: Mapped[dict] = mapped_column(JSON, nullable=False)
    source_config_digest: Mapped[str] = mapped_column(String(64), nullable=False)

    request: Mapped[CompleteAnswerRequest] = relationship(back_populates="sources")
    inputs: Mapped[list["CompleteAnswerSourceInput"]] = relationship(
        back_populates="request_source", overlaps="inputs,requested_aspect"
    )

    __table_args__ = (
        UniqueConstraint("complete_answer_request_id", "document_family"),
        UniqueConstraint("complete_answer_request_id", "source_order"),
        UniqueConstraint("id", "complete_answer_request_id"),
        UniqueConstraint("id", "complete_answer_request_id", "document_family"),
        CheckConstraint(
            "document_family IN ('MOS', 'LAYOUT', 'XSD')",
            name="ck_complete_request_source_family",
        ),
        Index(
            "ix_complete_answer_request_sources_request",
            "complete_answer_request_id",
        ),
    )


class CompleteAnswerRequestedAspect(Base):
    __tablename__ = "complete_answer_requested_aspects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    complete_answer_request_id: Mapped[str] = mapped_column(
        ForeignKey("complete_answer_requests.id"), nullable=False
    )
    aspect_key: Mapped[str] = mapped_column(String(300), nullable=False)
    aspect_order: Mapped[int] = mapped_column(Integer, nullable=False)
    subject_kind: Mapped[str] = mapped_column(String(100), nullable=False)
    subject_key: Mapped[str] = mapped_column(String(500), nullable=False)
    canonical_entity_id: Mapped[str | None] = mapped_column(
        ForeignKey("canonical_entities.id")
    )
    qualifiers: Mapped[dict] = mapped_column(JSON, nullable=False)
    aspect_digest: Mapped[str] = mapped_column(String(64), nullable=False)

    request: Mapped[CompleteAnswerRequest] = relationship(back_populates="aspects")
    canonical_entity: Mapped["CanonicalEntity | None"] = relationship()
    inputs: Mapped[list["CompleteAnswerSourceInput"]] = relationship(
        back_populates="requested_aspect", overlaps="inputs,request_source"
    )

    __table_args__ = (
        UniqueConstraint("complete_answer_request_id", "aspect_key"),
        UniqueConstraint("complete_answer_request_id", "aspect_order"),
        UniqueConstraint("id", "complete_answer_request_id"),
        Index(
            "ix_complete_answer_requested_aspects_request",
            "complete_answer_request_id",
        ),
    )


class CompleteAnswerSourceInput(Base):
    __tablename__ = "complete_answer_source_inputs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    complete_answer_request_id: Mapped[str] = mapped_column(
        ForeignKey("complete_answer_requests.id"), nullable=False
    )
    request_source_id: Mapped[str] = mapped_column(String(36), nullable=False)
    requested_aspect_id: Mapped[str] = mapped_column(String(36), nullable=False)
    requested_fact_id: Mapped[str] = mapped_column(
        ForeignKey("requested_facts.id"), nullable=False
    )
    input_order: Mapped[int] = mapped_column(Integer, nullable=False)
    retrieval_profile: Mapped[str] = mapped_column(String(100), nullable=False)
    query: Mapped[str] = mapped_column(Text, nullable=False)
    query_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    top_k: Mapped[int] = mapped_column(Integer, nullable=False)
    retrieval_config: Mapped[dict] = mapped_column(JSON, nullable=False)
    retrieval_config_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    assembly_config: Mapped[dict] = mapped_column(JSON, nullable=False)
    assembly_config_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    input_digest: Mapped[str] = mapped_column(String(64), nullable=False)

    request_source: Mapped[CompleteAnswerRequestSource] = relationship(
        back_populates="inputs", overlaps="inputs,requested_aspect"
    )
    requested_aspect: Mapped[CompleteAnswerRequestedAspect] = relationship(
        back_populates="inputs", overlaps="inputs,request_source"
    )
    requested_fact: Mapped["RequestedFact"] = relationship()

    __table_args__ = (
        ForeignKeyConstraint(
            ["request_source_id", "complete_answer_request_id"],
            [
                "complete_answer_request_sources.id",
                "complete_answer_request_sources.complete_answer_request_id",
            ],
        ),
        ForeignKeyConstraint(
            ["requested_aspect_id", "complete_answer_request_id"],
            [
                "complete_answer_requested_aspects.id",
                "complete_answer_requested_aspects.complete_answer_request_id",
            ],
        ),
        UniqueConstraint("request_source_id", "input_order"),
        UniqueConstraint("complete_answer_request_id", "input_digest"),
        CheckConstraint("top_k > 0", name="ck_complete_source_input_top_k"),
        Index(
            "ix_complete_answer_source_inputs_request",
            "complete_answer_request_id",
        ),
        Index("ix_complete_answer_source_inputs_fact", "requested_fact_id"),
    )


class CompleteAnswerRun(Base):
    __tablename__ = "complete_answer_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    complete_answer_request_id: Mapped[str] = mapped_column(String(36), nullable=False)
    corpus_build_id: Mapped[str] = mapped_column(
        ForeignKey("corpus_builds.id"), nullable=False
    )
    run_key: Mapped[str] = mapped_column(String(36), unique=True, nullable=False)
    execution_state: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str | None] = mapped_column(String(40))
    context_digest: Mapped[str | None] = mapped_column(String(64))
    failure_code: Mapped[str | None] = mapped_column(String(100))
    failure_details: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    synthesis_provider: Mapped[str | None] = mapped_column(String(50))
    synthesis_model_id: Mapped[str | None] = mapped_column(String(100))
    synthesis_model_config: Mapped[dict | None] = mapped_column(JSON)
    synthesis_model_config_digest: Mapped[str | None] = mapped_column(String(64))
    synthesis_contract_revision: Mapped[str | None] = mapped_column(String(100))
    synthesis_prompt_revision: Mapped[str | None] = mapped_column(String(100))
    synthesis_prompt_digest: Mapped[str | None] = mapped_column(String(64))
    synthesis_attempt_count: Mapped[int | None] = mapped_column(Integer)
    synthesis_provider_metadata: Mapped[dict | None] = mapped_column(JSON)
    synthesis_raw_response: Mapped[dict | str | None] = mapped_column(JSON)
    synthesis_rendered_answer: Mapped[str | None] = mapped_column(Text)
    synthesis_validation_summary: Mapped[dict | None] = mapped_column(JSON)

    request: Mapped[CompleteAnswerRequest] = relationship(back_populates="runs")
    build: Mapped["CorpusBuild"] = relationship(overlaps="request,runs")
    source_runs: Mapped[list["CompleteAnswerSourceRun"]] = relationship(
        back_populates="complete_run"
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["complete_answer_request_id", "corpus_build_id"],
            ["complete_answer_requests.id", "complete_answer_requests.corpus_build_id"],
        ),
        UniqueConstraint("id", "complete_answer_request_id"),
        CheckConstraint(
            "execution_state IN ('RUNNING', 'FINALIZED', 'FAILED')",
            name="ck_complete_answer_run_execution_state",
        ),
        Index(
            "ix_complete_answer_runs_request_created",
            "complete_answer_request_id",
            "created_at",
        ),
        Index("ix_complete_answer_runs_state", "execution_state"),
    )


class CompleteAnswerSourceRun(Base):
    __tablename__ = "complete_answer_source_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    complete_answer_run_id: Mapped[str] = mapped_column(String(36), nullable=False)
    complete_answer_request_id: Mapped[str] = mapped_column(String(36), nullable=False)
    request_source_id: Mapped[str] = mapped_column(String(36), nullable=False)
    answer_request_id: Mapped[str | None] = mapped_column(
        ForeignKey("answer_requests.id")
    )
    answer_run_id: Mapped[str | None] = mapped_column(ForeignKey("answer_runs.id"))
    document_family: Mapped[str] = mapped_column(String(20), nullable=False)
    source_order: Mapped[int] = mapped_column(Integer, nullable=False)
    availability: Mapped[str] = mapped_column(String(50), nullable=False)
    outcome_summary: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    complete_run: Mapped[CompleteAnswerRun] = relationship(back_populates="source_runs")
    request_source: Mapped[CompleteAnswerRequestSource] = relationship(
        overlaps="complete_run,source_runs"
    )
    answer_request: Mapped["AnswerRequest | None"] = relationship()
    answer_run: Mapped["AnswerRun | None"] = relationship()

    __table_args__ = (
        ForeignKeyConstraint(
            ["complete_answer_run_id", "complete_answer_request_id"],
            [
                "complete_answer_runs.id",
                "complete_answer_runs.complete_answer_request_id",
            ],
        ),
        ForeignKeyConstraint(
            [
                "request_source_id",
                "complete_answer_request_id",
                "document_family",
            ],
            [
                "complete_answer_request_sources.id",
                "complete_answer_request_sources.complete_answer_request_id",
                "complete_answer_request_sources.document_family",
            ],
        ),
        UniqueConstraint("complete_answer_run_id", "request_source_id"),
        UniqueConstraint("complete_answer_run_id", "source_order"),
        UniqueConstraint("answer_run_id"),
        CheckConstraint(
            "document_family IN ('MOS', 'LAYOUT', 'XSD')",
            name="ck_complete_source_run_family",
        ),
        CheckConstraint(
            "availability IN ('AVAILABLE', 'ARTIFACT_ROLE_UNAVAILABLE', "
            "'SOURCE_MATERIALIZATION_UNAVAILABLE')",
            name="ck_complete_source_run_availability",
        ),
        Index("ix_complete_answer_source_runs_complete", "complete_answer_run_id"),
        Index("ix_complete_answer_source_runs_answer_request", "answer_request_id"),
    )


class CompleteAnswerClaim(Base):
    __tablename__ = "complete_answer_claims"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    complete_answer_run_id: Mapped[str] = mapped_column(
        ForeignKey("complete_answer_runs.id"), nullable=False
    )
    claim_key: Mapped[str] = mapped_column(String(100), nullable=False)
    claim_order: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    text_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    validation_state: Mapped[str] = mapped_column(String(30), nullable=False)

    __table_args__ = (
        UniqueConstraint("complete_answer_run_id", "claim_key"),
        UniqueConstraint("complete_answer_run_id", "claim_order"),
        Index("ix_complete_answer_claims_run", "complete_answer_run_id"),
    )


class CompleteAnswerClaimFact(Base):
    __tablename__ = "complete_answer_claim_facts"

    complete_answer_claim_id: Mapped[str] = mapped_column(
        ForeignKey("complete_answer_claims.id"), primary_key=True
    )
    fact_resolution_id: Mapped[str] = mapped_column(
        ForeignKey("fact_resolutions.id"), primary_key=True
    )


class CompleteAnswerCitation(Base):
    __tablename__ = "complete_answer_citations"

    complete_answer_claim_id: Mapped[str] = mapped_column(
        ForeignKey("complete_answer_claims.id"), primary_key=True
    )
    evidence_unit_id: Mapped[str] = mapped_column(
        ForeignKey("evidence_units.id"), primary_key=True
    )
    citation_order: Mapped[int] = mapped_column(Integer, nullable=False)
    __table_args__ = (UniqueConstraint("complete_answer_claim_id", "citation_order"),)


class CompleteAnswerClaimComparison(Base):
    __tablename__ = "complete_answer_claim_comparisons"

    complete_answer_claim_id: Mapped[str] = mapped_column(
        ForeignKey("complete_answer_claims.id"), primary_key=True
    )
    comparison_id: Mapped[str] = mapped_column(
        ForeignKey("cross_source_comparisons.id"), primary_key=True
    )
