"""Backend lokalny — chunki jako pliki na dysku (tryb offline / testy)."""

import os

from .base import Backend


class LocalBackend(Backend):
    """Przechowuje chunki w <root>/objects/ab/cd/<sha>.zst"""

    def __init__(self, root: str):
        self.root = os.path.abspath(root)
        os.makedirs(os.path.join(self.root, "objects"), exist_ok=True)

    def _path(self, sha: str) -> str:
        return os.path.join(self.root, "objects", sha[:2], sha[2:4], sha + ".zst")

    def put(self, sha: str, blob: bytes) -> None:
        p = self._path(sha)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        tmp = p + ".tmp"
        with open(tmp, "wb") as f:
            f.write(blob)
        os.replace(tmp, p)

    def get(self, sha: str) -> bytes:
        p = self._path(sha)
        if not os.path.exists(p):
            raise KeyError(sha)
        with open(p, "rb") as f:
            return f.read()

    def delete(self, sha: str) -> None:
        p = self._path(sha)
        if os.path.exists(p):
            os.remove(p)

    def exists(self, sha: str) -> bool:
        return os.path.exists(self._path(sha))
