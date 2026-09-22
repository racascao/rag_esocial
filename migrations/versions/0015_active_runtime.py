import sqlalchemy as sa
from alembic import op

revision = "0015_active_runtime"
down_revision = "0014_complete_synthesis"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "active_runtimes",
        sa.Column("runtime_key", sa.String(80), primary_key=True),
        sa.Column("corpus_build_id", sa.String(36), nullable=False),
        sa.Column("search_projection_id", sa.String(36), nullable=False),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("generation", sa.Integer, nullable=False, server_default="1"),
        sa.ForeignKeyConstraint(["corpus_build_id"], ["corpus_builds.id"]),
        sa.ForeignKeyConstraint(["search_projection_id"], ["search_projections.id"]),
    )


def downgrade():
    op.drop_table("active_runtimes")
