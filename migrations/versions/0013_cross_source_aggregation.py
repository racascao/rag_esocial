import sqlalchemy as sa
from alembic import op

revision = "0013_cross_source_aggregation"
down_revision = "0012_complete_answer"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "cross_source_comparisons",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("complete_answer_run_id", sa.String(36), nullable=False),
        sa.Column("requested_aspect_id", sa.String(36)),
        sa.Column("comparison_key", sa.String(500), nullable=False),
        sa.Column("comparison_order", sa.Integer, nullable=False),
        sa.Column("comparison_kind", sa.String(50), nullable=False),
        sa.Column("comparison_revision", sa.String(100), nullable=False),
        sa.Column("details", sa.JSON, nullable=False),
        sa.Column("value_digest", sa.String(64), nullable=False),
        sa.Column("comparison_digest", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["complete_answer_run_id"], ["complete_answer_runs.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["requested_aspect_id"],
            ["complete_answer_requested_aspects.id"],
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "complete_answer_run_id", "comparison_key", name="uq_cross_comparison_key"
        ),
        sa.UniqueConstraint(
            "complete_answer_run_id",
            "comparison_order",
            name="uq_cross_comparison_order",
        ),
        sa.UniqueConstraint(
            "complete_answer_run_id",
            "comparison_digest",
            name="uq_cross_comparison_digest",
        ),
        sa.CheckConstraint(
            "comparison_kind IN ('SAME_ASPECT_SAME_VALUE', "
            "'SAME_ASPECT_DIFFERENT_VALUE', 'COMPLEMENTARY', 'DIFFERENT_ASPECT', "
            "'NOT_COMPARABLE', 'SINGLE_SOURCE')",
            name="ck_cross_source_comparison_kind",
        ),
        sa.CheckConstraint(
            "(comparison_kind = 'DIFFERENT_ASPECT' AND requested_aspect_id IS NULL) "
            "OR (comparison_kind <> 'DIFFERENT_ASPECT' AND "
            "requested_aspect_id IS NOT NULL)",
            name="ck_cross_source_comparison_aspect",
        ),
    )
    op.create_index(
        "ix_cross_source_comparisons_run",
        "cross_source_comparisons",
        ["complete_answer_run_id"],
    )
    op.create_index(
        "ix_cross_source_comparisons_aspect",
        "cross_source_comparisons",
        ["requested_aspect_id"],
    )
    op.create_table(
        "cross_source_comparison_members",
        sa.Column("comparison_id", sa.String(36), nullable=False),
        sa.Column("source_input_id", sa.String(36), nullable=False),
        sa.Column("fact_resolution_id", sa.String(36), nullable=False),
        sa.Column("document_family", sa.String(20), nullable=False),
        sa.Column("member_order", sa.Integer, nullable=False),
        sa.Column("fact_ref", sa.String(20), nullable=False),
        sa.Column("evidence_refs", sa.JSON, nullable=False),
        sa.Column("normalized_value", sa.JSON, nullable=False),
        sa.Column("normalized_value_digest", sa.String(64), nullable=False),
        sa.ForeignKeyConstraint(
            ["comparison_id"], ["cross_source_comparisons.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["source_input_id"],
            ["complete_answer_source_inputs.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["fact_resolution_id"], ["fact_resolutions.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint(
            "comparison_id", "source_input_id", "fact_resolution_id"
        ),
        sa.UniqueConstraint(
            "comparison_id", "member_order", name="uq_cross_comparison_member_order"
        ),
        sa.CheckConstraint(
            "document_family IN ('MOS', 'LAYOUT', 'XSD')",
            name="ck_cross_comparison_member_family",
        ),
    )
    op.create_index(
        "ix_cross_source_comparison_members_resolution",
        "cross_source_comparison_members",
        ["fact_resolution_id"],
    )
    op.create_index(
        "ix_cross_source_comparison_members_input",
        "cross_source_comparison_members",
        ["source_input_id"],
    )


def downgrade():
    op.drop_index(
        "ix_cross_source_comparison_members_input",
        table_name="cross_source_comparison_members",
    )
    op.drop_index(
        "ix_cross_source_comparison_members_resolution",
        table_name="cross_source_comparison_members",
    )
    op.drop_table("cross_source_comparison_members")
    op.drop_index(
        "ix_cross_source_comparisons_aspect",
        table_name="cross_source_comparisons",
    )
    op.drop_index(
        "ix_cross_source_comparisons_run",
        table_name="cross_source_comparisons",
    )
    op.drop_table("cross_source_comparisons")
