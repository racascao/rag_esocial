"""Add structural MOS materialization tables."""

import sqlalchemy as sa
from alembic import op

revision = "0004_mos_structure"
down_revision = "0003_build_identity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mos_documents",
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
        "mos_topics",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "mos_document_id",
            sa.String(36),
            sa.ForeignKey("mos_documents.id"),
            nullable=False,
        ),
        sa.Column("chapter", sa.String(20), nullable=False),
        sa.Column("number", sa.String(100), nullable=False),
        sa.Column("title", sa.String(500)),
        sa.Column("parent_topic_id", sa.String(36), sa.ForeignKey("mos_topics.id")),
        sa.Column("source_local_stable_path", sa.Text, nullable=False),
        sa.Column("content", sa.Text),
        sa.Column("display_order", sa.Integer),
        sa.UniqueConstraint("mos_document_id", "source_local_stable_path"),
    )
    op.create_table(
        "mos_event_sections",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "mos_document_id",
            sa.String(36),
            sa.ForeignKey("mos_documents.id"),
            nullable=False,
        ),
        sa.Column("event_code", sa.String(10), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("source_local_stable_path", sa.Text, nullable=False),
        sa.UniqueConstraint("mos_document_id", "source_local_stable_path"),
    )
    op.create_table(
        "mos_event_metadata_blocks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "event_section_id",
            sa.String(36),
            sa.ForeignKey("mos_event_sections.id"),
            nullable=False,
        ),
        sa.Column("block_kind", sa.String(80), nullable=False),
        sa.Column("original_label", sa.String(200), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("source_local_stable_path", sa.Text, nullable=False),
    )
    op.create_table(
        "mos_event_topics",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "event_section_id",
            sa.String(36),
            sa.ForeignKey("mos_event_sections.id"),
            nullable=False,
        ),
        sa.Column("number", sa.String(100), nullable=False),
        sa.Column("title", sa.String(500)),
        sa.Column("source_local_stable_path", sa.Text, nullable=False),
    )
    op.create_table(
        "mos_event_subitems",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "event_section_id",
            sa.String(36),
            sa.ForeignKey("mos_event_sections.id"),
            nullable=False,
        ),
        sa.Column("number", sa.String(100), nullable=False),
        sa.Column("parent_number", sa.String(100)),
        sa.Column("title", sa.String(500)),
        sa.Column("source_local_stable_path", sa.Text, nullable=False),
    )
    op.create_table(
        "mos_content_blocks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "mos_document_id",
            sa.String(36),
            sa.ForeignKey("mos_documents.id"),
            nullable=False,
        ),
        sa.Column("source_local_stable_path", sa.Text, nullable=False),
        sa.Column("block_type", sa.String(80), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("extraction_kind", sa.String(80), nullable=False),
    )
    op.create_table(
        "mos_explicit_references",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "corpus_build_id",
            sa.String(36),
            sa.ForeignKey("corpus_builds.id"),
            nullable=False,
        ),
        sa.Column(
            "origin_citation_target_id",
            sa.String(36),
            sa.ForeignKey("citation_targets.id"),
            nullable=False,
        ),
        sa.Column("reference_kind", sa.String(80), nullable=False),
        sa.Column("raw_value", sa.String(300), nullable=False),
        sa.Column("normalized_value", sa.String(300)),
        sa.Column("extraction_kind", sa.String(80), nullable=False),
        sa.Column("resolution_status", sa.String(30), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("mos_explicit_references")
    op.drop_table("mos_content_blocks")
    op.drop_table("mos_event_subitems")
    op.drop_table("mos_event_topics")
    op.drop_table("mos_event_metadata_blocks")
    op.drop_table("mos_event_sections")
    op.drop_table("mos_topics")
    op.drop_table("mos_documents")
