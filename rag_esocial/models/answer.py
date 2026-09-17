from datetime import datetime
from enum import StrEnum

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


class AnswerRunStatus(StrEnum):
    ANSWERED = "ANSWERED"
    PARTIAL = "PARTIAL"
    ABSTAINED = "ABSTAINED"
    MODEL_ERROR = "MODEL_ERROR"
    VALIDATION_FAILED = "VALIDATION_FAILED"


class AnswerRequest(Base):
    __tablename__ = "answer_requests"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    corpus_build_id: Mapped[str] = mapped_column(
        ForeignKey("corpus_builds.id"), nullable=False
    )
    document_family: Mapped[str] = mapped_column(String(20), nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    question_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    answer_contract_revision: Mapped[str] = mapped_column(String(100), nullable=False)
    prompt_revision: Mapped[str] = mapped_column(String(100), nullable=False)
    model_id: Mapped[str] = mapped_column(String(100), nullable=False)
    model_config: Mapped[dict] = mapped_column(JSON, nullable=False)
    model_config_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    request_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    __table_args__ = (UniqueConstraint("corpus_build_id", "request_digest"),)


class AnswerRequestFactResolution(Base):
    __tablename__ = "answer_request_fact_resolutions"
    answer_request_id: Mapped[str] = mapped_column(
        ForeignKey("answer_requests.id"), primary_key=True
    )
    fact_resolution_id: Mapped[str] = mapped_column(
        ForeignKey("fact_resolutions.id"), primary_key=True
    )
    request_order: Mapped[int] = mapped_column(Integer, nullable=False)


class AnswerRun(Base):
    __tablename__ = "answer_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    answer_request_id: Mapped[str] = mapped_column(
        ForeignKey("answer_requests.id"), nullable=False
    )
    run_key: Mapped[str] = mapped_column(String(36), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    model_id: Mapped[str] = mapped_column(String(100), nullable=False)
    model_config: Mapped[dict] = mapped_column(JSON, nullable=False)
    model_config_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    provider_metadata: Mapped[dict] = mapped_column(JSON, nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False)
    raw_response: Mapped[dict | None] = mapped_column(JSON)
    rendered_answer: Mapped[str | None] = mapped_column(Text)
    validation_summary: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class AnswerClaim(Base):
    __tablename__ = "answer_claims"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    answer_run_id: Mapped[str] = mapped_column(
        ForeignKey("answer_runs.id"), nullable=False
    )
    claim_key: Mapped[str] = mapped_column(String(100), nullable=False)
    claim_order: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    text_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    validation_state: Mapped[str] = mapped_column(String(30), nullable=False)
    __table_args__ = (UniqueConstraint("answer_run_id", "claim_key"),)


class AnswerClaimFact(Base):
    __tablename__ = "answer_claim_facts"
    answer_claim_id: Mapped[str] = mapped_column(
        ForeignKey("answer_claims.id"), primary_key=True
    )
    fact_resolution_id: Mapped[str] = mapped_column(
        ForeignKey("fact_resolutions.id"), primary_key=True
    )


class AnswerCitation(Base):
    __tablename__ = "answer_citations"
    answer_claim_id: Mapped[str] = mapped_column(
        ForeignKey("answer_claims.id"), primary_key=True
    )
    evidence_unit_id: Mapped[str] = mapped_column(
        ForeignKey("evidence_units.id"), primary_key=True
    )
    citation_order: Mapped[int] = mapped_column(Integer, nullable=False)
