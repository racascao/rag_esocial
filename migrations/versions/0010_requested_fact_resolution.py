import sqlalchemy as sa
from alembic import op

revision = "0010_requested_fact_resolution"
down_revision = "0009_retrieval_evidence"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_constraint("evidence_set_items_pkey", "evidence_set_items", type_="primary")
    op.create_primary_key(
        "evidence_set_items_pkey",
        "evidence_set_items",
        ["evidence_set_id", "evidence_unit_id"],
    )
    op.create_table(
        "requested_facts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "corpus_build_id",
            sa.String(36),
            sa.ForeignKey("corpus_builds.id"),
            nullable=False,
        ),
        sa.Column("request_revision", sa.String(100), nullable=False),
        sa.Column("fact_type", sa.String(100), nullable=False),
        sa.Column("subject_kind", sa.String(100), nullable=False),
        sa.Column("subject_key", sa.String(500), nullable=False),
        sa.Column(
            "canonical_entity_id", sa.String(36), sa.ForeignKey("canonical_entities.id")
        ),
        sa.Column("qualifiers", sa.JSON, nullable=False),
        sa.Column("request_payload", sa.JSON, nullable=False),
        sa.Column("request_digest", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("corpus_build_id", "request_digest"),
    )
    op.create_table(
        "fact_resolutions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "requested_fact_id",
            sa.String(36),
            sa.ForeignKey("requested_facts.id"),
            nullable=False,
        ),
        sa.Column("document_family", sa.String(20), nullable=False),
        sa.Column("evidence_set_id", sa.String(36), sa.ForeignKey("evidence_sets.id")),
        sa.Column("resolver_revision", sa.String(100), nullable=False),
        sa.Column("resolver_config", sa.JSON, nullable=False),
        sa.Column("resolver_config_digest", sa.String(64), nullable=False),
        sa.Column("runtime_status", sa.String(40), nullable=False),
        sa.Column("reason_code", sa.String(100)),
        sa.Column("resolved_value", sa.JSON),
        sa.Column("resolution_strategy", sa.String(100), nullable=False),
        sa.Column("provenance", sa.JSON, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "requested_fact_id",
            "document_family",
            "evidence_set_id",
            "resolver_config_digest",
        ),
    )
    op.create_table(
        "fact_resolution_supports",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "fact_resolution_id",
            sa.String(36),
            sa.ForeignKey("fact_resolutions.id"),
            nullable=False,
        ),
        sa.Column(
            "evidence_unit_id",
            sa.String(36),
            sa.ForeignKey("evidence_units.id"),
            nullable=False,
        ),
        sa.Column("source_fact_id", sa.String(36), sa.ForeignKey("source_facts.id")),
        sa.Column(
            "resolved_fact_id", sa.String(36), sa.ForeignKey("resolved_facts.id")
        ),
        sa.Column("support_role", sa.String(50), nullable=False),
        sa.Column("support_order", sa.Integer, nullable=False),
        sa.Column("provenance", sa.JSON, nullable=False),
        sa.UniqueConstraint(
            "fact_resolution_id",
            "evidence_unit_id",
            "source_fact_id",
            "resolved_fact_id",
        ),
    )


def downgrade():
    op.drop_table("fact_resolution_supports")
    op.drop_table("fact_resolutions")
    op.drop_table("requested_facts")
    op.drop_constraint("evidence_set_items_pkey", "evidence_set_items", type_="primary")
    op.create_primary_key(
        "evidence_set_items_pkey", "evidence_set_items", ["evidence_set_id"]
    )
