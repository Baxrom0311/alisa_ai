import httpx
import pytest

from app.storage.local import LocalStorage
from app.storage.supabase import SupabaseStorage
from app.config import settings
from app.services.storage_service import get_storage_backend
from app.utils.streaming import _content_disposition, parse_range_header


async def collect_bytes(chunks):
    body = bytearray()
    async for chunk in chunks:
        body.extend(chunk)
    return bytes(body)


@pytest.mark.asyncio
async def test_local_storage_get_size(tmp_path):
    storage = LocalStorage(base_path=str(tmp_path))

    await storage.save(b"stored bytes", "books/test.pdf")

    assert await storage.get_size("books/test.pdf") == len(b"stored bytes")
    assert await storage.get_size("books/missing.pdf") is None


@pytest.mark.asyncio
async def test_local_storage_save_stream(tmp_path):
    storage = LocalStorage(base_path=str(tmp_path))

    async def chunks():
        yield b"streamed "
        yield b"bytes"

    await storage.save_stream(chunks(), "books/streamed.pdf", content_type="application/pdf")

    stored = bytearray()
    async for chunk in storage.get("books/streamed.pdf"):
        stored.extend(chunk)
    assert bytes(stored) == b"streamed bytes"


@pytest.mark.asyncio
async def test_local_storage_save_stream_is_atomic_on_failure(tmp_path):
    storage = LocalStorage(base_path=str(tmp_path))
    await storage.save(b"original", "books/replace.pdf")

    async def failing_chunks():
        yield b"partial"
        raise RuntimeError("upload interrupted")

    with pytest.raises(RuntimeError, match="upload interrupted"):
        await storage.save_stream(failing_chunks(), "books/replace.pdf")

    stored = await collect_bytes(storage.get("books/replace.pdf"))
    leftovers = [
        path
        for path in (tmp_path / "books").iterdir()
        if path.name.startswith(".replace.pdf.") and path.name.endswith(".tmp")
    ]

    assert stored == b"original"
    assert leftovers == []


@pytest.mark.asyncio
async def test_local_storage_get_range_reads_only_requested_slice(tmp_path):
    storage = LocalStorage(base_path=str(tmp_path))
    body = b"0123456789abcdef" * 10_000
    await storage.save(body, "audio/test.mp3")

    start = 65_000
    end = 66_111
    ranged_body = await collect_bytes(storage.get_range("audio/test.mp3", start, end))

    assert ranged_body == body[start:end + 1]


@pytest.mark.asyncio
async def test_local_storage_rejects_paths_outside_base(tmp_path):
    storage = LocalStorage(base_path=str(tmp_path / "uploads"))

    with pytest.raises(ValueError, match="escapes base directory"):
        await storage.save(b"secret", "../outside.txt")

    assert not (tmp_path / "outside.txt").exists()


@pytest.mark.asyncio
async def test_local_storage_rejects_absolute_paths(tmp_path):
    storage = LocalStorage(base_path=str(tmp_path / "uploads"))

    with pytest.raises(ValueError, match="must be relative"):
        await storage.save(b"secret", str(tmp_path / "outside.txt"))


