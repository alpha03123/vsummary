"""Courseware slide decks extracted from video streams."""

from alembic import op
import sqlalchemy as sa

revision = "0023_courseware_decks"
down_revision = "0022_study_plans"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "courseware_decks",
        sa.Column("id", sa.String(26), nullable=False),
        sa.Column("video_id", sa.String(26), nullable=False),
        sa.Column("content_version", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(1024), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["video_id"], ["videos.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("video_id", name="uq_courseware_decks_video"),
    )


def downgrade():
    op.drop_table("courseware_decks")
