import sqlalchemy as sa
from alembic import op

revision = "0014_complete_synthesis"
down_revision = "0013_cross_source_aggregation"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "complete_answer_runs", sa.Column("synthesis_provider", sa.String(50))
    )
    op.add_column(
        "complete_answer_runs", sa.Column("synthesis_model_id", sa.String(100))
    )
    op.add_column("complete_answer_runs", sa.Column("synthesis_model_config", sa.JSON))
    op.add_column(
        "complete_answer_runs",
        sa.Column("synthesis_model_config_digest", sa.String(64)),
    )
    op.add_column(
        "complete_answer_runs", sa.Column("synthesis_contract_revision", sa.String(100))
    )
    op.add_column(
        "complete_answer_runs", sa.Column("synthesis_prompt_revision", sa.String(100))
    )
    op.add_column(
        "complete_answer_runs", sa.Column("synthesis_prompt_digest", sa.String(64))
    )
    op.add_column(
        "complete_answer_runs", sa.Column("synthesis_attempt_count", sa.Integer)
    )
    op.add_column(
        "complete_answer_runs", sa.Column("synthesis_provider_metadata", sa.JSON)
    )
    op.add_column("complete_answer_runs", sa.Column("synthesis_raw_response", sa.JSON))
    op.add_column(
        "complete_answer_runs", sa.Column("synthesis_rendered_answer", sa.Text)
    )
    op.add_column(
        "complete_answer_runs", sa.Column("synthesis_validation_summary", sa.JSON)
    )

    op.create_table(
        "complete_answer_claims",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("complete_answer_run_id", sa.String(36), nullable=False),
        sa.Column("claim_key", sa.String(100), nullable=False),
        sa.Column("claim_order", sa.Integer, nullable=False),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("text_sha256", sa.String(64), nullable=False),
        sa.Column("validation_state", sa.String(30), nullable=False),
        sa.ForeignKeyConstraint(
            ["complete_answer_run_id"], ["complete_answer_runs.id"], ondelete="RESTRICT"
        ),
        sa.UniqueConstraint("complete_answer_run_id", "claim_key"),
        sa.UniqueConstraint("complete_answer_run_id", "claim_order"),
    )
    op.create_index(
        "ix_complete_answer_claims_run",
        "complete_answer_claims",
        ["complete_answer_run_id"],
    )
    op.create_table(
        "complete_answer_claim_facts",
        sa.Column("complete_answer_claim_id", sa.String(36), nullable=False),
        sa.Column("fact_resolution_id", sa.String(36), nullable=False),
        sa.ForeignKeyConstraint(
            ["complete_answer_claim_id"],
            ["complete_answer_claims.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["fact_resolution_id"], ["fact_resolutions.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("complete_answer_claim_id", "fact_resolution_id"),
    )
    op.create_table(
        "complete_answer_citations",
        sa.Column("complete_answer_claim_id", sa.String(36), nullable=False),
        sa.Column("evidence_unit_id", sa.String(36), nullable=False),
        sa.Column("citation_order", sa.Integer, nullable=False),
        sa.ForeignKeyConstraint(
            ["complete_answer_claim_id"],
            ["complete_answer_claims.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["evidence_unit_id"], ["evidence_units.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("complete_answer_claim_id", "evidence_unit_id"),
        sa.UniqueConstraint("complete_answer_claim_id", "citation_order"),
    )
    op.create_table(
        "complete_answer_claim_comparisons",
        sa.Column("complete_answer_claim_id", sa.String(36), nullable=False),
        sa.Column("comparison_id", sa.String(36), nullable=False),
        sa.ForeignKeyConstraint(
            ["complete_answer_claim_id"],
            ["complete_answer_claims.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["comparison_id"], ["cross_source_comparisons.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("complete_answer_claim_id", "comparison_id"),
    )


def downgrade():
    op.drop_table("complete_answer_claim_comparisons")
    op.drop_table("complete_answer_citations")
    op.drop_table("complete_answer_claim_facts")
    op.drop_index("ix_complete_answer_claims_run", table_name="complete_answer_claims")
    op.drop_table("complete_answer_claims")
    for column in (
        "synthesis_validation_summary",
        "synthesis_rendered_answer",
        "synthesis_raw_response",
        "synthesis_attempt_count",
        "synthesis_provider_metadata",
        "synthesis_prompt_digest",
        "synthesis_prompt_revision",
        "synthesis_contract_revision",
        "synthesis_model_config_digest",
        "synthesis_model_config",
        "synthesis_model_id",
        "synthesis_provider",
    ):
        op.drop_column("complete_answer_runs", column)
