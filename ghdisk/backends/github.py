"""Backend GitHub — chunki jako bloby w repozytorium.

Zapis jest BUFOROWANY: `put()` tylko kolejkuje, a `flush()` robi JEDEN commit
przez Git Data API (bloby -> drzewo -> commit -> update ref). Dzięki temu
zapis 100 chunków to ~5 wywołań API, a nie 100.
"""

import base64

import requests

from .base import Backend

API = "https://api.github.com"


class GitHubBackend(Backend):
    def __init__(self, repo: str, token: str, branch: str = "main",
                 prefix: str = "objects", timeout: int = 60):
        if "/" not in repo:
            raise ValueError("repo musi mieć format 'owner/name'")
        self.repo = repo
        self.branch = branch
        self.prefix = prefix.strip("/")
        self.timeout = timeout
        self.s = requests.Session()
        self.s.headers.update({
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "ghdisk/1.0",
        })
        self._pending: dict[str, bytes] = {}
        self._deleted: set[str] = set()

    # ------------------------------------------------------------------ utils
    def _url(self, path: str) -> str:
        return f"{API}/repos/{self.repo}{path}"

    def _obj_path(self, sha: str) -> str:
        return f"{self.prefix}/{sha[:2]}/{sha[2:4]}/{sha}.zst"

    def _check(self, r: requests.Response) -> requests.Response:
        if r.status_code >= 400:
            raise RuntimeError(f"GitHub API {r.status_code}: {r.text[:300]}")
        return r

    # ------------------------------------------------------------------- API
    def put(self, sha: str, blob: bytes) -> None:
        self._pending[sha] = blob
        self._deleted.discard(sha)

    def get(self, sha: str) -> bytes:
        if sha in self._pending:
            return self._pending[sha]
        r = self.s.get(
            self._url(f"/contents/{self._obj_path(sha)}"),
            params={"ref": self.branch},
            headers={"Accept": "application/vnd.github.raw"},
            timeout=self.timeout,
        )
        if r.status_code == 404:
            raise KeyError(sha)
        self._check(r)
        return r.content

    def delete(self, sha: str) -> None:
        self._pending.pop(sha, None)
        self._deleted.add(sha)

    def exists(self, sha: str) -> bool:
        if sha in self._pending:
            return True
        r = self.s.get(
            self._url(f"/contents/{self._obj_path(sha)}"),
            params={"ref": self.branch},
            timeout=self.timeout,
        )
        return r.status_code == 200

    def flush(self) -> int:
        if not self._pending and not self._deleted:
            return 0

        # 1. aktualny commit i drzewo
        r = self.s.get(self._url(f"/git/ref/heads/{self.branch}"), timeout=self.timeout)
        if r.status_code == 404:
            raise RuntimeError(
                f"Gałąź '{self.branch}' nie istnieje. Utwórz repo z README "
                f"(auto_init) albo podaj istniejącą gałąź."
            )
        self._check(r)
        head = r.json()["object"]["sha"]
        r = self.s.get(self._url(f"/git/commits/{head}"), timeout=self.timeout)
        self._check(r)
        base_tree = r.json()["tree"]["sha"]

        # 2. bloby
        entries = []
        for sha, blob in self._pending.items():
            r = self.s.post(
                self._url("/git/blobs"),
                json={"content": base64.b64encode(blob).decode("ascii"),
                      "encoding": "base64"},
                timeout=self.timeout,
            )
            self._check(r)
            entries.append({
                "path": self._obj_path(sha),
                "mode": "100644",
                "type": "blob",
                "sha": r.json()["sha"],
            })

        # 3. usunięcia (sha=None usuwa ścieżkę z drzewa)
        for sha in self._deleted:
            entries.append({
                "path": self._obj_path(sha),
                "mode": "100644",
                "type": "blob",
                "sha": None,
            })

        if not entries:
            return 0

        # 4. drzewo
        r = self.s.post(
            self._url("/git/trees"),
            json={"base_tree": base_tree, "tree": entries},
            timeout=self.timeout,
        )
        self._check(r)
        new_tree = r.json()["sha"]

        # 5. commit
        n = len(self._pending)
        msg = f"ghdisk: store {n} chunk(s)" if n else "ghdisk: gc"
        r = self.s.post(
            self._url("/git/commits"),
            json={"message": msg, "tree": new_tree, "parents": [head]},
            timeout=self.timeout,
        )
        self._check(r)
        new_commit = r.json()["sha"]

        # 6. przesunięcie gałęzi
        r = self.s.patch(
            self._url(f"/git/refs/heads/{self.branch}"),
            json={"sha": new_commit, "force": False},
            timeout=self.timeout,
        )
        self._check(r)

        written = len(self._pending)
        self._pending.clear()
        self._deleted.clear()
        return written

    # --------------------------------------------------------------- pomocnicze
    def repo_info(self) -> dict:
        r = self.s.get(self._url(""), timeout=self.timeout)
        self._check(r)
        return r.json()

    def quota_used(self) -> int:
        """Rozmiar repozytorium wg GitHuba (bajty)."""
        info = self.repo_info()
        return int(info.get("size", 0)) * 1024  # GitHub podaje w KiB
