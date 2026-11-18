"""Matematyka pojemności dysku.

1024 PB = 1 024 000 000 000 000 000 bajtów (1.024 EB w systemie dziesiętnym).
To pojemność WIRTUALNA — tyle widzi system operacyjny w `df -h`.
Realną pojemność ogranicza GitHub (patrz docs/LIMITS.md).
"""

PB = 10**15

#: Pojemność wirtualna raportowana systemowi operacyjnemu.
VIRTUAL_TOTAL_BYTES = 1024 * PB  # 1_024_000_000_000_000_000 B

#: Rozmiar bloku raportowany w statfs (standardowy dla ext4/xfs).
BLOCK_SIZE = 4096

#: Maksymalna długość nazwy pliku.
NAME_MAX = 255


def blocks(nbytes: int) -> int:
    """Liczba bloków 4096 B dla danej liczby bajtów."""
    return nbytes // BLOCK_SIZE


def human(nbytes: int) -> str:
    """Czytelny zapis rozmiaru (jednostki binarne)."""
    n = float(nbytes)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB", "PiB", "EiB"):
        if abs(n) < 1024.0 or unit == "EiB":
            if unit == "B":
                return f"{int(n)} B"
            return f"{n:.2f} {unit}"
        n /= 1024.0
    return f"{nbytes} B"


def human_decimal(nbytes: int) -> str:
    """Czytelny zapis rozmiaru (jednostki dziesiętne — jak podaje producent).

    Zatrzymuje się na PB, żeby 1024 PB było widoczne jako "1024.00 PB",
    a nie "1.02 EB".
    """
    n = float(nbytes)
    for unit in ("B", "kB", "MB", "GB", "TB", "PB"):
        if abs(n) < 1000.0 or unit == "PB":
            if unit == "B":
                return f"{int(n)} B"
            return f"{n:.2f} {unit}"
        n /= 1000.0
    return f"{nbytes} B"


def statfs_dict(used_bytes: int, real_quota: int, honest: bool = False) -> dict:
    """Słownik dla FUSE.statfs.

    honest=False -> system widzi 1024 PB (pojemność wirtualna).
    honest=True  -> system widzi realny limit GitHuba (real_quota).
    """
    total = real_quota if honest else VIRTUAL_TOTAL_BYTES
    free = max(0, total - used_bytes)
    return {
        "f_bsize": BLOCK_SIZE,
        "f_frsize": BLOCK_SIZE,
        "f_blocks": blocks(total),
        "f_bfree": blocks(free),
        "f_bavail": blocks(free),
        "f_files": 1_000_000,
        "f_ffree": 1_000_000,
        "f_favail": 1_000_000,
        "f_flag": 0,
        "f_namemax": NAME_MAX,
    }
