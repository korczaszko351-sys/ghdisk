"""CLI ghdisk — init, put, get, ls, rm, df, gc, mount, info, bench."""

import argparse
import os
import sys
import time

from . import __version__, capacity, config as cfgmod
from .backends import get_backend
from .index import Index
from .store import ChunkStore
from .vfs import VFS


def _open(cfg, need_backend: bool = True):
    index = Index(cfg.index_file)
    backend = None
    if need_backend:
        if cfg.backend == "github":
            if not cfg.repo:
                sys.exit("Błąd: brak --repo (np. owner/ghdisk-store) lub GHDISK_REPO")
            if not cfg.token:
                sys.exit("Błąd: brak tokena. Ustaw GITHUB_TOKEN (scope: repo).")
            backend = get_backend(
                "github", repo=cfg.repo, token=cfg.token,
                branch=cfg.branch, prefix=cfg.prefix,
            )
        else:
            backend = get_backend("local", root=cfg.local_dir)
    store = ChunkStore(index, backend, chunk_size=cfg.chunk_size,
                       codec=cfg.codec, real_quota=cfg.real_quota)
    return index, store, VFS(index, store)


# --------------------------------------------------------------------- komendy
def cmd_init(args, cfg):
    cfg.repo = args.repo or cfg.repo
    cfg.branch = args.branch or cfg.branch
    path = cfgmod.save(cfg, args.config)
    index, _, _ = _open(cfg, need_backend=False)
    index.close()
    print(f"✓ Konfiguracja zapisana: {path}")
    print(f"✓ Indeks utworzony:     {cfg.index_file}")
    print(f"  Repo:   {cfg.repo or '(brak — ustaw GHDISK_REPO)'}")
    print(f"  Gałąź:  {cfg.branch}")
    print(f"  Limit:  {capacity.human(cfg.real_quota)} (realny, GitHub)")
    print(f"  Widok:  {capacity.human(capacity.VIRTUAL_TOTAL_BYTES)} (wirtualny)")
    print("\nToken ustaw w środowisku:  export GITHUB_TOKEN=ghp_xxx")


def cmd_put(args, cfg):
    index, store, vfs = _open(cfg)
    src = args.src
    dst = args.dst or "/" + os.path.basename(src)
    t0 = time.time()
    with open(src, "rb") as f:
        data = f.read()
    st = vfs.write_file(dst, data)
    dt = time.time() - t0
    print(f"✓ {src} -> {st['path']}")
    print(f"  rozmiar:        {capacity.human(st['size'])}")
    print(f"  chunków:        {st['chunks']} (unikalnych: {st['unique_chunks']})")
    print(f"  przyrost:       {capacity.human(max(0, st['stored_delta']))}")
    print(f"  czas:           {dt:.2f} s")
    index.close()


def cmd_get(args, cfg):
    index, store, vfs = _open(cfg)
    data = vfs.read_file(args.path)
    with open(args.dst, "wb") as f:
        f.write(data)
    print(f"✓ {args.path} -> {args.dst} ({capacity.human(len(data))})")
    index.close()


def cmd_ls(args, cfg):
    index, store, vfs = _open(cfg, need_backend=False)
    for name in vfs.listdir(args.path):
        full = (args.path.rstrip("/") + "/" + name)
        row = index.get(full)
        kind = "d" if row["kind"] == "dir" else "-"
        size = "" if row["kind"] == "dir" else capacity.human(row["size"])
        print(f"{kind} {size:>12}  {name}")
    index.close()


def cmd_rm(args, cfg):
    index, store, vfs = _open(cfg)
    vfs.unlink(args.path)
    n = store.gc()
    print(f"✓ usunięto {args.path} (GC: {n} chunków)")
    index.close()


def cmd_df(args, cfg):
    index, store, vfs = _open(cfg, need_backend=False)
    d = vfs.df()
    used = d["used_bytes"]
    total = cfg.real_quota if args.honest else capacity.VIRTUAL_TOTAL_BYTES
    free = max(0, total - used)
    pct = (used / total * 100) if total else 0
    print(f"Pojemność:  {capacity.human(total)}"
          f"  ({'realna' if args.honest else 'wirtualna'})")
    print(f"Zajęte:     {capacity.human(used)}  ({pct:.4f}%)")
    print(f"Wolne:      {capacity.human(free)}")
    print(f"Pliki:      {d['files']}   Katalogi: {d['dirs']}   Chunki: {d['chunks']}")
    print(f"Dane przed kompresją: {capacity.human(d['raw_bytes'])}")
    print(f"Współczynnik kompresji: {d['ratio']:.2f}x")
    index.close()


def cmd_gc(args, cfg):
    index, store, vfs = _open(cfg)
    n = store.gc()
    print(f"✓ GC: usunięto {n} nieużywanych chunków")
    index.close()


