#!/usr/bin/env bash
# Demo ghdisk — pokazuje 1024 PB, dedup i kompresję bez GitHuba (backend lokalny).
set -euo pipefail

export GHDISK_BACKEND=local
export GHDISK_LOCAL_ROOT="${TMPDIR:-/tmp}/ghdisk-demo"
export GHDISK_INDEX="${TMPDIR:-/tmp}/ghdisk-demo/index.db"
export GHDISK_REAL_QUOTA=5368709120

rm -rf "$GHDISK_LOCAL_ROOT"
mkdir -p "$GHDISK_LOCAL_ROOT"

echo "=== 1. Inicjalizacja ==="
ghdisk init

echo
echo "=== 2. Zapis 8 MiB tekstu ==="
head -c 8388608 /dev/zero | tr '\0' 'A' > /tmp/demo-a.bin
ghdisk put /tmp/demo-a.bin /demo/a.bin

echo
echo "=== 3. Druga kopia tego samego pliku (dedup) ==="
ghdisk put /tmp/demo-a.bin /demo/b.bin

echo
echo "=== 4. Zajętość ==="
ghdisk df
echo
echo "--- uczciwy widok (realny limit GitHuba) ---"
ghdisk df --honest

echo
echo "=== 5. Listowanie i odczyt ==="
ghdisk ls /demo
ghdisk get /demo/a.bin /tmp/demo-out.bin
cmp /tmp/demo-a.bin /tmp/demo-out.bin && echo "✓ odczyt identyczny z oryginałem"

echo
echo "=== 6. Usunięcie i GC ==="
ghdisk rm /demo/a.bin
ghdisk rm /demo/b.bin
ghdisk df

rm -f /tmp/demo-a.bin /tmp/demo-out.bin
echo
echo "✓ Demo zakończone."
