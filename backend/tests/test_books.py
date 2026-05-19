import pytest
from fastapi.testclient import TestClient
import asyncio
import io
from sqlalchemy import select, func
from app.config import settings
from app.models.audio import AudioFile
from app.models.book import Book
from app.models.library import LibraryEntry, ListeningProgress
from app.models.user import User
from app.services.book_service import delete_book
from app.routers.books import _commit_uploaded_book_asset
from app.services.storage_service import get_storage_backend
from app.utils.file_validation import COVER_MAX_SIZE
from tests.audio_helpers import make_wav_audio, wav_upload_data


PDF_BYTES = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\n%%EOF\n"
JPEG_BYTES = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x02\x00\x00\x01\x00\x01\x00\x00"
PNG_BYTES = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"


def create_book_with_file(
    client: TestClient,
    auth_headers: dict,
    content: bytes = PDF_BYTES + b"0123456789",
) -> tuple[int, bytes]:
    create_response = client.post(
        "/api/books",
        json={"title": "Streamable Book", "author": "Test Author"},
        headers=auth_headers,
    )
    assert create_response.status_code == 201
    book_id = create_response.json()["id"]

    file_response = client.post(
        f"/api/books/{book_id}/file",
        files={"file": ("book.pdf", io.BytesIO(content), "application/pdf")},
        headers=auth_headers,
    )
    assert file_response.status_code == 200
    return book_id, content


def test_get_books_empty(client: TestClient):
    response = client.get("/api/books")
    assert response.status_code == 200
    data = response.json()
    assert data["items"] == []
    assert data["total"] == 0


def test_get_categories_empty(client: TestClient):
    response = client.get("/api/categories")
    assert response.status_code == 200
    assert response.json() == []


def test_get_nonexistent_book(client: TestClient):
    response = client.get("/api/books/999")
    assert response.status_code == 404


def test_books_pagination(client: TestClient):
    # Test with different pagination parameters
    response = client.get("/api/books?skip=0&limit=10")
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "total" in data
    assert data["skip"] == 0
    assert data["limit"] == 10


def test_books_search(client: TestClient):
    # Test search functionality (should work even with no results)
    response = client.get("/api/books?search=nonexistent")
    assert response.status_code == 200
    data = response.json()
    assert data["items"] == []


def test_books_filter_by_category(client: TestClient):
    # Test category filter (should work even with no results)
    response = client.get("/api/books?category_id=999")
    assert response.status_code == 200
    data = response.json()
    assert data["items"] == []


def test_books_filter_by_title_author_and_genre(client: TestClient, auth_headers):
    category_response = client.post(
        "/api/categories",
        json={"name": "Historical", "description": "History books"},
        headers=auth_headers,
    )
    assert category_response.status_code == 201
    category_id = category_response.json()["id"]

    first_book = {
        "title": "Silk Road Stories",
        "author": "A. Historian",
        "category_id": category_id,
    }
    second_book = {
        "title": "Modern Python",
        "author": "Tech Writer",
    }
    assert client.post("/api/books", json=first_book, headers=auth_headers).status_code == 201
    assert client.post("/api/books", json=second_book, headers=auth_headers).status_code == 201

    title_response = client.get("/api/books?title=silk")
    assert title_response.status_code == 200
    assert title_response.json()["total"] == 1
    assert title_response.json()["items"][0]["title"] == "Silk Road Stories"

    author_response = client.get("/api/books?author=tech")
    assert author_response.status_code == 200
    assert author_response.json()["total"] == 1
    assert author_response.json()["items"][0]["title"] == "Modern Python"

    genre_response = client.get("/api/books?genre=hist")
    assert genre_response.status_code == 200
    assert genre_response.json()["total"] == 1
    assert genre_response.json()["items"][0]["title"] == "Silk Road Stories"

    category_response = client.get("/api/books?category=histor")
    assert category_response.status_code == 200
    assert category_response.json()["total"] == 1
    assert category_response.json()["items"][0]["title"] == "Silk Road Stories"


