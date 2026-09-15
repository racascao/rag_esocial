"""Add CorpusBuild and transversal identity registries."""

import sqlalchemy as sa
from alembic import op

revision = "0003_build_identity"
down_revision = "0002_corpus_provenance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "corpus_builds",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "corpus_snapshot_id",
            sa.String(36),
            sa.ForeignKey("corpus_snapshots.id"),
            nullable=False,
        ),
        sa.Column("parser_revision", sa.String(200), nullable=False),
        sa.Column("parser_config", sa.JSON, nullable=False),
        sa.Column("parser_config_digest", sa.String(64), nullable=False),
        sa.Column("build_digest", sa.String(64), unique=True, nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "citation_targets",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("stable_key", sa.String(500), unique=True, nullable=False),
        sa.Column(
            "document_version_id",
            sa.String(36),
            sa.ForeignKey("document_versions.id"),
            nullable=False,
        ),
        sa.Column("document_family", sa.String(20), nullable=False),
        sa.Column("target_kind", sa.String(80), nullable=False),
        sa.Column("source_local_stable_path", sa.Text, nullable=False),
        sa.Column("human_label", sa.String(500)),
        sa.Column("locator_metadata", sa.JSON),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("document_version_id", "source_local_stable_path"),
    )
    op.create_table(
        "corpus_build_citation_targets",
        sa.Column(
            "build_id",
            sa.String(36),
            sa.ForeignKey("corpus_builds.id"),
            primary_key=True,
        ),
        sa.Column(
            "citation_target_id",
            sa.String(36),
            sa.ForeignKey("citation_targets.id"),
            primary_key=True,
        ),
    )
    op.create_table(
        "canonical_entities",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("stable_key", sa.String(500), unique=True, nullable=False),
        sa.Column("entity_kind", sa.String(80), nullable=False),
        sa.Column("canonical_key", sa.String(300), nullable=False),
        sa.Column("display_name", sa.String(500)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("entity_kind", "canonical_key"),
    )


def downgrade() -> None:
    op.drop_table("corpus_build_citation_targets")
    op.drop_table("citation_targets")
    op.drop_table("canonical_entities")
    op.drop_table("corpus_builds")
