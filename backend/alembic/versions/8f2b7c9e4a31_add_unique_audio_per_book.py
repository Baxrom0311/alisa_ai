"""add unique audio per book

Revision ID: 8f2b7c9e4a31
Revises: b4f2a1c9d8e3
Create Date: 2026-05-15 00:00:00.000000

"""
from alembic import op


# revision identifiers, used by Alembic.
revision = "8f2b7c9e4a31"
down_revision = "b4f2a1c9d8e3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("audio_files") as batch_op:
            batch_op.create_unique_constraint("uq_audio_files_book_id", ["book_id"])
    else:
        op.create_unique_constraint(
            "uq_audio_files_book_id",
            "audio_files",
            ["book_id"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("audio_files") as batch_op:
            batch_op.drop_constraint("uq_audio_files_book_id", type_="unique")
    else:
        op.drop_constraint(
            "uq_audio_files_book_id",
            "audio_files",
            type_="unique",
        )
