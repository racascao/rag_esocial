import sqlalchemy as sa
from alembic import op

revision = "0008_search_projection_fts"
down_revision = "0007_deterministic_facts"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "search_projections",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "corpus_build_id",
            sa.String(36),
            sa.ForeignKey("corpus_builds.id"),
            nullable=False,
        ),
        sa.Column("profile", sa.String(80), nullable=False),
        sa.Column("projection_revision", sa.String(100), nullable=False),
        sa.Column("projection_config", sa.JSON, nullable=False),
        sa.Column("projection_config_digest", sa.String(64), nullable=False),
        sa.Column("text_search_config", sa.String(80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "corpus_build_id",
            "profile",
            "projection_revision",
            "projection_config_digest",
        ),
    )
    op.create_table(
        "search_units",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "search_projection_id",
            sa.String(36),
            sa.ForeignKey("search_projections.id"),
            nullable=False,
        ),
        sa.Column("document_family", sa.String(20), nullable=False),
        sa.Column("unit_kind", sa.String(80), nullable=False),
        sa.Column(
            "root_citation_target_id",
            sa.String(36),
            sa.ForeignKey("citation_targets.id"),
            nullable=False,
        ),
        sa.Column(
            "canonical_entity_id", sa.String(36), sa.ForeignKey("canonical_entities.id")
        ),
        sa.Column("source_local_stable_path", sa.Text, nullable=False),
        sa.Column("title", sa.String(500)),
        sa.Column("search_text", sa.Text, nullable=False),
        sa.Column("technical_terms", sa.Text, nullable=False),
        sa.Column("deterministic_key", sa.String(600), nullable=False),
        sa.Column("search_vector", sa.Text, nullable=False),
        sa.UniqueConstraint("search_projection_id", "deterministic_key"),
    )
    op.execute(
        "ALTER TABLE search_units ALTER COLUMN search_vector TYPE tsvector "
        "USING search_vector::tsvector"
    )
    op.execute(
        "CREATE INDEX ix_search_units_vector ON search_units USING gin (search_vector)"
    )
    op.create_table(
        "search_unit_citation_targets",
        sa.Column(
            "search_unit_id",
            sa.String(36),
            sa.ForeignKey("search_units.id"),
            primary_key=True,
        ),
        sa.Column(
            "citation_target_id",
            sa.String(36),
            sa.ForeignKey("citation_targets.id"),
            primary_key=True,
        ),
        sa.Column("role", sa.String(20), nullable=False),
    )


def downgrade():
    op.drop_table("search_unit_citation_targets")
    op.drop_index("ix_search_units_vector", table_name="search_units")
    op.drop_table("search_units")
    op.drop_table("search_projections")
