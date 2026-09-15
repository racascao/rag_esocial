"""Add immutable corpus provenance tables."""

import sqlalchemy as sa
from alembic import op

revision = "0002_corpus_provenance"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "document_versions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("document_family", sa.String(20), nullable=False),
        sa.Column("version_label", sa.String(200), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("publisher", sa.String(300)),
        sa.Column("official_published_at", sa.DateTime(timezone=True)),
        sa.Column("effective_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "document_artifacts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "document_version_id",
            sa.String(36),
            sa.ForeignKey("document_versions.id"),
            nullable=False,
        ),
        sa.Column("artifact_role", sa.String(80), nullable=False),
        sa.Column("official_url", sa.Text, nullable=False),
        sa.Column("original_filename", sa.String(500), nullable=False),
        sa.Column("media_type", sa.String(200)),
        sa.Column("storage_path", sa.Text, nullable=False),
        sa.Column("sha256", sa.String(64)),
        sa.Column("size_bytes", sa.Integer),
        sa.Column("retrieved_at", sa.DateTime(timezone=True)),
        sa.Column("capture_method", sa.String(50), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "archive_members",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "artifact_id",
            sa.String(36),
            sa.ForeignKey("document_artifacts.id"),
            nullable=False,
        ),
        sa.Column("relative_path", sa.Text, nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("size_bytes", sa.Integer, nullable=False),
        sa.UniqueConstraint("artifact_id", "relative_path"),
    )
    op.create_table(
        "corpus_snapshots",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("slug", sa.String(200), unique=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("frozen_at", sa.DateTime(timezone=True)),
        sa.Column("manifest_sha256", sa.String(64)),
    )
    op.create_table(
        "snapshot_members",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "snapshot_id",
            sa.String(36),
            sa.ForeignKey("corpus_snapshots.id"),
            nullable=False,
        ),
        sa.Column("artifact_role", sa.String(80), nullable=False),
        sa.Column(
            "document_version_id",
            sa.String(36),
            sa.ForeignKey("document_versions.id"),
            nullable=False,
        ),
        sa.UniqueConstraint("snapshot_id", "artifact_role"),
    )


def downgrade() -> None:
    op.drop_table("snapshot_members")
    op.drop_table("corpus_snapshots")
    op.drop_table("archive_members")
    op.drop_table("document_artifacts")
    op.drop_table("document_versions")
