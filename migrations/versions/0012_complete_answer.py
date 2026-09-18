import sqlalchemy as sa
from alembic import op

revision = "0012_complete_answer"
down_revision = "0011_answer_contract"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "complete_answer_requests",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "corpus_build_id",
            sa.String(36),
            sa.ForeignKey("corpus_builds.id"),
            nullable=False,
        ),
        sa.Column("question", sa.Text, nullable=False),
        sa.Column("question_digest", sa.String(64), nullable=False),
        sa.Column("contract_revision", sa.String(100), nullable=False),
        sa.Column("orchestration_revision", sa.String(100), nullable=False),
        sa.Column("orchestration_config", sa.JSON, nullable=False),
        sa.Column("orchestration_config_digest", sa.String(64), nullable=False),
        sa.Column("request_digest", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("corpus_build_id", "request_digest"),
        sa.UniqueConstraint("id", "corpus_build_id"),
    )
    op.create_index(
        "ix_complete_answer_requests_build_created",
        "complete_answer_requests",
        ["corpus_build_id", "created_at"],
    )
    op.create_table(
        "complete_answer_request_sources",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "complete_answer_request_id",
            sa.String(36),
            sa.ForeignKey("complete_answer_requests.id"),
            nullable=False,
        ),
        sa.Column("document_family", sa.String(20), nullable=False),
        sa.Column("source_order", sa.Integer, nullable=False),
        sa.Column("source_config", sa.JSON, nullable=False),
        sa.Column("source_config_digest", sa.String(64), nullable=False),
        sa.UniqueConstraint("complete_answer_request_id", "document_family"),
        sa.UniqueConstraint("complete_answer_request_id", "source_order"),
        sa.UniqueConstraint("id", "complete_answer_request_id"),
        sa.UniqueConstraint("id", "complete_answer_request_id", "document_family"),
        sa.CheckConstraint(
            "document_family IN ('MOS', 'LAYOUT', 'XSD')",
            name="ck_complete_request_source_family",
        ),
    )
    op.create_index(
        "ix_complete_answer_request_sources_request",
        "complete_answer_request_sources",
        ["complete_answer_request_id"],
    )
    op.create_table(
        "complete_answer_requested_aspects",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "complete_answer_request_id",
            sa.String(36),
            sa.ForeignKey("complete_answer_requests.id"),
            nullable=False,
        ),
        sa.Column("aspect_key", sa.String(300), nullable=False),
        sa.Column("aspect_order", sa.Integer, nullable=False),
        sa.Column("subject_kind", sa.String(100), nullable=False),
        sa.Column("subject_key", sa.String(500), nullable=False),
        sa.Column(
            "canonical_entity_id",
            sa.String(36),
            sa.ForeignKey("canonical_entities.id"),
        ),
        sa.Column("qualifiers", sa.JSON, nullable=False),
        sa.Column("aspect_digest", sa.String(64), nullable=False),
        sa.UniqueConstraint("complete_answer_request_id", "aspect_key"),
        sa.UniqueConstraint("complete_answer_request_id", "aspect_order"),
        sa.UniqueConstraint("id", "complete_answer_request_id"),
    )
    op.create_index(
        "ix_complete_answer_requested_aspects_request",
        "complete_answer_requested_aspects",
        ["complete_answer_request_id"],
    )
    op.create_table(
        "complete_answer_source_inputs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "complete_answer_request_id",
            sa.String(36),
            sa.ForeignKey("complete_answer_requests.id"),
            nullable=False,
        ),
        sa.Column("request_source_id", sa.String(36), nullable=False),
        sa.Column("requested_aspect_id", sa.String(36), nullable=False),
        sa.Column(
            "requested_fact_id",
            sa.String(36),
            sa.ForeignKey("requested_facts.id"),
            nullable=False,
        ),
        sa.Column("input_order", sa.Integer, nullable=False),
        sa.Column("retrieval_profile", sa.String(100), nullable=False),
        sa.Column("query", sa.Text, nullable=False),
        sa.Column("query_digest", sa.String(64), nullable=False),
        sa.Column("top_k", sa.Integer, nullable=False),
        sa.Column("retrieval_config", sa.JSON, nullable=False),
        sa.Column("retrieval_config_digest", sa.String(64), nullable=False),
        sa.Column("assembly_config", sa.JSON, nullable=False),
        sa.Column("assembly_config_digest", sa.String(64), nullable=False),
        sa.Column("input_digest", sa.String(64), nullable=False),
        sa.ForeignKeyConstraint(
            ["request_source_id", "complete_answer_request_id"],
            [
                "complete_answer_request_sources.id",
                "complete_answer_request_sources.complete_answer_request_id",
            ],
        ),
        sa.ForeignKeyConstraint(
            ["requested_aspect_id", "complete_answer_request_id"],
            [
                "complete_answer_requested_aspects.id",
                "complete_answer_requested_aspects.complete_answer_request_id",
            ],
        ),
        sa.UniqueConstraint("request_source_id", "input_order"),
        sa.UniqueConstraint("complete_answer_request_id", "input_digest"),
        sa.CheckConstraint("top_k > 0", name="ck_complete_source_input_top_k"),
    )
    op.create_index(
        "ix_complete_answer_source_inputs_request",
        "complete_answer_source_inputs",
        ["complete_answer_request_id"],
    )
    op.create_index(
        "ix_complete_answer_source_inputs_fact",
        "complete_answer_source_inputs",
        ["requested_fact_id"],
    )
    op.create_table(
        "complete_answer_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("complete_answer_request_id", sa.String(36), nullable=False),
        sa.Column(
            "corpus_build_id",
            sa.String(36),
            sa.ForeignKey("corpus_builds.id"),
            nullable=False,
        ),
        sa.Column("run_key", sa.String(36), unique=True, nullable=False),
        sa.Column("execution_state", sa.String(30), nullable=False),
        sa.Column("status", sa.String(40)),
        sa.Column("context_digest", sa.String(64)),
        sa.Column("failure_code", sa.String(100)),
        sa.Column("failure_details", sa.JSON),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["complete_answer_request_id", "corpus_build_id"],
            ["complete_answer_requests.id", "complete_answer_requests.corpus_build_id"],
        ),
        sa.UniqueConstraint("id", "complete_answer_request_id"),
        sa.CheckConstraint(
            "execution_state IN ('RUNNING', 'FINALIZED', 'FAILED')",
            name="ck_complete_answer_run_execution_state",
        ),
    )
    op.create_index(
        "ix_complete_answer_runs_request_created",
        "complete_answer_runs",
        ["complete_answer_request_id", "created_at"],
    )
    op.create_index(
        "ix_complete_answer_runs_state",
        "complete_answer_runs",
        ["execution_state"],
    )
    op.create_table(
        "complete_answer_source_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("complete_answer_run_id", sa.String(36), nullable=False),
        sa.Column("complete_answer_request_id", sa.String(36), nullable=False),
        sa.Column("request_source_id", sa.String(36), nullable=False),
        sa.Column(
            "answer_request_id",
            sa.String(36),
            sa.ForeignKey("answer_requests.id"),
        ),
        sa.Column("answer_run_id", sa.String(36), sa.ForeignKey("answer_runs.id")),
        sa.Column("document_family", sa.String(20), nullable=False),
        sa.Column("source_order", sa.Integer, nullable=False),
        sa.Column("availability", sa.String(50), nullable=False),
        sa.Column("outcome_summary", sa.JSON, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["complete_answer_run_id", "complete_answer_request_id"],
            [
                "complete_answer_runs.id",
                "complete_answer_runs.complete_answer_request_id",
            ],
        ),
        sa.ForeignKeyConstraint(
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
        sa.UniqueConstraint("complete_answer_run_id", "request_source_id"),
        sa.UniqueConstraint("complete_answer_run_id", "source_order"),
        sa.UniqueConstraint("answer_run_id"),
        sa.CheckConstraint(
            "document_family IN ('MOS', 'LAYOUT', 'XSD')",
            name="ck_complete_source_run_family",
        ),
        sa.CheckConstraint(
            "availability IN ('AVAILABLE', 'ARTIFACT_ROLE_UNAVAILABLE', "
            "'SOURCE_MATERIALIZATION_UNAVAILABLE')",
            name="ck_complete_source_run_availability",
        ),
    )
    op.create_index(
        "ix_complete_answer_source_runs_complete",
        "complete_answer_source_runs",
        ["complete_answer_run_id"],
    )
    op.create_index(
        "ix_complete_answer_source_runs_answer_request",
        "complete_answer_source_runs",
        ["answer_request_id"],
    )


def downgrade():
    for table in (
        "complete_answer_source_runs",
        "complete_answer_runs",
        "complete_answer_source_inputs",
        "complete_answer_requested_aspects",
        "complete_answer_request_sources",
        "complete_answer_requests",
    ):
        op.drop_table(table)
