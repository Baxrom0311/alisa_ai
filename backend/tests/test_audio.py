import pytest
from fastapi import HTTPException, UploadFile
from fastapi.testclient import TestClient
import io
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from starlette.datastructures import Headers
from app.config import settings
from app.models.audio import AudioFile
from app.models.book import Book
from app.models.library import ListeningProgress
from app.models.user import User
from app.services.audio_service import get_progress, upload_audio
from app.services.storage_service import get_storage_backend
from tests.audio_helpers import (
    DEFAULT_AUDIO_DURATION_SECONDS,
    expected_wav_bitrate,
    make_wav_audio,
    wav_upload_data,
)


def multi_chunk_wav() -> bytes:
    return make_wav_audio(duration_seconds=5)


def create_admin_user(client: TestClient):
    """Helper to create admin user and return auth headers"""
    # Register admin user
    user_data = {
        "email": "admin@example.com",
        "password": "admin123",
        "full_name": "Admin User"
    }
    client.post("/api/auth/register", json=user_data)
    
    # Make user admin (direct DB update would be needed in real scenario)
    # For testing, we'll assume the first user is admin
    
    # Login
    login_data = {
        "email": "admin@example.com",
        "password": "admin123"
    }
    login_response = client.post("/api/auth/login", json=login_data)
    token = login_response.json()["access_token"]
    
    return {"Authorization": f"Bearer {token}"}


def create_test_book(client: TestClient, admin_headers: dict):
    """Helper to create a test book"""
    book_data = {
        "title": "Test Book",
        "author": "Test Author",
        "description": "A test book"
    }
    response = client.post("/api/books", json=book_data, headers=admin_headers)
    return response.json()["id"]


def upload_test_audio(
    client: TestClient,
    admin_headers: dict,
    book_id: int,
    audio_content: bytes | None = None,
) -> bytes:
    audio_content = audio_content or make_wav_audio()
    files = {"file": ("test.wav", io.BytesIO(audio_content), "audio/wav")}
    upload_response = client.post(
        f"/api/books/{book_id}/audio",
        files=files,
        data=wav_upload_data(),
        headers=admin_headers,
    )
    assert upload_response.status_code == 201
    return audio_content


def test_get_audio_stream_no_audio(client: TestClient):
    admin_headers = create_admin_user(client)
    book_id = create_test_book(client, admin_headers)
    
    response = client.get(f"/api/books/{book_id}/audio/stream", headers=admin_headers)
    assert response.status_code == 404


def test_get_audio_metadata_no_audio(client: TestClient):
    admin_headers = create_admin_user(client)
    book_id = create_test_book(client, admin_headers)

    response = client.get(f"/api/books/{book_id}/audio", headers=admin_headers)
    assert response.status_code == 404
    assert response.json()["detail"] == "Audio file not found"


def test_audio_read_endpoints_require_auth(client: TestClient):
    admin_headers = create_admin_user(client)
    book_id = create_test_book(client, admin_headers)

    metadata_response = client.get(f"/api/books/{book_id}/audio")
    assert metadata_response.status_code == 401

    stream_response = client.get(f"/api/books/{book_id}/audio/stream")
    assert stream_response.status_code == 401


def test_get_audio_progress_no_audio(client: TestClient):
    admin_headers = create_admin_user(client)
    book_id = create_test_book(client, admin_headers)
    
    response = client.get(f"/api/books/{book_id}/audio/progress", headers=admin_headers)
    assert response.status_code == 404


def test_save_audio_progress_no_audio(client: TestClient):
    admin_headers = create_admin_user(client)
    book_id = create_test_book(client, admin_headers)
    
    progress_data = {"position_seconds": 120.5}
    response = client.put(f"/api/books/{book_id}/audio/progress", json=progress_data, headers=admin_headers)
    assert response.status_code == 404


