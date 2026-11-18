"""Indeks metadanych: SQLite (inody, chunki, referencje).

Indeks trzyma CAŁĄ strukturę katalogów i mapowanie plik -> lista chunków.
Dzięki temu montowanie jest natychmiastowe i nie wymaga listowania repo.
"""

import os
import sqlite3
import threading
import time

SCHEMA = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS inodes (
    path  TEXT PRIMARY KEY,
    kind  TEXT NOT NULL,              -- 'file' | 'dir'
    size  INTEGER NOT NULL DEFAULT 0,
    mode  INTEGER NOT NULL DEFAULT 420,
    mtime REAL NOT NULL,
    ctime REAL NOT NULL,
    atime REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS chunks (
    sha         TEXT PRIMARY KEY,
    raw_size    INTEGER NOT NULL,
    stored_size INTEGER NOT NULL,
    codec       TEXT NOT NULL,
    refcount    INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS file_chunks (
    path TEXT NOT NULL,
    idx  INTEGER NOT NULL,
    sha  TEXT NOT NULL,
    PRIMARY KEY (path, idx)
);

CREATE INDEX IF NOT EXISTS idx_file_chunks_sha ON file_chunks(sha);
"""


class Index:
    """Warstwa metadanych. Bezpieczna wątkami (FUSE woła z wielu wątków)."""

    def __init__(self, path: str):
        self.path = path
        os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
        self._lock = threading.RLock()
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        with self._lock:
            self.db.executescript(SCHEMA)
            self.db.commit()
        self._ensure_root()

    # ------------------------------------------------------------------ inody
    def _ensure_root(self) -> None:
        with self._lock:
            if not self.db.execute("SELECT 1 FROM inodes WHERE path='/'").fetchone():
                now = time.time()
                self.db.execute(
                    "INSERT INTO inodes(path,kind,size,mode,mtime,ctime,atime)"
                    " VALUES('/','dir',0,493,?,?,?)",
                    (now, now, now),
                )
                self.db.commit()

    def get(self, path: str):
        with self._lock:
            return self.db.execute(
                "SELECT * FROM inodes WHERE path=?", (path,)
            ).fetchone()

    def exists(self, path: str) -> bool:
        return self.get(path) is not None

    def listdir(self, path: str) -> list[str]:
        prefix = path.rstrip("/") + "/"
        with self._lock:
            rows = self.db.execute(
                "SELECT path FROM inodes WHERE path LIKE ? AND path <> ?",
                (prefix + "%", path),
            ).fetchall()
        out = []
        for r in rows:
            rest = r["path"][len(prefix) :]
            if rest and "/" not in rest:
                out.append(rest)
        return sorted(out)

    def mkdir(self, path: str, mode: int = 0o755) -> None:
        now = time.time()
        with self._lock:
            self.db.execute(
                "INSERT INTO inodes(path,kind,size,mode,mtime,ctime,atime)"
                " VALUES(?,'dir',0,?,?,?,?)",
                (path, mode, now, now, now),
            )
            self.db.commit()

    def rmdir(self, path: str) -> None:
        with self._lock:
            self.db.execute("DELETE FROM inodes WHERE path=? AND kind='dir'", (path,))
            self.db.commit()

    def unlink(self, path: str) -> list[str]:
        """Usuwa plik; zwraca listę chunków, które straciły ostatnią referencję."""
        with self._lock:
            shas = [r["sha"] for r in self.db.execute(
                "SELECT sha FROM file_chunks WHERE path=? ORDER BY idx", (path,))]
            self.db.execute("DELETE FROM file_chunks WHERE path=?", (path,))
            self.db.execute("DELETE FROM inodes WHERE path=? AND kind='file'", (path,))
            orphans = []
            for sha in shas:
                self.db.execute(
                    "UPDATE chunks SET refcount=refcount-1 WHERE sha=?", (sha,))
                row = self.db.execute(
                    "SELECT refcount FROM chunks WHERE sha=?", (sha,)).fetchone()
                if row and row["refcount"] <= 0:
                    orphans.append(sha)
            self.db.commit()
        return orphans

    def rename(self, old: str, new: str) -> None:
        with self._lock:
            self.db.execute("UPDATE inodes SET path=? WHERE path=?", (new, old))
            self.db.execute("UPDATE file_chunks SET path=? WHERE path=?", (new, old))
            self.db.commit()

    def touch(self, path: str, mtime: float | None = None) -> None:
        now = mtime if mtime is not None else time.time()
        with self._lock:
            self.db.execute("UPDATE inodes SET mtime=?, ctime=? WHERE path=?",
                            (now, now, path))
            self.db.commit()

    def chmod(self, path: str, mode: int) -> None:
        with self._lock:
            self.db.execute("UPDATE inodes SET mode=? WHERE path=?", (mode, path))
            self.db.commit()

    def set_size(self, path: str, size: int) -> None:
        with self._lock:
            self.db.execute("UPDATE inodes SET size=? WHERE path=?", (size, path))
            self.db.commit()

    # ----------------------------------------------------------------- chunki
    def chunks(self, path: str) -> list[str]:
        with self._lock:
            return [r["sha"] for r in self.db.execute(
                "SELECT sha FROM file_chunks WHERE path=? ORDER BY idx", (path,))]

    def set_chunks(self, path: str, shas: list[str]) -> list[str]:
        """Ustawia listę chunków pliku i wyrównuje refcounty.

        Zwraca listę chunków, które straciły ostatnie referencje (kandydaci do GC).
        """
        with self._lock:
            old = [r["sha"] for r in self.db.execute(
                "SELECT sha FROM file_chunks WHERE path=? ORDER BY idx", (path,))]
            self.db.execute("DELETE FROM file_chunks WHERE path=?", (path,))
            for i, sha in enumerate(shas):
                self.db.execute(
                    "INSERT INTO file_chunks(path,idx,sha) VALUES(?,?,?)",
                    (path, i, sha),
                )
                self.db.execute(
                    "UPDATE chunks SET refcount=refcount+1 WHERE sha=?", (sha,))
            orphans = []
            for sha in old:
                self.db.execute(
                    "UPDATE chunks SET refcount=refcount-1 WHERE sha=?", (sha,))
                row = self.db.execute(
                    "SELECT refcount FROM chunks WHERE sha=?", (sha,)).fetchone()
                if row and row["refcount"] <= 0:
                    orphans.append(sha)
            self.db.commit()
        return orphans

    def chunk_exists(self, sha: str) -> bool:
        with self._lock:
            return self.db.execute(
                "SELECT 1 FROM chunks WHERE sha=?", (sha,)).fetchone() is not None

    def chunk_register(self, sha: str, raw_size: int, stored_size: int,
                       codec: str) -> None:
        """Rejestruje nowy chunk (refcount startuje od 0)."""
        with self._lock:
            self.db.execute(
                "INSERT OR IGNORE INTO chunks(sha,raw_size,stored_size,codec,refcount)"
                " VALUES(?,?,?,?,0)",
                (sha, raw_size, stored_size, codec),
            )
            self.db.commit()

    def chunk_info(self, sha: str):
        with self._lock:
            return self.db.execute(
                "SELECT * FROM chunks WHERE sha=?", (sha,)).fetchone()

    def orphans(self) -> list[str]:
        with self._lock:
            return [r["sha"] for r in self.db.execute(
                "SELECT sha FROM chunks WHERE refcount<=0")]

    def drop_chunk(self, sha: str) -> None:
        with self._lock:
            self.db.execute("DELETE FROM chunks WHERE sha=?", (sha,))
            self.db.commit()

    # ------------------------------------------------------------------ staty
    def used_bytes(self) -> int:
        """Realnie zajęte miejsce (po kompresji, tylko żywe chunki)."""
        with self._lock:
            row = self.db.execute(
                "SELECT COALESCE(SUM(stored_size),0) AS s FROM chunks WHERE refcount>0"
            ).fetchone()
        return int(row["s"])

    def raw_bytes(self) -> int:
        """Rozmiar danych przed kompresją."""
        with self._lock:
            row = self.db.execute(
                "SELECT COALESCE(SUM(raw_size),0) AS s FROM chunks WHERE refcount>0"
            ).fetchone()
        return int(row["s"])

    def stats(self) -> dict:
        with self._lock:
            files = self.db.execute(
                "SELECT COUNT(*) c FROM inodes WHERE kind='file'").fetchone()["c"]
            dirs = self.db.execute(
                "SELECT COUNT(*) c FROM inodes WHERE kind='dir'").fetchone()["c"]
            chunks = self.db.execute(
                "SELECT COUNT(*) c FROM chunks WHERE refcount>0").fetchone()["c"]
            all_chunks = self.db.execute("SELECT COUNT(*) c FROM chunks").fetchone()["c"]
        return {
            "files": files,
            "dirs": dirs,
            "chunks": chunks,
            "chunks_total": all_chunks,
            "used_bytes": self.used_bytes(),
            "raw_bytes": self.raw_bytes(),
        }

    def close(self) -> None:
        with self._lock:
            self.db.commit()
            self.db.close()
