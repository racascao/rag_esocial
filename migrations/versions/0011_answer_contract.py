import sqlalchemy as sa
from alembic import op

revision = "0011_answer_contract"
down_revision = "0010_requested_fact_resolution"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "answer_requests",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "corpus_build_id",
            sa.String(36),
            sa.ForeignKey("corpus_builds.id"),
            nullable=False,
        ),
        sa.Column("document_family", sa.String(20), nullable=False),
        sa.Column("question", sa.Text, nullable=False),
        sa.Column("question_digest", sa.String(64), nullable=False),
        sa.Column("answer_contract_revision", sa.String(100), nullable=False),
        sa.Column("prompt_revision", sa.String(100), nullable=False),
        sa.Column("model_id", sa.String(100), nullable=False),
        sa.Column("model_config", sa.JSON, nullable=False),
        sa.Column("model_config_digest", sa.String(64), nullable=False),
        sa.Column("request_digest", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("corpus_build_id", "request_digest"),
    )
    op.create_table(
        "answer_request_fact_resolutions",
        sa.Column(
            "answer_request_id",
            sa.String(36),
            sa.ForeignKey("answer_requests.id"),
            primary_key=True,
        ),
        sa.Column(
            "fact_resolution_id",
            sa.String(36),
            sa.ForeignKey("fact_resolutions.id"),
            primary_key=True,
        ),
        sa.Column("request_order", sa.Integer, nullable=False),
    )
    op.create_table(
        "answer_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "answer_request_id",
            sa.String(36),
            sa.ForeignKey("answer_requests.id"),
            nullable=False,
        ),
        sa.Column("run_key", sa.String(36), unique=True, nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("model_id", sa.String(100), nullable=False),
        sa.Column("model_config", sa.JSON, nullable=False),
        sa.Column("model_config_digest", sa.String(64), nullable=False),
        sa.Column("provider_metadata", sa.JSON, nullable=False),
        sa.Column("attempt_count", sa.Integer, nullable=False),
        sa.Column("raw_response", sa.JSON),
        sa.Column("rendered_answer", sa.Text),
        sa.Column("validation_summary", sa.JSON, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "answer_claims",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "answer_run_id",
            sa.String(36),
            sa.ForeignKey("answer_runs.id"),
            nullable=False,
        ),
        sa.Column("claim_key", sa.String(100), nullable=False),
        sa.Column("claim_order", sa.Integer, nullable=False),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("text_sha256", sa.String(64), nullable=False),
        sa.Column("validation_state", sa.String(30), nullable=False),
        sa.UniqueConstraint("answer_run_id", "claim_key"),
    )
    op.create_table(
        "answer_claim_facts",
        sa.Column(
            "answer_claim_id",
            sa.String(36),
            sa.ForeignKey("answer_claims.id"),
            primary_key=True,
        ),
        sa.Column(
            "fact_resolution_id",
            sa.String(36),
            sa.ForeignKey("fact_resolutions.id"),
            primary_key=True,
        ),
    )
    op.create_table(
        "answer_citations",
        sa.Column(
            "answer_claim_id",
            sa.String(36),
            sa.ForeignKey("answer_claims.id"),
            primary_key=True,
        ),
        sa.Column(
            "evidence_unit_id",
            sa.String(36),
            sa.ForeignKey("evidence_units.id"),
            primary_key=True,
        ),
        sa.Column("citation_order", sa.Integer, nullable=False),
    )


def downgrade():
    for table in (
        "answer_citations",
        "answer_claim_facts",
        "answer_claims",
        "answer_runs",
        "answer_request_fact_resolutions",
        "answer_requests",
    ):
        op.drop_table(table)
