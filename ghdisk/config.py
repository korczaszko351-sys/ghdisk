"""Konfiguracja: plik TOML + zmienne środowiskowe."""

import os
import tomllib
from dataclasses import dataclass, field

DEFAULT_CONFIG = "~/.config/ghdisk/config.toml"

#: Domyślny realny limit GitHuba (miękki limit repo = 5 GB).
DEFAULT_REAL_QUOTA = 5 * 1024**3


@dataclass
class Config:
    repo: str = ""
    token: str = ""
    branch: str = "main"
    prefix: str = "objects"
    backend: str = "github"
    local_root: str = "~/.local/share/ghdisk"
    index_path: str = "~/.local/share/ghdisk/index.db"
    chunk_size: int = 4 * 1024 * 1024
    codec: str = "zstd"
    real_quota: int = DEFAULT_REAL_QUOTA
    mountpoint: str = "~/ghdisk"
    honest_df: bool = False
    extra: dict = field(default_factory=dict)

    @property
    def index_file(self) -> str:
        return os.path.expanduser(self.index_path)

    @property
    def local_dir(self) -> str:
        return os.path.expanduser(self.local_root)

    @property
    def mount_dir(self) -> str:
        return os.path.expanduser(self.mountpoint)


def load(path: str | None = None) -> Config:
    """Wczytuje konfigurację: plik TOML, potem nadpisania ze środowiska."""
    cfg = Config()
    p = os.path.expanduser(path or os.environ.get("GHDISK_CONFIG", DEFAULT_CONFIG))
    if os.path.exists(p):
        with open(p, "rb") as f:
            data = tomllib.load(f)
        for k, v in data.items():
            if hasattr(cfg, k):
                setattr(cfg, k, v)
            else:
                cfg.extra[k] = v

    # zmienne środowiskowe mają priorytet
    env_map = {
        "GHDISK_REPO": "repo",
        "GITHUB_TOKEN": "token",
        "GH_TOKEN": "token",
        "GHDISK_BRANCH": "branch",
        "GHDISK_BACKEND": "backend",
        "GHDISK_LOCAL_ROOT": "local_root",
        "GHDISK_INDEX": "index_path",
        "GHDISK_MOUNTPOINT": "mountpoint",
    }
    for env, attr in env_map.items():
        val = os.environ.get(env)
        if val:
            setattr(cfg, attr, val)
    if os.environ.get("GHDISK_REAL_QUOTA"):
        cfg.real_quota = int(os.environ["GHDISK_REAL_QUOTA"])
    if os.environ.get("GHDISK_CHUNK_SIZE"):
        cfg.chunk_size = int(os.environ["GHDISK_CHUNK_SIZE"])
    if os.environ.get("GHDISK_CODEC"):
        cfg.codec = os.environ["GHDISK_CODEC"]
    return cfg


def save(cfg: Config, path: str | None = None) -> str:
    """Zapisuje konfigurację do TOML (bez tokena — ten trzymaj w env)."""
    p = os.path.expanduser(path or DEFAULT_CONFIG)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    lines = [
        "# ghdisk — konfiguracja",
        f'repo = "{cfg.repo}"',
        f'branch = "{cfg.branch}"',
        f'prefix = "{cfg.prefix}"',
        f'backend = "{cfg.backend}"',
        f'local_root = "{cfg.local_root}"',
        f'index_path = "{cfg.index_path}"',
        f"chunk_size = {cfg.chunk_size}",
        f'codec = "{cfg.codec}"',
        f"real_quota = {cfg.real_quota}",
        f'mountpoint = "{cfg.mountpoint}"',
        f"honest_df = {str(cfg.honest_df).lower()}",
        "",
        "# Token NIE jest tu zapisywany. Użyj zmiennej GITHUB_TOKEN.",
    ]
    with open(p, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return p
