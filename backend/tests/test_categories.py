import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from app.models.category import Category, Tag


def test_get_tags_empty(client: TestClient):
    response = client.get("/api/tags")

    assert response.status_code == 200
    assert response.json() == []


def test_create_tag_success(client: TestClient, auth_headers):
    response = client.post(
        "/api/tags",
        json={"name": "fiction"},
        headers=auth_headers,
    )

    assert response.status_code == 201
    data = response.json()
    assert data["id"] > 0
    assert data["name"] == "fiction"


def test_create_category_normalizes_name_and_rejects_case_duplicate(client: TestClient, auth_headers):
    response = client.post(
        "/api/categories",
        json={"name": " Fiction "},
        headers=auth_headers,
    )

    assert response.status_code == 201
    assert response.json()["name"] == "Fiction"

    duplicate_response = client.post(
        "/api/categories",
        json={"name": "fiction"},
        headers=auth_headers,
    )

    assert duplicate_response.status_code == 409


def test_create_tag_normalizes_name_and_rejects_case_duplicate(client: TestClient, auth_headers):
    response = client.post(
        "/api/tags",
        json={"name": " Fiction "},
        headers=auth_headers,
    )

    assert response.status_code == 201
    assert response.json()["name"] == "fiction"

    duplicate_response = client.post(
        "/api/tags",
        json={"name": "FICTION"},
        headers=auth_headers,
    )

    assert duplicate_response.status_code == 409


def test_create_tag_unauthorized(client: TestClient):
    response = client.post("/api/tags", json={"name": "fiction"})

    assert response.status_code == 401


def test_create_duplicate_tag(client: TestClient, auth_headers):
    first_response = client.post(
        "/api/tags",
        json={"name": "fiction"},
        headers=auth_headers,
    )
    assert first_response.status_code == 201

    duplicate_response = client.post(
        "/api/tags",
        json={"name": "fiction"},
        headers=auth_headers,
    )

    assert duplicate_response.status_code == 409


def test_get_tags_includes_book_created_tags(client: TestClient, auth_headers):
    create_book_response = client.post(
        "/api/books",
        json={
            "title": "Tagged Book",
            "author": "Test Author",
            "tags": ["fiction", "classic"],
        },
        headers=auth_headers,
    )
    assert create_book_response.status_code == 201

    response = client.get("/api/tags")

    assert response.status_code == 200
    tag_names = {tag["name"] for tag in response.json()}
    assert tag_names == {"fiction", "classic"}


def test_get_category_books_supports_pagination(client: TestClient, auth_headers):
    category_response = client.post(
        "/api/categories",
        json={"name": "Paged", "description": "Paged category"},
        headers=auth_headers,
    )
    assert category_response.status_code == 201
    category_id = category_response.json()["id"]

    for index in range(3):
        response = client.post(
            "/api/books",
            json={
                "title": f"Paged Book {index}",
                "author": "Test Author",
                "category_id": category_id,
            },
            headers=auth_headers,
        )
        assert response.status_code == 201

    response = client.get(f"/api/categories/{category_id}/books?skip=1&limit=1")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["title"] == "Paged Book 1"


def test_get_category_books_rejects_missing_category(client: TestClient):
    response = client.get("/api/categories/999/books")

    assert response.status_code == 404
    assert response.json()["detail"] == "Category not found"


def test_get_category_books_rejects_limit_above_max(client: TestClient, auth_headers):
    category_response = client.post(
        "/api/categories",
        json={"name": "Limit Check"},
        headers=auth_headers,
    )
    assert category_response.status_code == 201
    category_id = category_response.json()["id"]

    response = client.get(f"/api/categories/{category_id}/books?limit=101")

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_category_name_unique_case_insensitive_at_db_level(db_session):
    db_session.add(Category(name="Fiction"))
    await db_session.commit()

    db_session.add(Category(name="fiction"))
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_tag_name_unique_case_insensitive_at_db_level(db_session):
    db_session.add(Tag(name="classic"))
    await db_session.commit()

    db_session.add(Tag(name="Classic"))
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()
