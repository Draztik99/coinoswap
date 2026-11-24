"""Offline media derivatives from authenticated official CoinoSwap PNGs.

Never alter source PNG pixels or rewrite production assets. Instagram JPEG
is a byte-for-byte separate derivative with its own SHA-256 and no upload.
"""
from __future__ import annotations

import hashlib
import hmac
import io
from dataclasses import dataclass

from PIL import Image, UnidentifiedImageError

SOURCE_DIMS = (1536, 1024)
MAX_X_PNG = 5_000_000
MAX_FB_PNG = 10_000_000
MAX_IG_JPEG = 8_000_000
IG_MIN_RATIO = 0.80
IG_MAX_RATIO = 1.91


class MediaRejected(ValueError):
    pass


@dataclass(frozen=True)
class PreparedMedia:
    png_bytes: bytes
    png_sha256: str
    jpeg_bytes: bytes
    jpeg_sha256: str
    width: int
    height: int


def prepare_media(source_png: bytes, expected_sha256: str) -> PreparedMedia:
    if not isinstance(source_png, bytes) or not isinstance(expected_sha256, str):
        raise MediaRejected("source PNG bytes and SHA-256 are required")
    if not hmac.compare_digest(
        hashlib.sha256(source_png).hexdigest(), expected_sha256.lower()
    ):
        raise MediaRejected("official PNG digest does not match audit")
    if len(source_png) > MAX_X_PNG:
        raise MediaRejected("official PNG too large for X 5 MB image limit")
    if len(source_png) > MAX_FB_PNG:
        raise MediaRejected("official PNG too large for Facebook 10 MB image limit")
    try:
        with Image.open(io.BytesIO(source_png)) as decoded:
            if decoded.format != "PNG" or decoded.size != SOURCE_DIMS:
                raise MediaRejected("official image format/dimensions do not match")
            decoded.verify()   # validates PNG CRC and decode boundaries
        with Image.open(io.BytesIO(source_png)) as decoded:
            original = decoded.convert("RGB")
            original.load()
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError) as exc:
        if isinstance(exc, MediaRejected):
            raise
        raise MediaRejected("official PNG cannot be decoded intact") from exc
    width, height = original.size
    if not IG_MIN_RATIO <= width / height <= IG_MAX_RATIO:
        raise MediaRejected("Instagram aspect ratio incompatible")
    out = io.BytesIO()
    original.save(out, format="JPEG", quality=95, subsampling=0, optimize=True)
    jpeg = out.getvalue()
    if not 0 < len(jpeg) <= MAX_IG_JPEG:
        raise MediaRejected("Instagram JPEG size invalid")
    try:
        with Image.open(io.BytesIO(jpeg)) as check:
            if check.format != "JPEG" or check.size != SOURCE_DIMS:
                raise MediaRejected("Instagram JPEG decode/size mismatch")
            if check.getexif():
                raise MediaRejected("unexpected JPEG EXIF")
            check.verify()
    except (UnidentifiedImageError, OSError, SyntaxError) as exc:
        raise MediaRejected("generated JPEG invalid") from exc
    return PreparedMedia(
        png_bytes=source_png,
        png_sha256=hashlib.sha256(source_png).hexdigest(),
        jpeg_bytes=jpeg,
        jpeg_sha256=hashlib.sha256(jpeg).hexdigest(),
        width=width,
        height=height,
    )
