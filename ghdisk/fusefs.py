"""System plików FUSE — montuje wirtualny dysk 1024 PB.

Wymaga: libfuse (Linux: `sudo apt install fuse3 libfuse2`) + pakiet `fusepy`.
"""

import errno
import os
import stat as statmod
import time

from .capacity import statfs_dict
from .vfs import VFS

try:
    from fuse import FUSE, FuseOSError, Operations
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        "Brak pakietu 'fusepy'. Zainstaluj: pip install fusepy\n"
        "oraz systemowo: sudo apt install fuse3 libfuse2"
    ) from exc


class GhDiskFS(Operations):
    """Implementacja FUSE nad VFS.

    Zapis jest buforowany w pamięci uchwytu pliku i commitowany przy
    flush/release — jeden commit GitHuba na plik zamiast jednego na chunk.
    """

    def __init__(self, vfs: VFS, real_quota: int, honest: bool = False):
        self.vfs = vfs
        self.real_quota = real_quota
        self.honest = honest
        self._buffers: dict[int, bytearray] = {}
        self._paths: dict[int, str] = {}
        self._next_fh = 1

    # ------------------------------------------------------------------ helpers
    def _row(self, path):
        row = self.vfs.index.get(path)
        if row is None:
            raise FuseOSError(errno.ENOENT)
        return row

    def _attrs(self, row) -> dict:
        is_dir = row["kind"] == "dir"
        mode = (statmod.S_IFDIR | (row["mode"] & 0o7777)) if is_dir else (
            statmod.S_IFREG | (row["mode"] & 0o7777))
        return {
            "st_mode": mode,
            "st_nlink": 2 if is_dir else 1,
            "st_size": 0 if is_dir else row["size"],
            "st_uid": os.getuid(),
            "st_gid": os.getgid(),
            "st_atime": row["atime"],
            "st_mtime": row["mtime"],
            "st_ctime": row["ctime"],
        }

    # ------------------------------------------------------------------- FUSE
    def getattr(self, path, fh=None):
        return self._attrs(self._row(path))

    def readdir(self, path, fh):
        return [".", ".."] + self.vfs.listdir(path)

    def statfs(self, path):
        return statfs_dict(self.vfs.index.used_bytes(), self.real_quota, self.honest)

    def mkdir(self, path, mode):
        try:
            self.vfs.mkdir(path, mode)
        except FileExistsError:
            raise FuseOSError(errno.EEXIST)

    def rmdir(self, path):
        try:
            self.vfs.rmdir(path)
        except OSError as e:
            raise FuseOSError(e.errno or errno.ENOTEMPTY)

    def unlink(self, path):
        try:
            self.vfs.unlink(path)
        except FileNotFoundError:
            raise FuseOSError(errno.ENOENT)

    def rename(self, old, new):
        try:
            self.vfs.rename(old, new)
        except FileNotFoundError:
            raise FuseOSError(errno.ENOENT)

    def chmod(self, path, mode):
        self.vfs.chmod(path, mode)

    def utimens(self, path, times=None):
        self.vfs.utime(path, times[1] if times else time.time())

    def truncate(self, path, length, fh=None):
        data = self.vfs.read_file(path) if self.vfs.index.exists(path) else b""
        data = data[:length].ljust(length, b"\0")
        self.vfs.write_file(path, data)

    def create(self, path, mode, fi=None):
        self.vfs.write_file(path, b"")
        fh = self._next_fh
        self._next_fh += 1
        self._buffers[fh] = bytearray()
        self._paths[fh] = path
        return fh

    def open(self, path, flags):
        fh = self._next_fh
        self._next_fh += 1
        self._paths[fh] = path
        if flags & (os.O_WRONLY | os.O_RDWR):
            self._buffers[fh] = bytearray(self.vfs.read_file(path))
        return fh

    def read(self, path, size, offset, fh):
        buf = self._buffers.get(fh)
        if buf is not None:
            return bytes(buf[offset : offset + size])
        return self.vfs.read_range(path, offset, size)

    def write(self, path, data, offset, fh):
        buf = self._buffers.get(fh)
        if buf is None:
            buf = bytearray(self.vfs.read_file(path))
            self._buffers[fh] = buf
        end = offset + len(data)
        if end > len(buf):
            buf.extend(b"\0" * (end - len(buf)))
        buf[offset:end] = data
        return len(data)

    def flush(self, path, fh):
        buf = self._buffers.get(fh)
        if buf is not None:
            self.vfs.write_file(path, bytes(buf))
        return 0

    def fsync(self, path, fdatasync, fh):
        return self.flush(path, fh)

    def release(self, path, fh):
        self.flush(path, fh)
        self._buffers.pop(fh, None)
        self._paths.pop(fh, None)
        return 0


def mount(vfs: VFS, mountpoint: str, real_quota: int, honest: bool = False,
          foreground: bool = True, allow_other: bool = False) -> None:
    """Montuje system plików."""
    os.makedirs(mountpoint, exist_ok=True)
    fs = GhDiskFS(vfs, real_quota=real_quota, honest=honest)
    FUSE(fs, mountpoint, foreground=foreground, allow_other=allow_other,
         nothreads=False, ro=False)
