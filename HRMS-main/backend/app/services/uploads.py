from fastapi import HTTPException, UploadFile, status


async def read_upload_limited(upload: UploadFile, max_bytes: int) -> bytes:
    """Read at most the configured size plus one byte from an uploaded file."""
    if upload.size is not None and upload.size > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"File too large (max {max_bytes // (1024 * 1024)} MB)",
        )

    content = bytearray()
    while True:
        remaining = max_bytes - len(content)
        chunk = await upload.read(min(64 * 1024, remaining + 1))
        if not chunk:
            return bytes(content)
        if len(chunk) > remaining:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail=f"File too large (max {max_bytes // (1024 * 1024)} MB)",
            )
        content.extend(chunk)
