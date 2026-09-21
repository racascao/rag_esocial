from datetime import datetime

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class CrossSourceComparison(Base):
    __tablename__ = "cross_source_comparisons"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    complete_answer_run_id: Mapped[str] = mapped_column(
        ForeignKey("complete_answer_runs.id"), nullable=False
    )
    requested_aspect_id: Mapped[str | None] = mapped_column(
        ForeignKey("complete_answer_requested_aspects.id")
    )
    comparison_key: Mapped[str] = mapped_column(String(500), nullable=False)
    comparison_order: Mapped[int] = mapped_column(Integer, nullable=False)
    comparison_kind: Mapped[str] = mapped_column(String(50), nullable=False)
    comparison_revision: Mapped[str] = mapped_column(String(100), nullable=False)
    details: Mapped[dict] = mapped_column(JSON, nullable=False)
    value_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    comparison_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    members: Mapped[list["CrossSourceComparisonMember"]] = relationship(
        back_populates="comparison", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint(
            "comparison_kind IN ('SAME_ASPECT_SAME_VALUE', "
            "'SAME_ASPECT_DIFFERENT_VALUE', 'COMPLEMENTARY', 'DIFFERENT_ASPECT', "
            "'NOT_COMPARABLE', 'SINGLE_SOURCE')",
            name="ck_cross_source_comparison_kind",
        ),
        CheckConstraint(
            "(comparison_kind = 'DIFFERENT_ASPECT' AND requested_aspect_id IS NULL) "
            "OR (comparison_kind <> 'DIFFERENT_ASPECT' AND "
            "requested_aspect_id IS NOT NULL)",
            name="ck_cross_source_comparison_aspect",
        ),
        Index("ix_cross_source_comparisons_run", "complete_answer_run_id"),
        Index("ix_cross_source_comparisons_aspect", "requested_aspect_id"),
    )


class CrossSourceComparisonMember(Base):
    __tablename__ = "cross_source_comparison_members"

    comparison_id: Mapped[str] = mapped_column(
        ForeignKey("cross_source_comparisons.id"), primary_key=True
    )
    source_input_id: Mapped[str] = mapped_column(
        ForeignKey("complete_answer_source_inputs.id"), primary_key=True
    )
    fact_resolution_id: Mapped[str] = mapped_column(
        ForeignKey("fact_resolutions.id"), primary_key=True
    )
    document_family: Mapped[str] = mapped_column(String(20), nullable=False)
    member_order: Mapped[int] = mapped_column(Integer, nullable=False)
    fact_ref: Mapped[str] = mapped_column(String(20), nullable=False)
    evidence_refs: Mapped[list] = mapped_column(JSON, nullable=False)
    normalized_value: Mapped[dict | list | str | int | float | bool | None] = (
        mapped_column(JSON, nullable=False)
    )
    normalized_value_digest: Mapped[str] = mapped_column(String(64), nullable=False)

    comparison: Mapped[CrossSourceComparison] = relationship(back_populates="members")

    __table_args__ = (
        Index("ix_cross_source_comparison_members_resolution", "fact_resolution_id"),
        Index("ix_cross_source_comparison_members_input", "source_input_id"),
    )
