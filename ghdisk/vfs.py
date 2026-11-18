"""Warstwa VFS — wspólna logika dla FUSE i CLI."""

import posixpath
import time

from .store import ChunkStore


class VFSError(OSError):
    pass


def _norm(path: str) -> str:
    """Normalizuje ścieżkę do postaci '/a/b' (bez końcowego ukośnika)."""
    p = posixpath.normpath("/" + path.strip("/"))
    return "/" if p == "." else p


class VFS:
    def __init__(self, index, store: ChunkStore):
        self.index = index
        self.store = store

    # ------------------------------------------------------------------ ścieżki
    def _parent(self, path: str) -> str:
        return posixpath.dirname(path) or "/"

    def _ensure_parents(self, path: str) -> None:
        parent = self._parent(path)
        if parent == "/":
            return
        parts = parent.strip("/").split("/")
        cur = ""
        for part in parts:
            cur += "/" + part
            if not self.index.exists(cur):
                self.index.mkdir(cur)

    # ------------------------------------------------------------------ odczyt
    def stat(self, path: str):
        row = self.index.get(_norm(path))
        if row is None:
            raise FileNotFoundError(path)
        return row

    def listdir(self, path: str) -> list[str]:
        p = _norm(path)
        row = self.index.get(p)
        if row is None:
            raise FileNotFoundError(path)
        if row["kind"] != "dir":
            raise NotADirectoryError(path)
        return self.index.listdir(p)

    def read_file(self, path: str) -> bytes:
        p = _norm(path)
        row = self.index.get(p)
        if row is None:
            raise FileNotFoundError(path)
        if row["kind"] != "file":
            raise IsADirectoryError(path)
        return self.store.read_all(self.index.chunks(p))

    def read_range(self, path: str, offset: int, size: int) -> bytes:
        p = _norm(path)
        row = self.index.get(p)
        if row is None:
            raise FileNotFoundError(path)
        return self.store.read_range(self.index.chunks(p), offset, size)

    # ------------------------------------------------------------------ zapis
    def write_file(self, path: str, data: bytes) -> dict:
        """Zapisuje cały plik. Zwraca statystyki (dedup/kompresja)."""
        p = _norm(path)
        self._ensure_parents(p)
        before = self.index.used_bytes()
        shas = self.store.put_bytes(data)
        orphans = self.index.set_chunks(p, shas)
        if not self.index.exists(p):
            now = time.time()
            self.index.db.execute(
                "INSERT INTO inodes(path,kind,size,mode,mtime,ctime,atime)"
                " VALUES(?,'file',?,420,?,?,?)",
                (p, len(data), now, now, now),
            )
            self.index.db.commit()
        self.index.set_size(p, len(data))
        self.index.touch(p)
        self.store.flush()
        after = self.index.used_bytes()
        return {
            "path": p,
            "size": len(data),
            "chunks": len(shas),
            "unique_chunks": len(set(shas)),
            "stored_delta": after - before,
            "orphans": len(orphans),
        }

    def mkdir(self, path: str, mode: int = 0o755) -> None:
        p = _norm(path)
        if self.index.exists(p):
            raise FileExistsError(path)
        self._ensure_parents(p)
        self.index.mkdir(p, mode)

    def rmdir(self, path: str) -> None:
        p = _norm(path)
        if self.index.listdir(p):
            raise OSError(39, "Directory not empty", path)
        self.index.rmdir(p)

    def unlink(self, path: str) -> None:
        p = _norm(path)
        row = self.index.get(p)
        if row is None:
            raise FileNotFoundError(path)
        if row["kind"] != "file":
            raise IsADirectoryError(path)
        self.index.unlink(p)

    def rename(self, old: str, new: str) -> None:
        o, n = _norm(old), _norm(new)
        if not self.index.exists(o):
            raise FileNotFoundError(old)
        self._ensure_parents(n)
        self.index.rename(o, n)

    def chmod(self, path: str, mode: int) -> None:
        self.index.chmod(_norm(path), mode)

    def utime(self, path: str, mtime: float) -> None:
        self.index.touch(_norm(path), mtime)

    # ------------------------------------------------------------------- staty
    def df(self) -> dict:
        st = self.index.stats()
        return {
            **st,
            "ratio": (st["raw_bytes"] / st["used_bytes"]) if st["used_bytes"] else 1.0,
        }
