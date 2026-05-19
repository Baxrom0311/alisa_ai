"""add fk indexes

Revision ID: b4f2a1c9d8e3
Revises: 620064bf067f
Create Date: 2026-05-16 00:00:00.000000

"""
from alembic import op


# revision identifiers, used by Alembic.
revision = "b4f2a1c9d8e3"
down_revision = "620064bf067f"
branch_labels = None
depends_on = None


INDEXES = (
    ("ix_books_category_id", "books", ["category_id"]),
    ("ix_library_entries_user_id", "library_entries", ["user_id"]),
    ("ix_library_entries_book_id", "library_entries", ["book_id"]),
    ("ix_listening_progress_user_id", "listening_progress", ["user_id"]),
    ("ix_listening_progress_audio_id", "listening_progress", ["audio_id"]),
    ("ix_book_tags_book_id", "book_tags", ["book_id"]),
    ("ix_book_tags_tag_id", "book_tags", ["tag_id"]),
)


def upgrade() -> None:
    for index_name, table_name, columns in INDEXES:
        op.create_index(
            index_name,
            table_name,
            columns,
            unique=False,
            if_not_exists=True,
        )


def downgrade() -> None:
    for index_name, table_name, _columns in reversed(INDEXES):
        op.drop_index(index_name, table_name=table_name, if_exists=True)
