"""Add structural Layout materialization tables."""

import sqlalchemy as sa
from alembic import op

revision = "0005_layout_structure"
down_revision = "0004_mos_structure"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "layout_documents",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "corpus_build_id",
            sa.String(36),
            sa.ForeignKey("corpus_builds.id"),
            nullable=False,
        ),
        sa.Column(
            "document_version_id",
            sa.String(36),
            sa.ForeignKey("document_versions.id"),
            nullable=False,
        ),
        sa.Column(
            "artifact_id",
            sa.String(36),
            sa.ForeignKey("document_artifacts.id"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "layout_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "layout_document_id",
            sa.String(36),
            sa.ForeignKey("layout_documents.id"),
            nullable=False,
        ),
        sa.Column("event_code", sa.String(10), nullable=False),
        sa.Column("title", sa.String(500)),
        sa.Column("source_local_stable_path", sa.Text, nullable=False),
        sa.Column("locator_metadata", sa.JSON),
        sa.UniqueConstraint("layout_document_id", "source_local_stable_path"),
    )
    op.create_table(
        "layout_groups",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "layout_event_id",
            sa.String(36),
            sa.ForeignKey("layout_events.id"),
            nullable=False,
        ),
        sa.Column("parent_group_id", sa.String(36), sa.ForeignKey("layout_groups.id")),
        sa.Column("technical_name", sa.String(300), nullable=False),
        sa.Column("level", sa.Integer, nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("occurrence", sa.String(100)),
        sa.Column("condition", sa.Text),
        sa.Column("source_local_stable_path", sa.Text, nullable=False),
        sa.Column("locator_metadata", sa.JSON),
        sa.UniqueConstraint("layout_event_id", "source_local_stable_path"),
    )
    op.create_table(
        "layout_fields",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "layout_group_id",
            sa.String(36),
            sa.ForeignKey("layout_groups.id"),
            nullable=False,
        ),
        sa.Column("technical_name", sa.String(300), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("field_type", sa.String(100)),
        sa.Column("occurrence", sa.String(100)),
        sa.Column("size", sa.String(100)),
        sa.Column("decimals", sa.String(100)),
        sa.Column("condition", sa.Text),
        sa.Column("source_local_stable_path", sa.Text, nullable=False),
        sa.Column("locator_metadata", sa.JSON),
        sa.UniqueConstraint("layout_group_id", "source_local_stable_path"),
    )


def downgrade() -> None:
    op.drop_table("layout_fields")
    op.drop_table("layout_groups")
    op.drop_table("layout_events")
    op.drop_table("layout_documents")
