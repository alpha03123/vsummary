"""Study plans for one video or a whole series."""

from alembic import op
import sqlalchemy as sa

revision = "0022_study_plans"
down_revision = "0021_incremental_rag_updates"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "study_plans",
        sa.Column("id", sa.String(26), nullable=False),
        sa.Column("video_id", sa.String(26), nullable=True),
        sa.Column("series_id", sa.String(26), nullable=True),
        sa.Column("content_version", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(1024), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["video_id"], ["videos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["series_id"], ["series.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("video_id", name="uq_study_plans_video"),
        sa.UniqueConstraint("series_id", name="uq_study_plans_series"),
    )


def downgrade():
    op.drop_table("study_plans")