def test_create_book_success(client: TestClient, auth_headers):
    """Test successful book creation"""
    book_data = {
        "title": "Test Book",
        "author": "Test Author",
        "description": "A test book",
        "total_pages": 100
    }
    response = client.post("/api/books", json=book_data, headers=auth_headers)
    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "Test Book"
    assert data["author"] == "Test Author"
    assert data["id"] is not None


def test_create_book_rejects_missing_category(client: TestClient, auth_headers):
    book_data = {
        "title": "Missing Category Book",
        "author": "Test Author",
        "category_id": 999
    }
    response = client.post("/api/books", json=book_data, headers=auth_headers)
    assert response.status_code == 404
    assert response.json()["detail"] == "Category not found"


def test_create_book_rejects_empty_title(client: TestClient, auth_headers):
    book_data = {
        "title": "",
        "author": "Test Author"
    }
    response = client.post("/api/books", json=book_data, headers=auth_headers)
    assert response.status_code == 422


def test_create_book_rejects_overlong_title(client: TestClient, auth_headers):
    book_data = {
        "title": "T" * 301,
        "author": "Test Author"
    }
    response = client.post("/api/books", json=book_data, headers=auth_headers)
    assert response.status_code == 422


def test_create_book_rejects_overlong_tag(client: TestClient, auth_headers):
    book_data = {
        "title": "Tagged",
        "author": "Test Author",
        "tags": ["t" * 41],
    }
    response = client.post("/api/books", json=book_data, headers=auth_headers)
    assert response.status_code == 422


def test_create_book_unauthorized(client: TestClient):
    """Test book creation without authentication"""
    book_data = {
        "title": "Test Book",
        "author": "Test Author"
    }
    response = client.post("/api/books", json=book_data)
    assert response.status_code == 401


