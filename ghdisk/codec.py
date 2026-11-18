"""Kompresja chunków: zstd (jeśli dostępny) albo zlib.

Każdy zapisany blob ma 1-bajtowy nagłówek identyfikujący kodek:
    b"Z" -> zstd
    b"z" -> zlib
    b"N" -> brak kompresji
"""

import zlib

try:  # pragma: no cover - zależne od środowiska
    import zstandard as _zstd
except Exception:  # pragma: no cover
    _zstd = None

TAG_ZSTD = b"Z"
TAG_ZLIB = b"z"
TAG_NONE = b"N"

ZSTD_LEVEL = 3


def available() -> list[str]:
    """Lista dostępnych kodeków."""
    codecs = ["none", "zlib"]
    if _zstd is not None:
        codecs.insert(0, "zstd")
    return codecs


def compress(data: bytes, codec: str = "zstd") -> bytes:
    """Kompresuje dane i dokleja nagłówek kodeka."""
    if codec == "none":
        return TAG_NONE + data
    if codec == "zstd":
        if _zstd is None:
            return TAG_ZLIB + zlib.compress(data, 6)
        return TAG_ZSTD + _zstd.ZstdCompressor(level=ZSTD_LEVEL).compress(data)
    if codec == "zlib":
        return TAG_ZLIB + zlib.compress(data, 6)
    raise ValueError(f"unknown codec: {codec}")


def decompress(blob: bytes) -> bytes:
    """Dekompresuje blob na podstawie nagłówka."""
    if not blob:
        return b""
    tag, body = blob[:1], blob[1:]
    if tag == TAG_ZSTD:
        if _zstd is None:
            raise RuntimeError("blob wymaga zstd, ale moduł nie jest zainstalowany")
        return _zstd.ZstdDecompressor().decompress(body)
    if tag == TAG_ZLIB:
        return zlib.decompress(body)
    if tag == TAG_NONE:
        return body
    raise ValueError(f"unknown codec tag: {tag!r}")


def codec_name(blob: bytes) -> str:
    """Nazwa kodeka użytego w blobie."""
    tag = blob[:1]
    return {TAG_ZSTD: "zstd", TAG_ZLIB: "zlib", TAG_NONE: "none"}.get(tag, "unknown")