def test_upload_audio_success(client: TestClient):
    """Test successful audio upload"""
    admin_headers = create_admin_user(client)
    book_id = create_test_book(client, admin_headers)
    
    # Create a fake audio file
    audio_content = make_wav_audio()
    files = {"file": ("test.wav", io.BytesIO(audio_content), "audio/wav")}
    data = wav_upload_data()
    
    response = client.post(f"/api/books/{book_id}/audio", files=files, data=data, headers=admin_headers)
    assert response.status_code == 201
    response_data = response.json()
    assert response_data["format"] == "wav"
    assert response_data["duration_seconds"] == pytest.approx(DEFAULT_AUDIO_DURATION_SECONDS)


def test_upload_audio_derives_metadata_without_form_fields(client: TestClient):
    admin_headers = create_admin_user(client)
    book_id = create_test_book(client, admin_headers)

    audio_content = make_wav_audio()
    files = {"file": ("test.wav", io.BytesIO(audio_content), "audio/wav")}

    response = client.post(f"/api/books/{book_id}/audio", files=files, headers=admin_headers)

    assert response.status_code == 201
    response_data = response.json()
    assert response_data["format"] == "wav"
    assert response_data["duration_seconds"] == pytest.approx(DEFAULT_AUDIO_DURATION_SECONDS)
    assert response_data["bitrate"] == expected_wav_bitrate()


def test_get_audio_metadata_after_upload(client: TestClient):
    admin_headers = create_admin_user(client)
    book_id = create_test_book(client, admin_headers)

    audio_content = make_wav_audio()
    files = {"file": ("test.wav", io.BytesIO(audio_content), "audio/wav")}
    data = wav_upload_data()
    data["format"] = "WAV"

    upload_response = client.post(
        f"/api/books/{book_id}/audio",
        files=files,
        data=data,
        headers=admin_headers,
    )
    assert upload_response.status_code == 201

    response = client.get(f"/api/books/{book_id}/audio", headers=admin_headers)
    assert response.status_code == 200
    response_data = response.json()
    assert response_data["book_id"] == book_id
    assert response_data["format"] == "wav"
    assert response_data["duration_seconds"] == pytest.approx(DEFAULT_AUDIO_DURATION_SECONDS)
    assert response_data["bitrate"] == expected_wav_bitrate()
    assert response_data["file_size"] == len(audio_content)


def test_upload_audio_rejects_non_audio_file(client: TestClient):
    admin_headers = create_admin_user(client)
    book_id = create_test_book(client, admin_headers)

    files = {"file": ("test.txt", io.BytesIO(b"not audio"), "text/plain")}
    data = {
        "format": "mp3",
        "duration_seconds": 120,
        "bitrate": 128
    }

    response = client.post(f"/api/books/{book_id}/audio", files=files, data=data, headers=admin_headers)
    assert response.status_code == 400


def test_audio_progress_operations(client: TestClient):
    """Test audio progress save and retrieve"""
    admin_headers = create_admin_user(client)
    book_id = create_test_book(client, admin_headers)
    
    # Upload audio first
    audio_content = make_wav_audio()
    files = {"file": ("test.wav", io.BytesIO(audio_content), "audio/wav")}
    data = wav_upload_data()
    upload_response = client.post(f"/api/books/{book_id}/audio", files=files, data=data, headers=admin_headers)
    assert upload_response.status_code == 201
    
    # Save progress
    progress_data = {"position_seconds": 60}
    save_response = client.put(f"/api/books/{book_id}/audio/progress", json=progress_data, headers=admin_headers)
    assert save_response.status_code == 200
    
    # Get progress
    get_response = client.get(f"/api/books/{book_id}/audio/progress", headers=admin_headers)
    assert get_response.status_code == 200
    progress = get_response.json()
    assert progress["position_seconds"] == 60


