import pytest
from fastapi.testclient import TestClient
import io
from tests.audio_helpers import make_wav_audio, wav_upload_data


def create_user_and_login(client: TestClient, email: str = "user@example.com"):
    """Helper to create user and return auth headers"""
    user_data = {
        "email": email,
        "password": "user12345",
        "full_name": "Test User"
    }
    client.post("/api/auth/register", json=user_data)
    
    login_data = {
        "email": email,
        "password": "user12345"
    }
    login_response = client.post("/api/auth/login", json=login_data)
    token = login_response.json()["access_token"]
    
    return {"Authorization": f"Bearer {token}"}


def create_admin_and_book(client: TestClient):
    """Helper to create admin user and a test book"""
    admin_data = {
        "email": "admin@example.com",
        "password": "admin123",
        "full_name": "Admin User"
    }
    client.post("/api/auth/register", json=admin_data)
    
    login_data = {
        "email": "admin@example.com",
        "password": "admin123"
    }
    login_response = client.post("/api/auth/login", json=login_data)
    admin_token = login_response.json()["access_token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    
    book_data = {
        "title": "Test Book",
        "author": "Test Author",
        "description": "A test book"
    }
    book_response = client.post("/api/books", json=book_data, headers=admin_headers)
    book_id = book_response.json()["id"]
    
    return book_id


def create_admin_and_login(client: TestClient):
    admin_data = {
        "email": "library-admin@example.com",
        "password": "admin123",
        "full_name": "Admin User"
    }
    register_response = client.post("/api/auth/register", json=admin_data)
    assert register_response.status_code == 201

    login_response = client.post(
        "/api/auth/login",
        json={"email": "library-admin@example.com", "password": "admin123"},
    )
    assert login_response.status_code == 200
    return {"Authorization": f"Bearer {login_response.json()['access_token']}"}


def create_book_as_admin(client: TestClient, admin_headers: dict, title: str) -> int:
    response = client.post(
        "/api/books",
        json={"title": title, "author": "Test Author", "description": "A test book"},
        headers=admin_headers,
    )
    assert response.status_code == 201
    return response.json()["id"]


def upload_audio_as_admin(client: TestClient, admin_headers: dict, book_id: int) -> None:
    audio_content = make_wav_audio()
    response = client.post(
        f"/api/books/{book_id}/audio",
        files={"file": ("test.wav", io.BytesIO(audio_content), "audio/wav")},
        data=wav_upload_data(),
        headers=admin_headers,
    )
    assert response.status_code == 201


def test_get_empty_library(client: TestClient):
    headers = create_user_and_login(client)
    
    response = client.get("/api/library", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["items"] == []
    assert data["total"] == 0
    assert data["skip"] == 0
    assert data["limit"] == 20


def test_add_book_to_library(client: TestClient):
    book_id = create_admin_and_book(client)
    headers = create_user_and_login(client)
    
    response = client.post(f"/api/library/{book_id}", headers=headers)
    assert response.status_code == 201
    data = response.json()
    assert data["book_id"] == book_id
    assert data["status"] == "want_to_read"
    assert data["is_favorite"] == False


def test_add_duplicate_book_to_library(client: TestClient):
    book_id = create_admin_and_book(client)
    headers = create_user_and_login(client)
    
    # Add book first time
    response = client.post(f"/api/library/{book_id}", headers=headers)
    assert response.status_code == 201
    
    # Try to add again
    response = client.post(f"/api/library/{book_id}", headers=headers)
    assert response.status_code == 409


def test_update_book_status(client: TestClient):
    book_id = create_admin_and_book(client)
    headers = create_user_and_login(client)
    
    # Add book to library
    client.post(f"/api/library/{book_id}", headers=headers)
    
    # Update status
    status_data = {"status": "reading", "is_favorite": True}
    response = client.put(f"/api/library/{book_id}/status", json=status_data, headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "reading"
    assert data["is_favorite"] == True


def test_get_library_filters_by_status(client: TestClient):
    book_id = create_admin_and_book(client)
    headers = create_user_and_login(client)

    client.post(f"/api/library/{book_id}", headers=headers)
    status_data = {"status": "reading", "is_favorite": False}
    client.put(f"/api/library/{book_id}/status", json=status_data, headers=headers)

    response = client.get("/api/library?status=reading", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["status"] == "reading"

    response = client.get("/api/library?status=completed", headers=headers)
    assert response.status_code == 200
    assert response.json()["total"] == 0


def test_get_library_rejects_invalid_status_filter(client: TestClient):
    headers = create_user_and_login(client, "invalid-status@example.com")

    response = client.get("/api/library?status=archived", headers=headers)

    assert response.status_code == 422


def test_get_library_orders_newest_entries_first(client: TestClient):
    headers = create_user_and_login(client, "library-order@example.com")

    first_book = client.post(
        "/api/books",
        json={"title": "First Added", "author": "Test Author"},
        headers=headers,
    )
    assert first_book.status_code == 201
    first_book_id = first_book.json()["id"]

    second_book = client.post(
        "/api/books",
        json={"title": "Second Added", "author": "Test Author"},
        headers=headers,
    )
    assert second_book.status_code == 201
    second_book_id = second_book.json()["id"]

    assert client.post(f"/api/library/{first_book_id}", headers=headers).status_code == 201
    assert client.post(f"/api/library/{second_book_id}", headers=headers).status_code == 201

    response = client.get("/api/library", headers=headers)

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    assert [item["book_id"] for item in data["items"]] == [second_book_id, first_book_id]


def test_update_reading_progress(client: TestClient):
    book_id = create_admin_and_book(client)
    headers = create_user_and_login(client)
    
    # Add book to library
    client.post(f"/api/library/{book_id}", headers=headers)
    
    # Update progress
    progress_data = {"current_page": 50}
    response = client.put(f"/api/library/{book_id}/progress", json=progress_data, headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["current_page"] == 50
    assert data["status"] == "reading"  # Should auto-update to reading


def test_update_reading_progress_rejects_pages_beyond_total(client: TestClient):
    headers = create_user_and_login(client, "pages@example.com")
    book_data = {
        "title": "Short Book",
        "author": "Test Author",
        "total_pages": 10
    }
    create_response = client.post("/api/books", json=book_data, headers=headers)
    assert create_response.status_code == 201
    book_id = create_response.json()["id"]

    client.post(f"/api/library/{book_id}", headers=headers)

    response = client.put(
        f"/api/library/{book_id}/progress",
        json={"current_page": 11},
        headers=headers,
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Current page cannot exceed book total pages"


def test_update_reading_progress_marks_completed_at_total_pages(client: TestClient):
    headers = create_user_and_login(client, "complete@example.com")
    book_data = {
        "title": "Finite Book",
        "author": "Test Author",
        "total_pages": 10
    }
    create_response = client.post("/api/books", json=book_data, headers=headers)
    assert create_response.status_code == 201
    book_id = create_response.json()["id"]

    client.post(f"/api/library/{book_id}", headers=headers)

    response = client.put(
        f"/api/library/{book_id}/progress",
        json={"current_page": 10},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["status"] == "completed"


def test_update_reading_progress_reopens_completed_book(client: TestClient):
    headers = create_user_and_login(client, "reopen-completed@example.com")
    book_data = {
        "title": "Reopen Completed Book",
        "author": "Test Author",
        "total_pages": 10
    }
    create_response = client.post("/api/books", json=book_data, headers=headers)
    assert create_response.status_code == 201
    book_id = create_response.json()["id"]

    assert client.post(f"/api/library/{book_id}", headers=headers).status_code == 201

    completed_response = client.put(
        f"/api/library/{book_id}/progress",
        json={"current_page": 10},
        headers=headers,
    )
    assert completed_response.status_code == 200
    assert completed_response.json()["status"] == "completed"

    reopened_response = client.put(
        f"/api/library/{book_id}/progress",
        json={"current_page": 4},
        headers=headers,
    )
    assert reopened_response.status_code == 200
    assert reopened_response.json()["current_page"] == 4
    assert reopened_response.json()["status"] == "reading"


def test_get_favorites_empty(client: TestClient):
    headers = create_user_and_login(client)
    
    response = client.get("/api/library/favorites", headers=headers)
    assert response.status_code == 200
    assert response.json() == []


def test_get_library_activity_requires_auth(client: TestClient):
    response = client.get("/api/library/activity")

    assert response.status_code == 401


def test_get_library_activity_orders_by_recent_progress(client: TestClient):
    headers = create_user_and_login(client, "activity@example.com")

    first_book = client.post(
        "/api/books",
        json={"title": "Recently Read", "author": "Reader", "total_pages": 25},
        headers=headers,
    )
    assert first_book.status_code == 201
    first_book_id = first_book.json()["id"]

    second_book = client.post(
        "/api/books",
        json={"title": "Only Added", "author": "Reader"},
        headers=headers,
    )
    assert second_book.status_code == 201
    second_book_id = second_book.json()["id"]

    assert client.post(f"/api/library/{first_book_id}", headers=headers).status_code == 201
    assert client.post(f"/api/library/{second_book_id}", headers=headers).status_code == 201

    progress_response = client.put(
        f"/api/library/{first_book_id}/progress",
        json={"current_page": 5},
        headers=headers,
    )
    assert progress_response.status_code == 200

    response = client.get("/api/library/activity?skip=0&limit=1", headers=headers)

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    assert data["skip"] == 0
    assert data["limit"] == 1
    assert len(data["items"]) == 1
    assert data["items"][0]["book_id"] == first_book_id
    assert data["items"][0]["last_read_at"] is not None

    full_response = client.get("/api/library/activity", headers=headers)
    assert full_response.status_code == 200
    book_ids = [item["book_id"] for item in full_response.json()["items"]]
    assert book_ids[0] == first_book_id
    assert set(book_ids) == {first_book_id, second_book_id}


def test_audio_progress_updates_library_activity(client: TestClient):
    admin_headers = create_admin_and_login(client)
    audio_book_id = create_book_as_admin(client, admin_headers, "Audio Activity")
    added_only_book_id = create_book_as_admin(client, admin_headers, "Only Added")
    upload_audio_as_admin(client, admin_headers, audio_book_id)
    reader_headers = create_user_and_login(client, "audio-reader@example.com")

    assert client.post(f"/api/library/{audio_book_id}", headers=reader_headers).status_code == 201
    assert client.post(f"/api/library/{added_only_book_id}", headers=reader_headers).status_code == 201

    progress_response = client.put(
        f"/api/books/{audio_book_id}/audio/progress",
        json={"position_seconds": 30},
        headers=reader_headers,
    )
    assert progress_response.status_code == 200

    response = client.get("/api/library/activity?skip=0&limit=2", headers=reader_headers)

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    assert data["items"][0]["book_id"] == audio_book_id
    assert data["items"][0]["last_read_at"] is not None
    assert {item["book_id"] for item in data["items"]} == {audio_book_id, added_only_book_id}


def test_audio_progress_without_library_entry_does_not_create_library_entry(client: TestClient):
    admin_headers = create_admin_and_login(client)
    book_id = create_book_as_admin(client, admin_headers, "Audio Without Library")
    upload_audio_as_admin(client, admin_headers, book_id)
    reader_headers = create_user_and_login(client, "audio-no-library@example.com")

    progress_response = client.put(
        f"/api/books/{book_id}/audio/progress",
        json={"position_seconds": 30},
        headers=reader_headers,
    )
    assert progress_response.status_code == 200

    library_response = client.get("/api/library", headers=reader_headers)
    assert library_response.status_code == 200
    assert library_response.json()["total"] == 0

    activity_response = client.get("/api/library/activity", headers=reader_headers)
    assert activity_response.status_code == 200
    assert activity_response.json()["total"] == 0


def test_get_favorites_with_favorite_book(client: TestClient):
    book_id = create_admin_and_book(client)
    headers = create_user_and_login(client)
    
    # Add book to library
    client.post(f"/api/library/{book_id}", headers=headers)
    
    # Mark as favorite
    status_data = {"status": "reading", "is_favorite": True}
    client.put(f"/api/library/{book_id}/status", json=status_data, headers=headers)
    
    # Get favorites
    response = client.get("/api/library/favorites", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["is_favorite"] == True


def test_remove_book_from_library(client: TestClient):
    book_id = create_admin_and_book(client)
    headers = create_user_and_login(client)
    
    # Add book to library
    client.post(f"/api/library/{book_id}", headers=headers)
    
    # Remove from library
    response = client.delete(f"/api/library/{book_id}", headers=headers)
    assert response.status_code == 204
    
    # Verify it's removed
    response = client.get("/api/library", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["items"] == []
    assert data["total"] == 0
