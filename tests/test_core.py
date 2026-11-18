"""Testy jednostkowe rdzenia ghdisk (bez sieci, backend lokalny)."""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ghdisk import capacity, chunker, codec  # noqa: E402
from ghdisk.backends.local import LocalBackend  # noqa: E402
from ghdisk.index import Index  # noqa: E402
from ghdisk.store import ChunkStore, QuotaExceeded  # noqa: E402
from ghdisk.vfs import VFS  # noqa: E402


@pytest.fixture()
def vfs(tmp_path):
    idx = Index(str(tmp_path / "index.db"))
    be = LocalBackend(str(tmp_path / "store"))
    st = ChunkStore(idx, be, chunk_size=1024, codec="zstd")
    v = VFS(idx, st)
    yield v
    idx.close()


# ------------------------------------------------------------------ capacity
def test_virtual_capacity_is_1024_pb():
    assert capacity.VIRTUAL_TOTAL_BYTES == 1024 * 10**15
    assert capacity.VIRTUAL_TOTAL_BYTES == 1_024_000_000_000_000_000


def test_statfs_reports_1024_pb():
    st = capacity.statfs_dict(used_bytes=0, real_quota=5 * 1024**3)
    total = st["f_blocks"] * st["f_bsize"]
    assert total == capacity.VIRTUAL_TOTAL_BYTES


def test_statfs_honest_mode():
    st = capacity.statfs_dict(used_bytes=0, real_quota=5 * 1024**3, honest=True)
    assert st["f_blocks"] * st["f_bsize"] == 5 * 1024**3


def test_human_units():
    assert capacity.human(1024) == "1.00 KiB"
    assert capacity.human(1024**3) == "1.00 GiB"
    assert capacity.human_decimal(10**15) == "1.00 PB"


# ------------------------------------------------------------------- chunker
def test_split_and_join():
    data = b"x" * 2500
    parts = list(chunker.split(data, 1000))
    assert [len(p) for p in parts] == [1000, 1000, 500]
    assert chunker.join(parts) == data


def test_chunk_count():
    assert chunker.chunk_count(0) == 0
    assert chunker.chunk_count(1) == 1
    assert chunker.chunk_count(4 * 1024 * 1024) == 1
    assert chunker.chunk_count(4 * 1024 * 1024 + 1) == 2


# --------------------------------------------------------------------- codec
@pytest.mark.parametrize("name", ["none", "zlib", "zstd"])
def test_codec_roundtrip(name):
    data = b"abc" * 1000
    blob = codec.compress(data, name)
    assert codec.decompress(blob) == data


def test_codec_compresses_repetitive_data():
    data = b"a" * 100_000
    blob = codec.compress(data, "zstd")
    assert len(blob) < len(data) / 10


# ----------------------------------------------------------------------- VFS
def test_write_read_roundtrip(vfs):
    data = os.urandom(5000)
    vfs.write_file("/a/b/c.bin", data)
    assert vfs.read_file("/a/b/c.bin") == data


def test_read_range_touches_only_needed_chunks(vfs):
    data = bytes(range(256)) * 20  # 5120 B -> 5 chunków po 1024
    vfs.write_file("/r.bin", data)
    assert vfs.read_range("/r.bin", 0, 10) == data[:10]
    assert vfs.read_range("/r.bin", 1020, 10) == data[1020:1030]
    assert vfs.read_range("/r.bin", 5000, 200) == data[5000:5200]


def test_dedup_identical_files_cost_nothing(vfs):
    data = b"duplicate payload " * 500
    vfs.write_file("/one.bin", data)
    used_after_first = vfs.index.used_bytes()
    r = vfs.write_file("/two.bin", data)
    assert r["stored_delta"] == 0
    assert vfs.index.used_bytes() == used_after_first


def test_dedup_partial_overlap(vfs):
    # 3 różne chunki, żeby dedup był mierzalny (same "A" kompresują się do ~0 B)
    c1, c2, c3 = b"A" * 1024, b"B" * 1024, b"C" * 1024
    vfs.write_file("/p1.bin", c1 + c2)
    used1 = vfs.index.used_bytes()
    vfs.write_file("/p2.bin", c1 + c2 + c3)  # 2 wspólne + 1 nowy
    used2 = vfs.index.used_bytes()
    assert used2 > used1
    assert used2 < used1 * 2


def test_mkdir_listdir_rmdir(vfs):
    vfs.mkdir("/docs")
    vfs.write_file("/docs/x.txt", b"hi")
    assert vfs.listdir("/") == ["docs"]
    assert vfs.listdir("/docs") == ["x.txt"]
    with pytest.raises(OSError):
        vfs.rmdir("/docs")  # niepusty
    vfs.unlink("/docs/x.txt")
    vfs.rmdir("/docs")
    assert vfs.listdir("/") == []


def test_rename(vfs):
    vfs.write_file("/old.txt", b"data")
    vfs.rename("/old.txt", "/new.txt")
    assert vfs.read_file("/new.txt") == b"data"
    with pytest.raises(FileNotFoundError):
        vfs.read_file("/old.txt")


def test_unlink_then_gc_frees_space(vfs):
    vfs.write_file("/tmp.bin", os.urandom(3000))
    assert vfs.index.used_bytes() > 0
    vfs.unlink("/tmp.bin")
    vfs.store.gc()
    assert vfs.index.used_bytes() == 0


def test_quota_exceeded(tmp_path):
    idx = Index(str(tmp_path / "q.db"))
    be = LocalBackend(str(tmp_path / "qstore"))
    st = ChunkStore(idx, be, chunk_size=1024, codec="none", real_quota=2048)
    v = VFS(idx, st)
    with pytest.raises(QuotaExceeded):
        v.write_file("/big.bin", os.urandom(10_000))
    idx.close()


def test_stats_ratio(vfs):
    vfs.write_file("/z.bin", b"z" * 100_000)
    d = vfs.df()
    assert d["files"] == 1
    assert d["ratio"] > 10
