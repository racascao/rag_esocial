import sqlalchemy as sa
from alembic import op

revision = "0007_deterministic_facts"
down_revision = "0006_xsd_structure"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "source_facts",
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
            "subject_entity_id", sa.String(36), sa.ForeignKey("canonical_entities.id")
        ),
        sa.Column("fact_type", sa.String(100), nullable=False),
        sa.Column("extraction_kind", sa.String(30), nullable=False),
        sa.Column("fact_key", sa.String(500), nullable=False),
        sa.Column("string_value", sa.Text),
        sa.Column("structured_value", sa.JSON),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("corpus_build_id", "fact_key"),
    )
    op.create_table(
        "reference_resolutions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "corpus_build_id",
            sa.String(36),
            sa.ForeignKey("corpus_builds.id"),
            nullable=False,
        ),
        sa.Column(
            "explicit_reference_id",
            sa.String(36),
            sa.ForeignKey("mos_explicit_references.id"),
            nullable=False,
        ),
        sa.Column("outcome", sa.String(30), nullable=False),
        sa.Column("strategy", sa.String(100), nullable=False),
        sa.Column("normalized_target_key", sa.String(500)),
        sa.Column(
            "target_entity_id", sa.String(36), sa.ForeignKey("canonical_entities.id")
        ),
        sa.Column(
            "target_citation_target_id",
            sa.String(36),
            sa.ForeignKey("citation_targets.id"),
        ),
        sa.Column("diagnostic", sa.JSON),
        sa.UniqueConstraint("corpus_build_id", "explicit_reference_id"),
    )
    op.create_table(
        "entity_relations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "corpus_build_id",
            sa.String(36),
            sa.ForeignKey("corpus_builds.id"),
            nullable=False,
        ),
        sa.Column(
            "source_entity_id",
            sa.String(36),
            sa.ForeignKey("canonical_entities.id"),
            nullable=False,
        ),
        sa.Column(
            "target_entity_id",
            sa.String(36),
            sa.ForeignKey("canonical_entities.id"),
            nullable=False,
        ),
        sa.Column("relation_type", sa.String(100), nullable=False),
        sa.Column("strategy", sa.String(100), nullable=False),
        sa.Column(
            "origin_citation_target_id",
            sa.String(36),
            sa.ForeignKey("citation_targets.id"),
        ),
        sa.Column(
            "explicit_reference_id",
            sa.String(36),
            sa.ForeignKey("mos_explicit_references.id"),
        ),
        sa.Column("provenance", sa.JSON),
        sa.UniqueConstraint(
            "corpus_build_id", "source_entity_id", "target_entity_id", "relation_type"
        ),
    )
    op.create_table(
        "resolved_facts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "corpus_build_id",
            sa.String(36),
            sa.ForeignKey("corpus_builds.id"),
            nullable=False,
        ),
        sa.Column(
            "subject_entity_id",
            sa.String(36),
            sa.ForeignKey("canonical_entities.id"),
            nullable=False,
        ),
        sa.Column("fact_type", sa.String(100), nullable=False),
        sa.Column("fact_key", sa.String(500), nullable=False),
        sa.Column("value", sa.JSON, nullable=False),
        sa.Column("resolution_strategy", sa.String(100), nullable=False),
        sa.Column("provenance", sa.JSON, nullable=False),
        sa.UniqueConstraint("corpus_build_id", "fact_key"),
    )


def downgrade():
    for name in (
        "resolved_facts",
        "entity_relations",
        "reference_resolutions",
        "source_facts",
    ):
        op.drop_table(name)
