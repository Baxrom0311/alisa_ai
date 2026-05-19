import re
import unicodedata
from typing import Optional, Tuple
from urllib.parse import quote

from fastapi import Request, HTTPException, status
from fastapi.responses import Response, StreamingResponse


_HEADER_UNSAFE_RE = re.compile(r'[\x00-\x1f\x7f"]+')
_ASCII_FILENAME_UNSAFE_RE = re.compile(r"[^A-Za-z0-9._ -]+")


def _range_error(file_size: int, detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_416_RANGE_NOT_SATISFIABLE,
        detail=detail,
        headers={
            "Accept-Ranges": "bytes",
            "Content-Range": f"bytes */{file_size}",
        },
    )


def _content_disposition(filename: str) -> str:
    cleaned = _HEADER_UNSAFE_RE.sub("", filename).strip()
    if not cleaned:
        cleaned = "download"

    ascii_name = (
        unicodedata.normalize("NFKD", cleaned)
        .encode("ascii", "ignore")
        .decode("ascii")
    )
    ascii_name = _ASCII_FILENAME_UNSAFE_RE.sub("_", ascii_name).strip(" ._")
    if not ascii_name:
        ascii_name = "download"

    encoded_name = quote(cleaned, safe="")
    return f'inline; filename="{ascii_name}"; filename*=UTF-8\'\'{encoded_name}'


def parse_range_header(range_header: str, file_size: int) -> Tuple[int, int]:
    """Parse HTTP Range header and return start, end positions."""
    if not range_header.startswith("bytes="):
        raise _range_error(file_size, "Invalid range header")
    
    range_spec = range_header[6:]  # Remove "bytes="
    
    if "," in range_spec:
        # Multiple ranges not supported
        raise _range_error(file_size, "Multiple ranges not supported")
    
    if "-" not in range_spec:
        raise _range_error(file_size, "Invalid range format")
    
    start_str, end_str = range_spec.split("-", 1)
    
    try:
        if start_str:
            start = int(start_str)
            if start < 0 or start >= file_size:
                raise _range_error(file_size, "Range start out of bounds")
        else:
            suffix_length = int(end_str)
            if suffix_length <= 0:
                raise _range_error(file_size, "Range suffix out of bounds")
            start = max(file_size - suffix_length, 0)
            end = file_size - 1
            return start, end
        
        if end_str:
            end = int(end_str)
            if end < start:
                raise _range_error(file_size, "Range end out of bounds")
            end = min(end, file_size - 1)
        else:
            end = file_size - 1
            
    except ValueError:
        raise _range_error(file_size, "Invalid range values")
    
    return start, end


async def create_range_response(
    file_path: str,
    storage,
    media_type: str,
    request: Request,
    filename: Optional[str] = None
) -> StreamingResponse:
    """Create a streaming response with proper range support."""
    
    # Get file size
    if not await storage.exists(file_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found"
        )
    
    file_size = await storage.get_size(file_path)
    if file_size is None:
        async def generate():
            async for chunk in storage.get(file_path):
                yield chunk

        headers = {"Accept-Ranges": "bytes"}
        if filename:
            headers["Content-Disposition"] = _content_disposition(filename)

        if request.method == "HEAD":
            return Response(
                status_code=206 if request.headers.get("range") else 200,
                headers=headers,
                media_type=media_type,
            )

        return StreamingResponse(
            generate(),
            media_type=media_type,
            headers=headers
        )
    
    range_header = request.headers.get("range")
    
    if not range_header:
        # No range request, return full file
        async def generate():
            async for chunk in storage.get(file_path):
                yield chunk
        
        headers = {
            "Accept-Ranges": "bytes",
            "Content-Length": str(file_size)
        }
        if filename:
            headers["Content-Disposition"] = _content_disposition(filename)

        if request.method == "HEAD":
            return Response(
                status_code=200,
                headers=headers,
                media_type=media_type,
            )
        
        return StreamingResponse(
            generate(),
            media_type=media_type,
            headers=headers
        )
    
    # Parse range request
    start, end = parse_range_header(range_header, file_size)
    content_length = end - start + 1
    
    range_reader = getattr(storage, "get_range", None)

    async def generate_range_from_get_range():
        async for chunk in range_reader(file_path, start, end):
            yield chunk

    async def generate_range_from_full_read():
        bytes_read = 0
        target_bytes = content_length

        async for chunk in storage.get(file_path):
            if bytes_read + len(chunk) <= start:
                # Skip this chunk entirely
                bytes_read += len(chunk)
                continue
            
            # Determine what part of this chunk we need
            chunk_start = max(0, start - bytes_read)
            chunk_end = min(len(chunk), start + target_bytes - bytes_read)
            
            if chunk_start < chunk_end:
                yield chunk[chunk_start:chunk_end]
                target_bytes -= (chunk_end - chunk_start)
                
                if target_bytes <= 0:
                    break
            
            bytes_read += len(chunk)

    generate_range = (
        generate_range_from_get_range
        if callable(range_reader)
        else generate_range_from_full_read
    )
    
    headers = {
        "Accept-Ranges": "bytes",
        "Content-Range": f"bytes {start}-{end}/{file_size}",
        "Content-Length": str(content_length)
    }
    if filename:
        headers["Content-Disposition"] = _content_disposition(filename)

    if request.method == "HEAD":
        return Response(
            status_code=206,
            headers=headers,
            media_type=media_type,
        )
    
    return StreamingResponse(
        generate_range(),
        status_code=206,  # Partial Content
        media_type=media_type,
        headers=headers
    )
