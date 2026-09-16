import sqlalchemy as sa
from alembic import op

revision = "0006_xsd_structure"
down_revision = "0005_layout_structure"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "xsd_package_documents",
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
        "xsd_event_schemas",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "package_document_id",
            sa.String(36),
            sa.ForeignKey("xsd_package_documents.id"),
            nullable=False,
        ),
        sa.Column("relative_path", sa.Text, nullable=False),
        sa.Column("schema_kind", sa.String(40), nullable=False),
        sa.Column("target_namespace", sa.Text),
        sa.Column("schema_key", sa.String(300), nullable=False),
        sa.Column("event_code", sa.String(20)),
        sa.Column("root_name", sa.String(300)),
        sa.Column("documentation", sa.Text),
        sa.Column("source_local_stable_path", sa.Text, nullable=False),
        sa.Column("locator_metadata", sa.JSON),
        sa.UniqueConstraint("package_document_id", "source_local_stable_path"),
    )
    op.create_table(
        "xsd_shared_types",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "package_document_id",
            sa.String(36),
            sa.ForeignKey("xsd_package_documents.id"),
            nullable=False,
        ),
        sa.Column("name", sa.String(300), nullable=False),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("target_namespace", sa.Text),
        sa.Column("base_qname", sa.String(300)),
        sa.Column("facets", sa.JSON),
        sa.Column("documentation", sa.Text),
        sa.Column("source_local_stable_path", sa.Text, nullable=False),
        sa.Column("locator_metadata", sa.JSON),
        sa.UniqueConstraint("package_document_id", "source_local_stable_path"),
    )
    op.create_table(
        "xsd_elements",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "package_document_id",
            sa.String(36),
            sa.ForeignKey("xsd_package_documents.id"),
            nullable=False,
        ),
        sa.Column(
            "owner_schema_id", sa.String(36), sa.ForeignKey("xsd_event_schemas.id")
        ),
        sa.Column(
            "owner_shared_type_id", sa.String(36), sa.ForeignKey("xsd_shared_types.id")
        ),
        sa.Column("parent_element_id", sa.String(36), sa.ForeignKey("xsd_elements.id")),
        sa.Column("name", sa.String(300), nullable=False),
        sa.Column("type_qname", sa.String(300)),
        sa.Column("ref_qname", sa.String(300)),
        sa.Column("min_occurs", sa.String(30)),
        sa.Column("max_occurs", sa.String(30)),
        sa.Column("nillable", sa.Boolean),
        sa.Column("default_value", sa.Text),
        sa.Column("fixed_value", sa.Text),
        sa.Column("facets", sa.JSON),
        sa.Column("documentation", sa.Text),
        sa.Column("source_local_stable_path", sa.Text, nullable=False),
        sa.Column("locator_metadata", sa.JSON),
        sa.UniqueConstraint("package_document_id", "source_local_stable_path"),
    )
    op.create_table(
        "xsd_enumerations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "package_document_id",
            sa.String(36),
            sa.ForeignKey("xsd_package_documents.id"),
            nullable=False,
        ),
        sa.Column("owner_element_id", sa.String(36), sa.ForeignKey("xsd_elements.id")),
        sa.Column(
            "owner_shared_type_id", sa.String(36), sa.ForeignKey("xsd_shared_types.id")
        ),
        sa.Column("value", sa.String(500), nullable=False),
        sa.Column("documentation", sa.Text),
        sa.Column("source_local_stable_path", sa.Text, nullable=False),
        sa.UniqueConstraint("package_document_id", "source_local_stable_path"),
    )


def downgrade():
    for name in (
        "xsd_enumerations",
        "xsd_elements",
        "xsd_shared_types",
        "xsd_event_schemas",
        "xsd_package_documents",
    ):
        op.drop_table(name)