def cmd_info(args, cfg):
    from . import codec as _codec

    print(f"ghdisk {__version__}")
    print(f"  backend:   {cfg.backend}")
    print(f"  repo:      {cfg.repo or '(brak)'}")
    print(f"  gałąź:     {cfg.branch}")
    print(f"  chunk:     {capacity.human(cfg.chunk_size)}")
    print(f"  kodek:     {cfg.codec}")
    print(f"  indeks:    {cfg.index_file}")
    print(f"  mountpoint:{cfg.mount_dir}")
    print(f"  limit realny: {capacity.human(cfg.real_quota)}")
    print(f"  widok:        {capacity.human(capacity.VIRTUAL_TOTAL_BYTES)}")
    print(f"  kodeki dostępne: {', '.join(_codec.available())}")


def cmd_mount(args, cfg):
    from .fusefs import mount

    index, store, vfs = _open(cfg)
    mp = args.mountpoint or cfg.mount_dir
    print(f"Montowanie {capacity.human(capacity.VIRTUAL_TOTAL_BYTES)} "
          f"w {mp} (Ctrl+C aby odmontować)")
    try:
        mount(vfs, mp, real_quota=cfg.real_quota,
              honest=args.honest or cfg.honest_df,
              foreground=True, allow_other=args.allow_other)
    except KeyboardInterrupt:
        print("\nOdmontowano.")
    finally:
        index.close()


def cmd_bench(args, cfg):
    """Mierzy kompresję i dedup na wygenerowanych danych."""
    index, store, vfs = _open(cfg, need_backend=False)
    size = args.size * 1024 * 1024
    print(f"Benchmark: {capacity.human(size)} danych, chunk "
          f"{capacity.human(cfg.chunk_size)}, kodek {cfg.codec}")
    payload = (b"ghdisk benchmark payload 0123456789 " * (size // 36 + 1))[:size]
    t0 = time.time()
    shas = store.put_bytes(payload)
    t1 = time.time()
    raw = sum(index.chunk_info(s)["raw_size"] for s in shas)
    stored = sum(index.chunk_info(s)["stored_size"] for s in shas)
    print(f"  chunków:      {len(shas)}")
    print(f"  przed:        {capacity.human(raw)}")
    print(f"  po:           {capacity.human(stored)}")
    print(f"  kompresja:    {raw / stored:.2f}x")
    print(f"  czas zapisu:  {t1 - t0:.2f} s "
          f"({capacity.human(int(size / max(t1 - t0, 1e-9)))}/s)")
    index.close()


# ----------------------------------------------------------------------- main
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ghdisk",
        description="Wirtualny dysk 1024 PB na repozytorium GitHub.",
    )
    p.add_argument("--config", help="ścieżka pliku konfiguracji")
    p.add_argument("--repo", help="owner/nazwa repozytorium")
    p.add_argument("--branch", help="gałąź (domyślnie main)")
    p.add_argument("--version", action="version", version=f"ghdisk {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("init", help="utwórz konfigurację i indeks")
    s.set_defaults(func=cmd_init)

    s = sub.add_parser("put", help="wgraj plik na dysk")
    s.add_argument("src")
    s.add_argument("dst", nargs="?")
    s.set_defaults(func=cmd_put)

    s = sub.add_parser("get", help="pobierz plik z dysku")
    s.add_argument("path")
    s.add_argument("dst")
    s.set_defaults(func=cmd_get)

    s = sub.add_parser("ls", help="listuj katalog")
    s.add_argument("path", nargs="?", default="/")
    s.set_defaults(func=cmd_ls)

    s = sub.add_parser("rm", help="usuń plik")
    s.add_argument("path")
    s.set_defaults(func=cmd_rm)

    s = sub.add_parser("df", help="zajętość dysku")
    s.add_argument("--honest", action="store_true",
                   help="pokaż realny limit GitHuba zamiast 1024 PB")
    s.set_defaults(func=cmd_df)

    s = sub.add_parser("gc", help="usuń nieużywane chunki")
    s.set_defaults(func=cmd_gc)

    s = sub.add_parser("info", help="pokaż konfigurację")
    s.set_defaults(func=cmd_info)

    s = sub.add_parser("mount", help="zamontuj dysk (FUSE)")
    s.add_argument("mountpoint", nargs="?")
    s.add_argument("--honest", action="store_true",
                   help="raportuj realny limit zamiast 1024 PB")
    s.add_argument("--allow-other", action="store_true")
    s.set_defaults(func=cmd_mount)

    s = sub.add_parser("bench", help="benchmark kompresji")
    s.add_argument("--size", type=int, default=64, help="MiB danych")
    s.set_defaults(func=cmd_bench)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    cfg = cfgmod.load(args.config)
    if args.repo:
        cfg.repo = args.repo
    if args.branch:
        cfg.branch = args.branch
    try:
        args.func(args, cfg)
    except KeyboardInterrupt:
        return 130
    except Exception as e:  # pragma: no cover
        print(f"Błąd: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
