"""Dzielenie plików na fragmenty (chunki) o stałym rozmiarze."""

from typing import Iterable, Iterator

DEFAULT_CHUNK_SIZE = 4 * 1024 * 1024  # 4 MiB


def split(data: bytes, size: int = DEFAULT_CHUNK_SIZE) -> Iterator[bytes]:
    """Dzieli bajty na fragmenty o rozmiarze `size` (ostatni może być krótszy)."""
    if size <= 0:
        raise ValueError("chunk size must be > 0")
    for off in range(0, len(data), size):
        yield data[off : off + size]


def join(chunks: Iterable[bytes]) -> bytes:
    """Skleja fragmenty w całość."""
    return b"".join(chunks)


def chunk_count(size: int, chunk_size: int = DEFAULT_CHUNK_SIZE) -> int:
    """Ile chunków zajmie plik o danym rozmiarze."""
    if size <= 0:
        return 0
    return (size + chunk_size - 1) // chunk_size
