from app.models import Base


EXPECTED_INDEXES = {
    "books": {"ix_books_category_id"},
    "library_entries": {
        "ix_library_entries_user_id",
        "ix_library_entries_book_id",
    },
    "listening_progress": {
        "ix_listening_progress_user_id",
        "ix_listening_progress_audio_id",
    },
    "book_tags": {
        "ix_book_tags_book_id",
        "ix_book_tags_tag_id",
    },
}


def test_expected_indexes_present():
    for table_name, expected_names in EXPECTED_INDEXES.items():
        table = Base.metadata.tables[table_name]
        index_names = {index.name for index in table.indexes}

        assert expected_names <= index_names
