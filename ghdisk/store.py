"""Magazyn chunków: adresowanie po SHA-256 + kompresja + deduplikacja."""

import hashlib

from . import codec as _codec
from .chunker import DEFAULT_CHUNK_SIZE, split


class QuotaExceeded(OSError):
    """Realny limit GitHuba zostałby przekroczony."""


class ChunkStore:
    def __init__(self, index, backend, chunk_size: int = DEFAULT_CHUNK_SIZE,
                 codec: str = "zstd", real_quota: int | None = None):
        self.index = index
        self.backend = backend
        self.chunk_size = chunk_size
        self.codec = codec
        self.real_quota = real_quota

    # ------------------------------------------------------------------ zapis
    def ensure_chunk(self, data: bytes) -> str:
        """Zapisuje chunk jeśli go nie ma; zwraca SHA-256. Nie rusza refcount."""
        sha = hashlib.sha256(data).hexdigest()
        if self.index.chunk_exists(sha):
            return sha
        blob = _codec.compress(data, self.codec)
        if self.real_quota is not None:
            if self.index.used_bytes() + len(blob) > self.real_quota:
                raise QuotaExceeded(
                    f"Przekroczono realny limit {self.real_quota} B "
                    f"(GitHub). Zwolnij miejsce lub podnieś --real-quota."
                )
        self.backend.put(sha, blob)
        self.index.chunk_register(sha, len(data), len(blob), self.codec)
        return sha

    def put_bytes(self, data: bytes) -> list[str]:
        """Dzieli dane na chunki i zwraca listę SHA (bez refcountów).

        Limit sprawdzany jest narastająco w obrębie jednego wywołania, bo
        `index.used_bytes()` liczy tylko chunki z refcount>0 — a nowo zapisane
        chunki mają refcount 0 aż do `set_chunks()`.
        """
        shas: list[str] = []
        added = 0
        for chunk in split(data, self.chunk_size):
            sha = hashlib.sha256(chunk).hexdigest()
            known = self.index.chunk_exists(sha)
            shas.append(self.ensure_chunk(chunk))
            if not known and self.real_quota is not None:
                info = self.index.chunk_info(sha)
                added += int(info["stored_size"]) if info else 0
                if self.index.used_bytes() + added > self.real_quota:
                    raise QuotaExceeded(
                        f"Przekroczono realny limit {self.real_quota} B "
                        f"(GitHub). Zwolnij miejsce lub podnieś --real-quota."
                    )
        return shas

    # ------------------------------------------------------------------ odczyt
    def get_chunk(self, sha: str) -> bytes:
        return _codec.decompress(self.backend.get(sha))

    def read_all(self, shas: list[str]) -> bytes:
        return b"".join(self.get_chunk(s) for s in shas)

    def read_range(self, shas: list[str], offset: int, size: int) -> bytes:
        """Czyta wycinek pliku, dotykając tylko potrzebnych chunków."""
        if size <= 0 or not shas:
            return b""
        cs = self.chunk_size
        first = offset // cs
        last = (offset + size - 1) // cs
        out = bytearray()
        for ci in range(first, min(last, len(shas) - 1) + 1):
            data = self.get_chunk(shas[ci])
            start = ci * cs
            lo = max(offset, start) - start
            hi = min(offset + size, start + len(data)) - start
            if hi > lo:
                out += data[lo:hi]
        return bytes(out)

    # --------------------------------------------------------------------- GC
    def gc(self) -> int:
        """Usuwa chunki bez referencji. Zwraca liczbę usuniętych."""
        removed = 0
        for sha in self.index.orphans():
            try:
                self.backend.delete(sha)
            except KeyError:
                pass
            self.index.drop_chunk(sha)
            removed += 1
        self.backend.flush()
        return removed

    def flush(self) -> int:
        return self.backend.flush()
