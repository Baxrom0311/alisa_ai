import pytest
from fastapi.testclient import TestClient
import io
from tests.audio_helpers import make_wav_audio, wav_upload_data


PDF_BYTES = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\n%%EOF\n"
JPEG_BYTES = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x02\x00\x00\x01\x00\x01\x00\x00"


def test_complete_user_flow(client: TestClient):
    """
    Integration test covering the complete user flow:
    register → login → admin creates book → upload cover + PDF → user adds to library →
    updates status + page → uploads audio → streams audio with Range → saves listening progress
    """
    
    # 1. Register admin user
    admin_data = {
        "email": "integration-admin@example.com",
        "password": "testpass123",
        "full_name": "Integration Admin"
    }
    register_response = client.post("/api/auth/register", json=admin_data)
    assert register_response.status_code == 201
    
    # 2. Login as admin
    admin_login_data = {
        "email": "integration-admin@example.com",
        "password": "testpass123"
    }
    login_response = client.post("/api/auth/login", json=admin_login_data)
    assert login_response.status_code == 200
    admin_token = login_response.json()["access_token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    
    # 3. Create category
    category_data = {
        "name": "Integration Fiction",
        "description": "Books for integration testing"
    }
    category_response = client.post("/api/categories", json=category_data, headers=admin_headers)
    assert category_response.status_code == 201
    category_id = category_response.json()["id"]
    
    # 4. Create book
    book_data = {
        "title": "Integration Test Book",
        "author": "Test Author",
        "description": "A book for integration testing",
        "category_id": category_id,
        "total_pages": 200
    }
    book_response = client.post("/api/books", json=book_data, headers=admin_headers)
    assert book_response.status_code == 201
    book_id = book_response.json()["id"]
    
    # 5. Upload book cover
    cover_content = JPEG_BYTES + b"fake image content"
    cover_files = {"file": ("cover.jpg", io.BytesIO(cover_content), "image/jpeg")}
    cover_response = client.post(f"/api/books/{book_id}/cover", files=cover_files, headers=admin_headers)
    assert cover_response.status_code == 200
    
    # 6. Upload book file
    book_content = PDF_BYTES + b"fake pdf content"
    book_files = {"file": ("book.pdf", io.BytesIO(book_content), "application/pdf")}
    file_response = client.post(f"/api/books/{book_id}/file", files=book_files, headers=admin_headers)
    assert file_response.status_code == 200
    
    # 7. Upload audio file
    audio_content = make_wav_audio(duration_seconds=3600, sample_rate=100)
    audio_files = {"file": ("audio.wav", io.BytesIO(audio_content), "audio/wav")}
    audio_data = wav_upload_data(duration_seconds=3600, sample_rate=100)
    audio_response = client.post(f"/api/books/{book_id}/audio", files=audio_files, data=audio_data, headers=admin_headers)
    assert audio_response.status_code == 201
    
    # 8. Register reader user
    reader_data = {
        "email": "integration-reader@example.com",
        "password": "testpass123",
        "full_name": "Integration Reader"
    }
    reader_register_response = client.post("/api/auth/register", json=reader_data)
    assert reader_register_response.status_code == 201

    # 9. Login as reader
    reader_login_data = {
        "email": "integration-reader@example.com",
        "password": "testpass123"
    }
    reader_login_response = client.post("/api/auth/login", json=reader_login_data)
    assert reader_login_response.status_code == 200
    reader_token = reader_login_response.json()["access_token"]
    reader_headers = {"Authorization": f"Bearer {reader_token}"}

    # 10. Add book to library
    library_add_response = client.post(f"/api/library/{book_id}", headers=reader_headers)
    assert library_add_response.status_code == 201
    
    # 11. Update reading status
    status_data = {"status": "reading", "is_favorite": True}
    status_response = client.put(f"/api/library/{book_id}/status", json=status_data, headers=reader_headers)
    assert status_response.status_code == 200
    
    # 12. Update reading progress
    progress_data = {"current_page": 50}
    progress_response = client.put(f"/api/library/{book_id}/progress", json=progress_data, headers=reader_headers)
    assert progress_response.status_code == 200
    
    # 13. Get library
    library_response = client.get("/api/library", headers=reader_headers)
    assert library_response.status_code == 200
    library_data = library_response.json()
    assert len(library_data["items"]) == 1
    library_entry = library_data["items"][0]
    assert library_entry["status"] == "reading"
    assert library_entry["is_favorite"] is True
    assert library_entry["current_page"] == 50
    
    # 14. Get favorites
    favorites_response = client.get("/api/library/favorites", headers=reader_headers)
    assert favorites_response.status_code == 200
    favorites_data = favorites_response.json()
    assert len(favorites_data) == 1
    
    # 15. Stream book file
    stream_response = client.get(f"/api/books/{book_id}/read", headers=reader_headers)
    assert stream_response.status_code == 200
    
    # 16. Stream audio file with a byte range
    audio_stream_response = client.get(
        f"/api/books/{book_id}/audio/stream",
        headers={**reader_headers, "Range": "bytes=2-5"}
    )
    assert audio_stream_response.status_code == 206
    assert audio_stream_response.headers["content-range"] == f"bytes 2-5/{len(audio_content)}"
    assert audio_stream_response.headers["content-length"] == "4"
    assert audio_stream_response.content == audio_content[2:6]
    
    # 17. Update audio progress
    audio_progress_data = {"position_seconds": 1800}
    audio_progress_response = client.put(
        f"/api/books/{book_id}/audio/progress",
        json=audio_progress_data,
        headers=reader_headers
    )
    assert audio_progress_response.status_code == 200
    
    # 18. Get audio progress
    get_audio_progress_response = client.get(f"/api/books/{book_id}/audio/progress", headers=reader_headers)
    assert get_audio_progress_response.status_code == 200
    audio_progress = get_audio_progress_response.json()
    assert audio_progress["position_seconds"] == 1800
    
    # 19. Test category books endpoint
    category_books_response = client.get(f"/api/categories/{category_id}/books")
    assert category_books_response.status_code == 200
    category_books = category_books_response.json()
    assert len(category_books) == 1
    assert category_books[0]["id"] == book_id
    
    # 20. Test book search
    search_response = client.get("/api/books?search=Integration")
    assert search_response.status_code == 200
    search_data = search_response.json()
    assert len(search_data["items"]) == 1
    assert search_data["items"][0]["id"] == book_id


def test_storage_abstraction_local(client: TestClient):
    """Test that local storage backend works correctly"""
    # Register and login
    user_data = {
        "email": "storage@example.com",
        "password": "testpass123",
        "full_name": "Storage Test User"
    }
    client.post("/api/auth/register", json=user_data)
    
    login_data = {
        "email": "storage@example.com",
        "password": "testpass123"
    }
    login_response = client.post("/api/auth/login", json=login_data)
    token = login_response.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    
    # Create book
    book_data = {
        "title": "Storage Test Book",
        "author": "Storage Author"
    }
    book_response = client.post("/api/books", json=book_data, headers=headers)
    book_id = book_response.json()["id"]
    
    # Test file upload and storage
    file_content = PDF_BYTES + b"test file content for storage"
    files = {"file": ("test.pdf", io.BytesIO(file_content), "application/pdf")}
    upload_response = client.post(f"/api/books/{book_id}/file", files=files, headers=headers)
    assert upload_response.status_code == 200
    
    # Verify file can be streamed (indicating storage worked)
    stream_response = client.get(f"/api/books/{book_id}/read", headers=headers)
    assert stream_response.status_code == 200
    
    # Test cover upload
    cover_content = JPEG_BYTES + b"test cover content"
    cover_files = {"file": ("cover.jpg", io.BytesIO(cover_content), "image/jpeg")}
    cover_response = client.post(f"/api/books/{book_id}/cover", files=cover_files, headers=headers)
    assert cover_response.status_code == 200


def test_validation_edge_cases(client: TestClient):
    """Test validation for edge cases and negative values"""
    # Register and login
    user_data = {
        "email": "validation@example.com",
        "password": "testpass123",
        "full_name": "Validation Test User"
    }
    client.post("/api/auth/register", json=user_data)
    
    login_data = {
        "email": "validation@example.com",
        "password": "testpass123"
    }
    login_response = client.post("/api/auth/login", json=login_data)
    token = login_response.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    
    # Create book and add to library
    book_data = {
        "title": "Validation Test Book",
        "author": "Validation Author"
    }
    book_response = client.post("/api/books", json=book_data, headers=headers)
    book_id = book_response.json()["id"]
    
    client.post(f"/api/library/{book_id}", headers=headers)
    
    # Test negative current_page validation
    negative_progress = {"current_page": -5}
    response = client.put(f"/api/library/{book_id}/progress", json=negative_progress, headers=headers)
    assert response.status_code == 422  # Validation error
    
    # Upload audio for audio validation tests
    audio_content = make_wav_audio()
    audio_files = {"file": ("test.wav", io.BytesIO(audio_content), "audio/wav")}
    audio_data = wav_upload_data()
    client.post(f"/api/books/{book_id}/audio", files=audio_files, data=audio_data, headers=headers)
    
    # Test negative audio progress validation
    negative_audio_progress = {"position_seconds": -10}
    response = client.put(f"/api/books/{book_id}/audio/progress", json=negative_audio_progress, headers=headers)
    assert response.status_code == 422  # Validation error
    
    # Test invalid audio format
    invalid_audio_files = {"file": ("test.xyz", io.BytesIO(audio_content), "audio/wav")}
    invalid_audio_data = {
        "format": "invalid_format",
        "duration_seconds": 120,
        "bitrate": 128
    }
    response = client.post(f"/api/books/999/audio", files=invalid_audio_files, data=invalid_audio_data, headers=headers)
    assert response.status_code == 400  # Bad request for invalid format
