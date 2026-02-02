# =========================================
# FILE: app/services/storage.py
# (FULL FILE - streaming save + size limit)
# =========================================
import os
import uuid
from typing import Tuple

from fastapi import UploadFile, HTTPException

from app.core.config import settings

UPLOAD_DIR = "uploads"


def ensure_upload_dir() -> None:
    os.makedirs(UPLOAD_DIR, exist_ok=True)


def _guess_ext(filename: str | None) -> str:
    if not filename or "." not in filename:
        return ""
    return "." + filename.rsplit(".", 1)[-1].lower()


def save_upload_streaming(file: UploadFile) -> Tuple[str, int]:
    """
    Stream file to disk safely and enforce a max size.
    Returns (stored_path, bytes_written).
    """
    ensure_upload_dir()

    ext = _guess_ext(file.filename)
    safe_name = f"{uuid.uuid4()}{ext}"
    path = os.path.join(UPLOAD_DIR, safe_name)

    max_bytes = settings.MAX_UPLOAD_MB * 1024 * 1024
    bytes_written = 0

    try:
        with open(path, "wb") as out:
            while True:
                chunk = file.file.read(1024 * 1024)  # 1MB chunks
                if not chunk:
                    break
                bytes_written += len(chunk)
                if bytes_written > max_bytes:
                    raise HTTPException(
                        status_code=413,
                        detail=f"File too large. Max is {settings.MAX_UPLOAD_MB}MB.",
                    )
                out.write(chunk)
    except HTTPException:
        if os.path.exists(path):
            try:
                os.remove(path)
            except Exception:
                pass
        raise
    except Exception as e:
        if os.path.exists(path):
            try:
                os.remove(path)
            except Exception:
                pass
        raise HTTPException(status_code=500, detail=f"Upload failed: {e}")

    return path, bytes_written

# import os
# import uuid
# import shutil
# from typing import Tuple

# from fastapi import UploadFile, HTTPException

# from app.core.config import settings

# UPLOAD_DIR = "uploads"


# def ensure_upload_dir() -> None:
#     os.makedirs(UPLOAD_DIR, exist_ok=True)


# def _guess_ext(filename: str | None) -> str:
#     if not filename or "." not in filename:
#         return ""
#     return "." + filename.rsplit(".", 1)[-1].lower()


# def save_upload_streaming(file: UploadFile) -> Tuple[str, int]:
#     """
#     Stream file to disk safely and enforce a max size.
#     Returns (stored_path, bytes_written).
#     """
#     ensure_upload_dir()

#     ext = _guess_ext(file.filename)
#     safe_name = f"{uuid.uuid4()}{ext}"
#     path = os.path.join(UPLOAD_DIR, safe_name)

#     max_bytes = settings.MAX_UPLOAD_MB * 1024 * 1024
#     bytes_written = 0

#     try:
#         with open(path, "wb") as out:
#             while True:
#                 chunk = file.file.read(1024 * 1024)  # 1MB chunks
#                 if not chunk:
#                     break
#                 bytes_written += len(chunk)
#                 if bytes_written > max_bytes:
#                     raise HTTPException(
#                         status_code=413,
#                         detail=f"File too large. Max is {settings.MAX_UPLOAD_MB}MB.",
#                     )
#                 out.write(chunk)
#     except HTTPException:
#         # clean up partial file
#         if os.path.exists(path):
#             try:
#                 os.remove(path)
#             except Exception:
#                 pass
#         raise
#     except Exception as e:
#         if os.path.exists(path):
#             try:
#                 os.remove(path)
#             except Exception:
#                 pass
#         raise HTTPException(status_code=500, detail=f"Upload failed: {e}")

#     return path, bytes_written

