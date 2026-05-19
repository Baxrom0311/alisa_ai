import re
from collections.abc import Awaitable, Callable

from fastapi import HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response

from ..config import settings
from ..utils.file_validation import COVER_MAX_SIZE, ensure_content_length_allowed


_UPLOAD_LIMIT_ROUTES = {
    "cover": (COVER_MAX_SIZE, "Cover image"),
    "file": (lambda: settings.MAX_BOOK_FILE_SIZE, "Book"),
    "audio": (lambda: settings.MAX_AUDIO_FILE_SIZE, "Audio"),
}
_UPLOAD_PATH_RE = re.compile(r"^/api/books/\d+/(cover|file|audio)$")


def _resolve_limit(value: int | Callable[[], int]) -> int:
    return value() if callable(value) else value


class UploadContentLengthLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        if request.method != "POST":
            return await call_next(request)

        match = _UPLOAD_PATH_RE.fullmatch(request.url.path)
        if match is None:
            return await call_next(request)

        max_size, file_type = _UPLOAD_LIMIT_ROUTES[match.group(1)]
        try:
            ensure_content_length_allowed(request, _resolve_limit(max_size), file_type)
        except HTTPException as exc:
            return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

        return await call_next(request)