def test_update_book_success(client: TestClient, auth_headers):
    """Test successful book update"""
    # First create a book
    book_data = {
        "title": "Original Title",
        "author": "Original Author"
    }
    create_response = client.post("/api/books", json=book_data, headers=auth_headers)
    assert create_response.status_code == 201
    book_id = create_response.json()["id"]
    
    # Update the book
    update_data = {
        "title": "Updated Title",
        "description": "Updated description"
    }
    response = client.put(f"/api/books/{book_id}", json=update_data, headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "Updated Title"
    assert data["description"] == "Updated description"
    assert data["author"] == "Original Author"  # Should remain unchanged


def test_update_book_rejects_missing_category(client: TestClient, auth_headers):
    book_data = {
        "title": "Original Title",
        "author": "Original Author"
    }
    create_response = client.post("/api/books", json=book_data, headers=auth_headers)
    assert create_response.status_code == 201
    book_id = create_response.json()["id"]

    response = client.put(
        f"/api/books/{book_id}",
        json={"category_id": 999},
        headers=auth_headers,
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Category not found"


def test_update_book_can_replace_and_clear_tags(client: TestClient, auth_headers):
    book_data = {
        "title": "Tagged Book",
        "author": "Tag Author",
        "tags": ["fiction", " classic ", "fiction"]
    }
    create_response = client.post("/api/books", json=book_data, headers=auth_headers)
    assert create_response.status_code == 201
    book_id = create_response.json()["id"]
    assert create_response.json()["tags"] == ["fiction", "classic"]

    update_response = client.put(
        f"/api/books/{book_id}",
        json={"tags": ["history"]},
        headers=auth_headers,
    )
    assert update_response.status_code == 200
    assert update_response.json()["tags"] == ["history"]

    old_tag_response = client.get("/api/books?tag=fiction")
    assert old_tag_response.status_code == 200
    assert old_tag_response.json()["total"] == 0

    clear_response = client.put(
        f"/api/books/{book_id}",
        json={"tags": []},
        headers=auth_headers,
    )
    assert clear_response.status_code == 200
    assert clear_response.json()["tags"] == []


def test_book_tags_are_normalized_and_filter_case_insensitive(client: TestClient, auth_headers):
    create_response = client.post(
        "/api/books",
        json={
            "title": "Normalized Tags",
            "author": "Tag Author",
            "tags": [" Fiction ", "fiction", "CLASSIC"],
        },
        headers=auth_headers,
    )

    assert create_response.status_code == 201
    assert create_response.json()["tags"] == ["fiction", "classic"]

    filter_response = client.get("/api/books?tag=FICTION")

    assert filter_response.status_code == 200
    assert filter_response.json()["total"] == 1
    assert filter_response.json()["items"][0]["title"] == "Normalized Tags"


@pytest.mark.asyncio
async def test_commit_uploaded_book_asset_deletes_new_file_on_commit_failure():
    class FailingDb:
        rolled_back = False

        async def commit(self):
            raise RuntimeError("commit failed")

        async def rollback(self):
            self.rolled_back = True

    class FakeStorage:
        def __init__(self):
            self.deleted_paths = []

        async def delete(self, path):
            self.deleted_paths.append(path)

    db = FailingDb()
    storage = FakeStorage()

    with pytest.raises(RuntimeError, match="commit failed"):
        await _commit_uploaded_book_asset(
            db,
            storage,
            "covers/new.jpg",
            "covers/old.jpg",
            "new cover upload",
            "old cover",
        )

    assert db.rolled_back is True
    assert storage.deleted_paths == ["covers/new.jpg"]


@pytest.mark.asyncio
async def test_commit_uploaded_book_asset_deletes_old_file_after_commit_success():
    class SuccessfulDb:
        committed = False
        rolled_back = False

        async def commit(self):
            self.committed = True

        async def rollback(self):
            self.rolled_back = True

    class FakeStorage:
        def __init__(self):
            self.deleted_paths = []

        async def delete(self, path):
            self.deleted_paths.append(path)

    db = SuccessfulDb()
    storage = FakeStorage()

    await _commit_uploaded_book_asset(
        db,
        storage,
        "books/new.pdf",
        "books/old.pdf",
        "new book upload",
        "old book file",
    )

    assert db.committed is True
    assert db.rolled_back is False
    assert storage.deleted_paths == ["books/old.pdf"]


def test_delete_book_success(client: TestClient, auth_headers):
    """Test successful book deletion"""
    # First create a book
    book_data = {
        "title": "Book to Delete",
        "author": "Test Author"
    }
    create_response = client.post("/api/books", json=book_data, headers=auth_headers)
    assert create_response.status_code == 201
    book_id = create_response.json()["id"]
    
    # Delete the book
    response = client.delete(f"/api/books/{book_id}", headers=auth_headers)
    assert response.status_code == 204
    
    # Verify book is deleted
    get_response = client.get(f"/api/books/{book_id}")
    assert get_response.status_code == 404


def test_upload_book_cover_replaces_old_storage_object(client: TestClient, auth_headers):
    book_data = {
        "title": "Book With Cover",
        "author": "Test Author"
    }
    create_response = client.post("/api/books", json=book_data, headers=auth_headers)
    assert create_response.status_code == 201
    book_id = create_response.json()["id"]

    first_files = {"file": ("cover.jpg", io.BytesIO(JPEG_BYTES + b"first cover"), "image/jpeg")}
    first_response = client.post(
        f"/api/books/{book_id}/cover",
        files=first_files,
        headers=auth_headers,
    )
    assert first_response.status_code == 200
    old_path = first_response.json()["path"]

    second_files = {"file": ("cover.jpg", io.BytesIO(JPEG_BYTES + b"second cover"), "image/jpeg")}
    second_response = client.post(
        f"/api/books/{book_id}/cover",
        files=second_files,
        headers=auth_headers,
    )
    assert second_response.status_code == 200
    new_path = second_response.json()["path"]
    assert new_path != old_path

    storage = get_storage_backend()
    assert asyncio.run(storage.exists(old_path)) is False
    assert asyncio.run(storage.exists(new_path)) is True


def test_public_cover_endpoint_and_cover_url(client: TestClient, auth_headers):
    create_response = client.post(
        "/api/books",
        json={"title": "Public Cover Book", "author": "Test Author"},
        headers=auth_headers,
    )
    assert create_response.status_code == 201
    book_id = create_response.json()["id"]

    cover_bytes = JPEG_BYTES + b"public cover bytes"
    upload_response = client.post(
        f"/api/books/{book_id}/cover",
        files={"file": ("cover.jpg", io.BytesIO(cover_bytes), "image/jpeg")},
        headers=auth_headers,
    )
    assert upload_response.status_code == 200
    assert upload_response.json()["cover_url"] == f"/api/books/{book_id}/cover"

    detail_response = client.get(f"/api/books/{book_id}")
    assert detail_response.status_code == 200
    assert detail_response.json()["cover_url"] == f"/api/books/{book_id}/cover"

    list_response = client.get("/api/books")
    assert list_response.status_code == 200
    assert list_response.json()["items"][0]["cover_url"] == f"/api/books/{book_id}/cover"

    cover_response = client.get(f"/api/books/{book_id}/cover")
    assert cover_response.status_code == 200
    assert cover_response.content == cover_bytes
    assert cover_response.headers["content-type"].startswith("image/jpeg")

    head_response = client.head(f"/api/books/{book_id}/cover")
    assert head_response.status_code == 200
    assert head_response.headers["content-length"] == str(len(cover_bytes))
    assert head_response.content == b""


def test_upload_book_file_replaces_old_storage_object(client: TestClient, auth_headers):
    book_data = {
        "title": "Book With File",
        "author": "Test Author"
    }
    create_response = client.post("/api/books", json=book_data, headers=auth_headers)
    assert create_response.status_code == 201
    book_id = create_response.json()["id"]

    first_files = {"file": ("book.pdf", io.BytesIO(PDF_BYTES + b"first pdf"), "application/pdf")}
    first_response = client.post(
        f"/api/books/{book_id}/file",
        files=first_files,
        headers=auth_headers,
    )
    assert first_response.status_code == 200
    old_path = first_response.json()["path"]

    second_files = {"file": ("book.pdf", io.BytesIO(PDF_BYTES + b"second pdf"), "application/pdf")}
    second_response = client.post(
        f"/api/books/{book_id}/file",
        files=second_files,
        headers=auth_headers,
    )
    assert second_response.status_code == 200
    new_path = second_response.json()["path"]
    assert new_path != old_path

    storage = get_storage_backend()
    assert asyncio.run(storage.exists(old_path)) is False
    assert asyncio.run(storage.exists(new_path)) is True


def test_upload_book_file_rejects_mismatched_magic_bytes(client: TestClient, auth_headers):
    create_response = client.post(
        "/api/books",
        json={"title": "Spoofed File", "author": "Test Author"},
        headers=auth_headers,
    )
    assert create_response.status_code == 201
    book_id = create_response.json()["id"]

    response = client.post(
        f"/api/books/{book_id}/file",
        files={"file": ("book.pdf", io.BytesIO(PNG_BYTES + b"not a pdf"), "application/pdf")},
        headers=auth_headers,
    )

    assert response.status_code == 400
    assert "not allowed" in response.json()["detail"]


def test_uploads_reject_oversize_content_length_before_handler(
    client: TestClient,
    auth_headers,
    monkeypatch,
):
    book_data = {
        "title": "Oversize Upload",
        "author": "Test Author"
    }
    create_response = client.post("/api/books", json=book_data, headers=auth_headers)
    assert create_response.status_code == 201
    book_id = create_response.json()["id"]

    async def fail_prepare(*args, **kwargs):
        raise AssertionError("upload handler should not read the file body")

    async def fail_audio_upload(*args, **kwargs):
        raise AssertionError("audio upload handler should not run")

    monkeypatch.setattr("app.routers.books.prepare_validated_upload", fail_prepare)
    monkeypatch.setattr("app.routers.audio.upload_audio", fail_audio_upload)

    cases = [
        (
            f"/api/books/{book_id}/cover",
            {"file": ("cover.jpg", io.BytesIO(JPEG_BYTES), "image/jpeg")},
            None,
            COVER_MAX_SIZE + 1,
        ),
        (
            f"/api/books/{book_id}/file",
            {"file": ("book.pdf", io.BytesIO(PDF_BYTES), "application/pdf")},
            None,
            settings.MAX_BOOK_FILE_SIZE + 1,
        ),
        (
            f"/api/books/{book_id}/audio",
            {"file": ("audio.wav", io.BytesIO(make_wav_audio()), "audio/wav")},
            wav_upload_data(),
            settings.MAX_AUDIO_FILE_SIZE + 1,
        ),
    ]

    for url, files, data, content_length in cases:
        response = client.post(
            url,
            files=files,
            data=data,
            headers={**auth_headers, "content-length": str(content_length)},
        )
        assert response.status_code == 413


def test_upload_book_file_replace_ignores_old_storage_delete_failure(
    client: TestClient,
    auth_headers,
    monkeypatch,
):
    book_data = {
        "title": "Book With Missing Old File",
        "author": "Test Author"
    }
    create_response = client.post("/api/books", json=book_data, headers=auth_headers)
    assert create_response.status_code == 201
    book_id = create_response.json()["id"]

    first_response = client.post(
        f"/api/books/{book_id}/file",
        files={"file": ("book.pdf", io.BytesIO(PDF_BYTES + b"first pdf"), "application/pdf")},
        headers=auth_headers,
    )
    assert first_response.status_code == 200
    old_path = first_response.json()["path"]
    storage = get_storage_backend()

    class DeleteFailingStorage:
        def __init__(self, wrapped, failing_path: str):
            self._wrapped = wrapped
            self._failing_path = failing_path

        async def save(self, file_data: bytes, path: str) -> str:
            return await self._wrapped.save(file_data, path)

        async def save_stream(self, chunks, path: str, content_type: str | None = None) -> str:
            return await self._wrapped.save_stream(chunks, path, content_type=content_type)

        async def delete(self, path: str) -> None:
            if path == self._failing_path:
                raise FileNotFoundError(path)
            await self._wrapped.delete(path)

    monkeypatch.setattr(
        "app.routers.books.get_storage_backend",
        lambda: DeleteFailingStorage(storage, old_path),
    )

    second_response = client.post(
        f"/api/books/{book_id}/file",
        files={"file": ("book.pdf", io.BytesIO(PDF_BYTES + b"second pdf"), "application/pdf")},
        headers=auth_headers,
    )
    assert second_response.status_code == 200
    new_path = second_response.json()["path"]
    assert new_path != old_path
    assert asyncio.run(storage.exists(new_path)) is True


def test_read_book_requires_auth(client: TestClient, auth_headers):
    create_response = client.post(
        "/api/books",
        json={"title": "Private Book", "author": "Test Author"},
        headers=auth_headers,
    )
    assert create_response.status_code == 201
    book_id = create_response.json()["id"]

    file_response = client.post(
        f"/api/books/{book_id}/file",
        files={"file": ("book.pdf", io.BytesIO(PDF_BYTES + b"pdf content"), "application/pdf")},
        headers=auth_headers,
    )
    assert file_response.status_code == 200

    response = client.get(f"/api/books/{book_id}/read")
    assert response.status_code == 401

    authed_response = client.get(f"/api/books/{book_id}/read", headers=auth_headers)
    assert authed_response.status_code == 200


def test_read_book_head_returns_headers_without_body(client: TestClient, auth_headers):
    book_id, content = create_book_with_file(client, auth_headers)

    response = client.head(f"/api/books/{book_id}/read", headers=auth_headers)

    assert response.status_code == 200
    assert response.headers["content-length"] == str(len(content))
    assert response.headers["accept-ranges"] == "bytes"
    assert response.content == b""


def test_read_book_head_range_returns_partial_headers_without_body(client: TestClient, auth_headers):
    book_id, content = create_book_with_file(client, auth_headers)

    response = client.head(
        f"/api/books/{book_id}/read",
        headers={**auth_headers, "Range": "bytes=0-3"},
    )

    assert response.status_code == 206
    assert response.headers["content-range"] == f"bytes 0-3/{len(content)}"
    assert response.headers["content-length"] == "4"
    assert response.headers["accept-ranges"] == "bytes"
    assert response.content == b""


@pytest.mark.parametrize(
    "range_header",
    [
        "bytes=999-1000",
        "foo=0-1",
        "bytes=0-1,3-4",
    ],
)
def test_read_book_rejects_invalid_http_ranges(
    client: TestClient,
    auth_headers,
    range_header: str,
):
    book_id, content = create_book_with_file(client, auth_headers)

    response = client.get(
        f"/api/books/{book_id}/read",
        headers={**auth_headers, "Range": range_header},
    )

    assert response.status_code == 416
    assert response.headers["accept-ranges"] == "bytes"
    assert response.headers["content-range"] == f"bytes */{len(content)}"


def test_read_book_supports_suffix_range_http_response(client: TestClient, auth_headers):
    book_id, content = create_book_with_file(client, auth_headers)
    expected_start = len(content) - 3
    expected_end = len(content) - 1

    response = client.get(
        f"/api/books/{book_id}/read",
        headers={**auth_headers, "Range": "bytes=-3"},
    )

    assert response.status_code == 206
    assert response.headers["content-range"] == (
        f"bytes {expected_start}-{expected_end}/{len(content)}"
    )
    assert response.headers["content-length"] == "3"
    assert response.content == content[-3:]


@pytest.mark.asyncio
async def test_delete_book_cascades_library_and_audio_progress(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "STORAGE_BACKEND", "local")
    monkeypatch.setattr(settings, "LOCAL_STORAGE_PATH", str(tmp_path / "uploads"))

    user = User(
        email="cascade@example.com",
        full_name="Cascade User",
        hashed_password="hashed",
        is_admin=True,
    )
    book = Book(title="Cascade Book", author="Cascade Author")
    db_session.add_all([user, book])
    await db_session.flush()

    audio = AudioFile(
        book_id=book.id,
        file_path="audio/missing.mp3",
        duration_seconds=120,
        format="mp3",
        bitrate=128,
        file_size=10,
    )
    library_entry = LibraryEntry(
        user_id=user.id,
        book_id=book.id,
        status="reading",
        current_page=5,
    )
    db_session.add_all([audio, library_entry])
    await db_session.flush()

    progress = ListeningProgress(
        user_id=user.id,
        audio_id=audio.id,
        position_seconds=42,
    )
    db_session.add(progress)
    await db_session.commit()

    await delete_book(db_session, book.id)

    for model in (Book, AudioFile, LibraryEntry, ListeningProgress):
        result = await db_session.execute(select(func.count(model.id)))
        assert result.scalar_one() == 0


def test_books_with_tags_filter(client: TestClient):
    """Test tag filtering in books list"""
    response = client.get("/api/books?tag=fiction")
    assert response.status_code == 200
    data = response.json()
    assert "items" in data


def test_create_book_with_tags_and_filter(client: TestClient, auth_headers):
    book_data = {
        "title": "Tagged Book",
        "author": "Tag Author",
        "tags": ["fiction", "classic"]
    }
    create_response = client.post("/api/books", json=book_data, headers=auth_headers)
    assert create_response.status_code == 201
    assert set(create_response.json()["tags"]) == {"fiction", "classic"}

    filter_response = client.get("/api/books?tag=fiction")
    assert filter_response.status_code == 200
    data = filter_response.json()
    assert data["total"] == 1
    assert data["items"][0]["title"] == "Tagged Book"