def test_audio_progress_rejects_position_beyond_duration(client: TestClient):
    admin_headers = create_admin_user(client)
    book_id = create_test_book(client, admin_headers)

    audio_content = make_wav_audio()
    files = {"file": ("test.wav", io.BytesIO(audio_content), "audio/wav")}
    data = wav_upload_data()
    upload_response = client.post(f"/api/books/{book_id}/audio", files=files, data=data, headers=admin_headers)
    assert upload_response.status_code == 201

    response = client.put(
        f"/api/books/{book_id}/audio/progress",
        json={"position_seconds": 121},
        headers=admin_headers,
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Position cannot exceed audio duration"


def test_stream_audio_success(client: TestClient):
    """Test audio streaming"""
    admin_headers = create_admin_user(client)
    book_id = create_test_book(client, admin_headers)
    
    # Upload audio first
    audio_content = make_wav_audio()
    files = {"file": ("test.wav", io.BytesIO(audio_content), "audio/wav")}
    data = wav_upload_data()
    upload_response = client.post(f"/api/books/{book_id}/audio", files=files, data=data, headers=admin_headers)
    assert upload_response.status_code == 201
    
    # Stream audio
    stream_response = client.get(f"/api/books/{book_id}/audio/stream", headers=admin_headers)
    assert stream_response.status_code == 200
    # Note: The content-type will depend on the format mapping implementation


def test_stream_audio_supports_range_requests(client: TestClient):
    admin_headers = create_admin_user(client)
    book_id = create_test_book(client, admin_headers)

    audio_content = make_wav_audio()
    files = {"file": ("test.wav", io.BytesIO(audio_content), "audio/wav")}
    data = wav_upload_data()
    upload_response = client.post(f"/api/books/{book_id}/audio", files=files, data=data, headers=admin_headers)
    assert upload_response.status_code == 201

    stream_response = client.get(
        f"/api/books/{book_id}/audio/stream",
        headers={**admin_headers, "Range": "bytes=2-5"}
    )
    assert stream_response.status_code == 206
    assert stream_response.headers["content-range"] == f"bytes 2-5/{len(audio_content)}"
    assert stream_response.content == audio_content[2:6]


def test_stream_audio_head_returns_headers_without_body(client: TestClient):
    admin_headers = create_admin_user(client)
    book_id = create_test_book(client, admin_headers)
    audio_content = upload_test_audio(client, admin_headers, book_id)

    response = client.head(f"/api/books/{book_id}/audio/stream", headers=admin_headers)

    assert response.status_code == 200
    assert response.headers["content-length"] == str(len(audio_content))
    assert response.headers["accept-ranges"] == "bytes"
    assert response.content == b""


def test_stream_audio_head_range_returns_partial_headers_without_body(client: TestClient):
    admin_headers = create_admin_user(client)
    book_id = create_test_book(client, admin_headers)
    audio_content = upload_test_audio(client, admin_headers, book_id)

    response = client.head(
        f"/api/books/{book_id}/audio/stream",
        headers={**admin_headers, "Range": "bytes=0-3"},
    )

    assert response.status_code == 206
    assert response.headers["content-range"] == f"bytes 0-3/{len(audio_content)}"
    assert response.headers["content-length"] == "4"
    assert response.headers["accept-ranges"] == "bytes"
    assert response.content == b""


@pytest.mark.parametrize(
    "range_header",
    [
        "bytes=999999999-1000000000",
        "foo=0-1",
        "bytes=0-1,3-4",
    ],
)
def test_stream_audio_rejects_invalid_http_ranges(
    client: TestClient,
    range_header: str,
):
    admin_headers = create_admin_user(client)
    book_id = create_test_book(client, admin_headers)
    audio_content = upload_test_audio(client, admin_headers, book_id)

    response = client.get(
        f"/api/books/{book_id}/audio/stream",
        headers={**admin_headers, "Range": range_header},
    )

    assert response.status_code == 416
    assert response.headers["accept-ranges"] == "bytes"
    assert response.headers["content-range"] == f"bytes */{len(audio_content)}"


def test_stream_audio_supports_suffix_range_http_response(client: TestClient):
    admin_headers = create_admin_user(client)
    book_id = create_test_book(client, admin_headers)
    audio_content = upload_test_audio(client, admin_headers, book_id)
    expected_start = len(audio_content) - 3
    expected_end = len(audio_content) - 1

    response = client.get(
        f"/api/books/{book_id}/audio/stream",
        headers={**admin_headers, "Range": "bytes=-3"},
    )

    assert response.status_code == 206
    assert response.headers["content-range"] == (
        f"bytes {expected_start}-{expected_end}/{len(audio_content)}"
    )
    assert response.headers["content-length"] == "3"
    assert response.content == audio_content[-3:]


def test_stream_audio_supports_mid_file_range_for_multi_chunk_local_body(client: TestClient):
    admin_headers = create_admin_user(client)
    book_id = create_test_book(client, admin_headers)

    audio_content = multi_chunk_wav()
    files = {"file": ("test.wav", io.BytesIO(audio_content), "audio/wav")}
    data = wav_upload_data(duration_seconds=5)
    upload_response = client.post(f"/api/books/{book_id}/audio", files=files, data=data, headers=admin_headers)
    assert upload_response.status_code == 201

    start = 70_000
    end = 70_321
    stream_response = client.get(
        f"/api/books/{book_id}/audio/stream",
        headers={**admin_headers, "Range": f"bytes={start}-{end}"},
    )

    assert stream_response.status_code == 206
    assert stream_response.headers["content-range"] == f"bytes {start}-{end}/{len(audio_content)}"
    assert stream_response.headers["content-length"] == str(end - start + 1)
    assert stream_response.content == audio_content[start:end + 1]


def test_stream_audio_supports_suffix_range_for_multi_chunk_local_body(client: TestClient):
    admin_headers = create_admin_user(client)
    book_id = create_test_book(client, admin_headers)

    audio_content = multi_chunk_wav()
    files = {"file": ("test.wav", io.BytesIO(audio_content), "audio/wav")}
    data = wav_upload_data(duration_seconds=5)
    upload_response = client.post(f"/api/books/{book_id}/audio", files=files, data=data, headers=admin_headers)
    assert upload_response.status_code == 201

    suffix_length = 12_345
    start = len(audio_content) - suffix_length
    end = len(audio_content) - 1
    stream_response = client.get(
        f"/api/books/{book_id}/audio/stream",
        headers={**admin_headers, "Range": f"bytes=-{suffix_length}"},
    )

    assert stream_response.status_code == 206
    assert stream_response.headers["content-range"] == f"bytes {start}-{end}/{len(audio_content)}"
    assert stream_response.headers["content-length"] == str(suffix_length)
    assert stream_response.content == audio_content[-suffix_length:]


def test_upload_audio_rejects_format_mismatch(client: TestClient):
    admin_headers = create_admin_user(client)
    book_id = create_test_book(client, admin_headers)

    files = {"file": ("test.wav", io.BytesIO(make_wav_audio()), "audio/wav")}
    data = wav_upload_data()
    data["format"] = "ogg"

    response = client.post(f"/api/books/{book_id}/audio", files=files, data=data, headers=admin_headers)
    assert response.status_code == 400
    assert "does not match detected" in response.json()["detail"]


def test_upload_audio_rejects_duration_metadata_mismatch(client: TestClient):
    admin_headers = create_admin_user(client)
    book_id = create_test_book(client, admin_headers)

    files = {"file": ("test.wav", io.BytesIO(make_wav_audio()), "audio/wav")}
    data = wav_upload_data()
    data["duration_seconds"] = "60"

    response = client.post(f"/api/books/{book_id}/audio", files=files, data=data, headers=admin_headers)

    assert response.status_code == 400
    assert response.json()["detail"] == "Duration field does not match extracted audio metadata"


def test_upload_audio_rejects_bitrate_metadata_mismatch(client: TestClient):
    admin_headers = create_admin_user(client)
    book_id = create_test_book(client, admin_headers)

    files = {"file": ("test.wav", io.BytesIO(make_wav_audio()), "audio/wav")}
    data = wav_upload_data()
    data["bitrate"] = "1"

    response = client.post(f"/api/books/{book_id}/audio", files=files, data=data, headers=admin_headers)

    assert response.status_code == 400
    assert response.json()["detail"] == "Bitrate field does not match extracted audio metadata"


@pytest.mark.asyncio
async def test_get_audio_progress_default_does_not_create_row(db_session):
    user = User(
        email="audio-progress@example.com",
        full_name="Audio Progress User",
        hashed_password="hashed",
        is_admin=False,
    )
    book = Book(title="Audio Progress Book", author="Test Author")
    db_session.add_all([user, book])
    await db_session.flush()

    audio = AudioFile(
        book_id=book.id,
        file_path="audio/test.mp3",
        duration_seconds=120,
        format="mp3",
        bitrate=128,
        file_size=10,
    )
    db_session.add(audio)
    await db_session.commit()

    response = await get_progress(db_session, user.id, book.id)
    assert response.position_seconds == 0.0
    assert response.updated_at is None

    result = await db_session.execute(select(func.count(ListeningProgress.id)))
    assert result.scalar_one() == 0


@pytest.mark.asyncio
async def test_upload_audio_concurrent_insert_conflict_returns_409(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "STORAGE_BACKEND", "local")
    monkeypatch.setattr(settings, "LOCAL_STORAGE_PATH", str(tmp_path / "uploads"))

    book = Book(title="Race Book", author="Race Author")
    db_session.add(book)
    await db_session.commit()
    await db_session.refresh(book)

    async def raise_unique_conflict():
        raise IntegrityError(
            statement="INSERT INTO audio_files",
            params={},
            orig=Exception("unique audio per book"),
        )

    monkeypatch.setattr(db_session, "commit", raise_unique_conflict)
    upload = UploadFile(
        file=io.BytesIO(make_wav_audio()),
        filename="race.wav",
        headers=Headers({"content-type": "audio/wav"}),
    )

    with pytest.raises(HTTPException) as exc_info:
        await upload_audio(
            db_session,
            book.id,
            upload,
            duration_seconds=DEFAULT_AUDIO_DURATION_SECONDS,
            format="wav",
            bitrate=expected_wav_bitrate(),
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "Audio file already exists for this book"

    storage = get_storage_backend()
    audio_dir = storage.base_path / "audio"
    assert not audio_dir.exists() or list(audio_dir.iterdir()) == []


@pytest.mark.asyncio
async def test_upload_audio_removes_partial_file_after_non_http_storage_error(
    db_session,
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(settings, "STORAGE_BACKEND", "local")
    monkeypatch.setattr(settings, "LOCAL_STORAGE_PATH", str(tmp_path / "uploads"))

    book = Book(title="Partial Upload Book", author="Partial Author")
    db_session.add(book)
    await db_session.commit()
    await db_session.refresh(book)

    storage = get_storage_backend()
    captured = {}

    async def fail_after_partial_write(chunks, dest_path, content_type):
        captured["dest_path"] = dest_path
        target = storage.base_path / dest_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"partial")
        raise RuntimeError("boom")

    monkeypatch.setattr(storage, "save_stream", fail_after_partial_write)
    upload = UploadFile(
        file=io.BytesIO(make_wav_audio()),
        filename="partial.wav",
        headers=Headers({"content-type": "audio/wav"}),
    )

    with pytest.raises(RuntimeError, match="boom"):
        await upload_audio(
            db_session,
            book.id,
            upload,
            duration_seconds=DEFAULT_AUDIO_DURATION_SECONDS,
            format="wav",
            bitrate=expected_wav_bitrate(),
        )

    assert captured["dest_path"].startswith("audio/")
    assert not (storage.base_path / captured["dest_path"]).exists()
    audio_dir = storage.base_path / "audio"
    assert not audio_dir.exists() or list(audio_dir.iterdir()) == []