@pytest.mark.asyncio
async def test_supabase_storage_get_size_uses_object_metadata(monkeypatch):
    monkeypatch.setattr(settings, "SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setattr(settings, "SUPABASE_KEY", "test-key")
    captured = {}

    class StubAsyncClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            return None

        async def head(self, url, headers):
            captured["url"] = url
            captured["headers"] = headers
            return httpx.Response(200, headers={"content-length": "42"})

    monkeypatch.setattr(
        "app.storage.supabase.httpx.AsyncClient",
        lambda: StubAsyncClient()
    )

    storage = SupabaseStorage()
    storage.base_url = "https://example.supabase.co/storage/v1/object/kitobxon"
    storage.headers = {"Authorization": "Bearer test-key"}

    assert await storage.get_size("books/test.pdf") == 42
    assert captured["url"].endswith("/books/test.pdf")
    assert captured["headers"] == {"Authorization": "Bearer test-key"}


@pytest.mark.asyncio
async def test_supabase_storage_encodes_object_paths(monkeypatch):
    monkeypatch.setattr(settings, "SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setattr(settings, "SUPABASE_KEY", "test-key")
    captured = {}

    class StubAsyncClient:
        async def head(self, url, headers):
            captured["url"] = url
            return httpx.Response(200, headers={"content-length": "42"})

    monkeypatch.setattr(
        "app.storage.supabase.httpx.AsyncClient",
        lambda: StubAsyncClient()
    )

    storage = SupabaseStorage()

    assert await storage.get_size("books/test file #1.pdf") == 42
    assert captured["url"].endswith("/books/test%20file%20%231.pdf")


@pytest.mark.parametrize(
    "path",
    [
        "",
        ".",
        "/books/test.pdf",
        "../secret.txt",
        "books/../secret.txt",
        "books\\secret.txt",
        "books//secret.txt",
    ],
)
@pytest.mark.asyncio
async def test_supabase_storage_rejects_unsafe_paths(monkeypatch, path):
    monkeypatch.setattr(settings, "SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setattr(settings, "SUPABASE_KEY", "test-key")
    storage = SupabaseStorage()

    with pytest.raises(ValueError, match="Storage path"):
        await storage.get_size(path)


@pytest.mark.asyncio
async def test_supabase_storage_get_size_returns_none_without_metadata(monkeypatch):
    monkeypatch.setattr(settings, "SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setattr(settings, "SUPABASE_KEY", "test-key")

    class StubAsyncClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            return None

        async def head(self, url, headers):
            return httpx.Response(404)

    monkeypatch.setattr(
        "app.storage.supabase.httpx.AsyncClient",
        lambda: StubAsyncClient()
    )

    storage = SupabaseStorage()

    assert await storage.get_size("books/missing.pdf") is None


@pytest.mark.asyncio
async def test_supabase_storage_reuses_client_and_closes(monkeypatch):
    monkeypatch.setattr(settings, "SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setattr(settings, "SUPABASE_KEY", "test-key")
    created = []

    class StubAsyncClient:
        is_closed = False

        def __init__(self):
            created.append(self)

        async def head(self, url, headers):
            return httpx.Response(200, headers={"content-length": "42"})

        async def aclose(self):
            self.is_closed = True

    monkeypatch.setattr(
        "app.storage.supabase.httpx.AsyncClient",
        StubAsyncClient,
    )

    storage = SupabaseStorage()

    assert await storage.get_size("books/one.pdf") == 42
    assert await storage.get_size("books/two.pdf") == 42
    assert len(created) == 1

    await storage.close()
    assert created[0].is_closed is True


@pytest.mark.asyncio
async def test_supabase_storage_get_range_sends_range_header(monkeypatch):
    monkeypatch.setattr(settings, "SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setattr(settings, "SUPABASE_KEY", "test-key")
    captured = {}

    class StubStreamResponse:
        def raise_for_status(self):
            return None

        async def aiter_bytes(self, chunk_size):
            captured["chunk_size"] = chunk_size
            yield b"abc"
            yield b"def"

    class StubStream:
        async def __aenter__(self):
            return StubStreamResponse()

        async def __aexit__(self, exc_type, exc, traceback):
            return None

    class StubAsyncClient:
        def stream(self, method, url, headers):
            captured["method"] = method
            captured["url"] = url
            captured["headers"] = headers
            return StubStream()

    monkeypatch.setattr(
        "app.storage.supabase.httpx.AsyncClient",
        lambda: StubAsyncClient()
    )

    storage = SupabaseStorage()
    storage.base_url = "https://example.supabase.co/storage/v1/object/kitobxon"
    storage.headers = {"Authorization": "Bearer test-key"}

    body = await collect_bytes(storage.get_range("audio/test.mp3", 10, 20))

    assert body == b"abcdef"
    assert captured["method"] == "GET"
    assert captured["url"].endswith("/audio/test.mp3")
    assert captured["headers"]["Range"] == "bytes=10-20"
    assert captured["chunk_size"] == 64 * 1024


def test_supabase_storage_requires_url_and_key(monkeypatch):
    monkeypatch.setattr(settings, "SUPABASE_URL", "")
    monkeypatch.setattr(settings, "SUPABASE_KEY", "")

    with pytest.raises(ValueError, match="SUPABASE_URL and SUPABASE_KEY"):
        SupabaseStorage()


@pytest.mark.asyncio
async def test_supabase_storage_save_stream_sets_upload_headers(monkeypatch):
    monkeypatch.setattr(settings, "SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setattr(settings, "SUPABASE_KEY", "test-key")
    captured = {}

    class StubAsyncClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            return None

        async def post(self, url, content, headers):
            body = bytearray()
            async for chunk in content:
                body.extend(chunk)
            captured["url"] = url
            captured["headers"] = headers
            captured["body"] = bytes(body)
            return httpx.Response(200, request=httpx.Request("POST", url))

    monkeypatch.setattr(
        "app.storage.supabase.httpx.AsyncClient",
        lambda: StubAsyncClient()
    )

    storage = SupabaseStorage()

    async def chunks():
        yield b"pdf"

    stored_path = await storage.save_stream(chunks(), "books/test.pdf", content_type="application/pdf")

    assert stored_path == "books/test.pdf"
    assert captured["url"].endswith("/books/test.pdf")
    assert captured["headers"]["Content-Type"] == "application/pdf"
    assert captured["headers"]["x-upsert"] == "true"
    assert captured["body"] == b"pdf"


@pytest.mark.asyncio
async def test_supabase_storage_delete_ignores_missing_objects(monkeypatch):
    monkeypatch.setattr(settings, "SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setattr(settings, "SUPABASE_KEY", "test-key")
    captured = {}

    class StubAsyncClient:
        async def delete(self, url, headers):
            captured["url"] = url
            captured["headers"] = headers
            return httpx.Response(404, request=httpx.Request("DELETE", url))

    monkeypatch.setattr(
        "app.storage.supabase.httpx.AsyncClient",
        lambda: StubAsyncClient()
    )

    storage = SupabaseStorage()

    await storage.delete("books/missing.pdf")

    assert captured["url"].endswith("/books/missing.pdf")
    assert captured["headers"]["Authorization"] == "Bearer test-key"


def test_storage_factory_rejects_unknown_backend(monkeypatch):
    monkeypatch.setattr(settings, "STORAGE_BACKEND", "unknown")

    with pytest.raises(ValueError, match="Unsupported storage backend"):
        get_storage_backend()


def test_storage_factory_is_case_insensitive(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "STORAGE_BACKEND", "LOCAL")
    monkeypatch.setattr(settings, "LOCAL_STORAGE_PATH", str(tmp_path / "uploads"))

    storage = get_storage_backend()

    assert isinstance(storage, LocalStorage)


def test_parse_range_header_supports_suffix_ranges():
    assert parse_range_header("bytes=-4", 10) == (6, 9)
    assert parse_range_header("bytes=-20", 10) == (0, 9)


def test_parse_range_header_clamps_open_ended_ranges_to_file_size():
    assert parse_range_header("bytes=2-999", 10) == (2, 9)
    assert parse_range_header("bytes=0-10", 10) == (0, 9)


@pytest.mark.parametrize(
    ("filename", "expected_ascii", "expected_encoded"),
    [
        ('My "Quoted" Book\n', "My Quoted Book", "My%20Quoted%20Book"),
        ("Kitobxon — урок", "Kitobxon", "Kitobxon%20%E2%80%94%20%D1%83%D1%80%D0%BE%D0%BA"),
        ("", "download", "download"),
    ],
)
def test_content_disposition_sanitizes_filename(filename, expected_ascii, expected_encoded):
    header = _content_disposition(filename)

    assert "\r" not in header
    assert "\n" not in header
    assert header.count("filename=") == 1
    assert header.count("filename*=") == 1
    assert header.startswith(f'inline; filename="{expected_ascii}"')
    assert header.endswith(f"filename*=UTF-8''{expected_encoded}")
