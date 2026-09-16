import sqlalchemy as sa
from alembic import op

revision = "0009_retrieval_evidence"
down_revision = "0008_search_projection_fts"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "evidence_sets",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "corpus_build_id",
            sa.String(36),
            sa.ForeignKey("corpus_builds.id"),
            nullable=False,
        ),
        sa.Column(
            "search_projection_id",
            sa.String(36),
            sa.ForeignKey("search_projections.id"),
            nullable=False,
        ),
        sa.Column("query", sa.Text, nullable=False),
        sa.Column("query_digest", sa.String(64), nullable=False),
        sa.Column("retrieval_revision", sa.String(100), nullable=False),
        sa.Column("retrieval_config", sa.JSON, nullable=False),
        sa.Column("retrieval_config_digest", sa.String(64), nullable=False),
        sa.Column("assembly_revision", sa.String(100), nullable=False),
        sa.Column("assembly_config", sa.JSON, nullable=False),
        sa.Column("assembly_config_digest", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "corpus_build_id",
            "search_projection_id",
            "query_digest",
            "retrieval_config_digest",
            "assembly_config_digest",
        ),
    )
    op.create_table(
        "evidence_units",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "corpus_build_id",
            sa.String(36),
            sa.ForeignKey("corpus_builds.id"),
            nullable=False,
        ),
        sa.Column(
            "citation_target_id",
            sa.String(36),
            sa.ForeignKey("citation_targets.id"),
            nullable=False,
        ),
        sa.Column(
            "canonical_entity_id", sa.String(36), sa.ForeignKey("canonical_entities.id")
        ),
        sa.Column("document_family", sa.String(20), nullable=False),
        sa.Column("source_local_stable_path", sa.Text, nullable=False),
        sa.Column("renderer_revision", sa.String(100), nullable=False),
        sa.Column("rendered_content", sa.Text, nullable=False),
        sa.Column("rendered_content_sha256", sa.String(64), nullable=False),
        sa.Column("metadata", sa.JSON, nullable=False),
        sa.UniqueConstraint(
            "corpus_build_id", "citation_target_id", "renderer_revision"
        ),
    )
    op.create_table(
        "evidence_set_items",
        sa.Column(
            "evidence_set_id",
            sa.String(36),
            sa.ForeignKey("evidence_sets.id"),
            primary_key=True,
        ),
        sa.Column(
            "evidence_unit_id",
            sa.String(36),
            sa.ForeignKey("evidence_units.id"),
            nullable=False,
        ),
        sa.Column(
            "source_search_unit_id",
            sa.String(36),
            sa.ForeignKey("search_units.id"),
            nullable=False,
        ),
        sa.Column("retrieval_rank", sa.Integer, nullable=False),
        sa.Column("retrieval_score", sa.Float, nullable=False),
        sa.Column("evidence_order", sa.Integer, nullable=False),
        sa.Column("inclusion_role", sa.String(20), nullable=False),
        sa.UniqueConstraint("evidence_set_id", "evidence_unit_id"),
    )


def downgrade():
    op.drop_table("evidence_set_items")
    op.drop_table("evidence_units")
    op.drop_table("evidence_sets")
