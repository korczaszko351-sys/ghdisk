# ghdisk — wirtualny dysk 1024 PB na repozytorium GitHub

**Zamontuj dysk o pojemności 1024 PB na swoim laptopie i trzymaj jego dane w repozytorium GitHub.**

`ghdisk` to system plików FUSE, który:
- raportuje systemowi operacyjnemu **1024 PB** (1 024 000 000 000 000 000 B) pojemności,
- dzieli pliki na chunki 4 MiB, kompresuje je **zstd** i **deduplikuje** po SHA-256,
- trzyma metadane w lokalnym indeksie SQLite (natychmiastowe montowanie, brak listowania repo),
- zapisuje chunki do GitHuba **jednym commitem na plik** (Git Data API), a nie jednym na chunk.

```bash
$ df -h ~/ghdisk
Filesystem      Size  Used Avail Use% Mounted on
ghdisk         1024P   12M 1024P   1% /home/user/ghdisk
```

---

## ⚠️ Przeczytaj to najpierw: 1024 PB jest WIRTUALNE

To najważniejsza część dokumentacji. **GitHub nie daje 1024 PB.**

| Co | Wartość |
|---|---|
| Pojemność **raportowana** systemowi (`df -h`) | **1024 PB** = 1 024 000 000 000 000 000 B |
| Realna pojemność repozytorium GitHub (miękki limit) | **~5 GB** |
| Realna pojemność z GitHub LFS (darmowo) | ~6 GB (5 GB repo + 1 GB LFS) |
| Realna pojemność z GitHub LFS (paid) | do 250 GB+ (zależnie od planu) |
| Twardy limit pojedynczego pliku w repo | 100 MB (blob), 2 GB (LFS) |

`ghdisk` **nie oszukuje**: `df` pokazuje 1024 PB, bo tak działa każdy wirtualny system plików
(tak samo robi `tmpfs` z `size=` albo S3-mounted dyski). Ale gdy spróbujesz zapisać więcej niż
realny limit, dostaniesz **`QuotaExceeded`** — kontrolowane, z jasnym komunikatem, a nie ciche
przepełnienie. Pełne wyliczenia i obejścia: **[docs/LIMITS.md](docs/LIMITS.md)**.

Chcesz uczciwy widok? Użyj `ghdisk df --honest` albo zamontuj z `--honest`:

```bash
ghdisk mount ~/ghdisk --honest   # df pokaże realny limit GitHuba
```

---

## Szybki start (5 minut)

### 1. Wymagania

- Linux (testowane) lub macOS — FUSE
- Python **3.11+**
- `libfuse` (Linux): `sudo apt install fuse3 libfuse2`

### 2. Instalacja

```bash
git clone https://github.com/korczaszko351-sys/ghdisk.git
cd ghdisk
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[fuse,dev]"
```

### 3. Token GitHub

Utwórz token z zakresem **`repo`** (Settings → Developer settings → Personal access tokens):

```bash
export GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxx
```

> Token trzymaj **tylko** w zmiennej środowiskowej. `ghdisk` nigdy nie zapisuje go do pliku konfiguracyjnego.

### 4. Repozytorium na dane

Utwórz **puste** repo (np. `twoj-user/ghdisk-store`) z zaznaczonym *Add a README* —
potrzebna jest istniejąca gałąź `main`.

### 5. Konfiguracja i montowanie

```bash
ghdisk init --repo twoj-user/ghdisk-store
ghdisk mount ~/ghdisk
```

W drugim terminalu:

```bash
df -h ~/ghdisk                 # 1024P
echo "hello" > ~/ghdisk/hello.txt
ls -la ~/ghdisk
cat ~/ghdisk/hello.txt
```

Odmontowanie: `Ctrl+C` w terminalu z `mount` lub `fusermount -u ~/ghdisk`.

---

## Użycie CLI (bez montowania)

```bash
ghdisk put ./duzy-plik.bin /backup/duzy-plik.bin   # wgraj plik
ghdisk get /backup/duzy-plik.bin ./odzyskany.bin   # pobierz plik
ghdisk ls /backup                                  # listuj katalog
ghdisk rm /backup/duzy-plik.bin                    # usuń + GC
ghdisk df                                          # zajętość (wirtualna)
ghdisk df --honest                                 # zajętość (realna)
ghdisk gc                                          # usuń nieużywane chunki
ghdisk info                                        # konfiguracja
ghdisk bench --size 64                             # benchmark kompresji
```

Przykładowy wynik `ghdisk put`:

```
✓ ./duzy-plik.bin -> /backup/duzy-plik.bin
  rozmiar:        48.00 MiB
  chunków:        12 (unikalnych: 12)
  przyrost:       9.31 MiB
  czas:           3.42 s
```

---

## Jak to działa

```
┌──────────────┐   write()    ┌──────────────┐   chunk 4 MiB   ┌─────────────┐
│  aplikacja   │ ───────────► │  FUSE (VFS)  │ ──────────────► │  ChunkStore │
└──────────────┘              └──────────────┘                 └─────────────┘
                                     │                                │
                                     │ metadane                       │ SHA-256 + zstd
                                     ▼                                ▼
                              ┌──────────────┐                 ┌─────────────┐
                              │ SQLite index │                 │  Backend    │
                              │ inody+chunki │                 │ GitHub/Local│
                              └──────────────┘                 └─────────────┘
```

1. **Chunking** — plik dzielony na fragmenty 4 MiB (`ghdisk/chunker.py`).
2. **Kompresja** — każdy chunk kompresowany zstd (fallback: zlib), 1-bajtowy nagłówek kodeka.
3. **Deduplikacja** — adresowanie po SHA-256; identyczny chunk nie jest zapisywany drugi raz.
4. **Indeks** — SQLite trzyma drzewo katalogów, rozmiary, uprawnienia i mapowanie plik → chunki.
5. **Backend** — chunki lądują w `objects/ab/cd/<sha>.zst` w repozytorium.
6. **Batch commit** — `flush()` robi **jeden** commit na plik: bloby → drzewo → commit → ref.

### Dlaczego jeden commit na plik, a nie na chunk

GitHub ma limit ~5000 wywołań API/h. Zapis 1 GB w chunkach 4 MiB to 256 chunków.
Naiwna implementacja = 256 commitów = 256 × 5 wywołań = 1280 wywołań API.
`ghdisk` buforuje chunki i robi **jeden** commit: ~5 wywołań na plik.

### Deduplikacja w praktyce

```
$ ghdisk put kopia-1.iso /iso/kopia-1.iso
  przyrost: 4.12 GiB
$ ghdisk put kopia-2.iso /iso/kopia-2.iso   # ten sam plik
  przyrost: 0 B
```

---

## Konfiguracja

Plik `~/.config/ghdisk/config.toml` (tworzony przez `ghdisk init`):

```toml
repo = "twoj-user/ghdisk-store"
branch = "main"
prefix = "objects"
backend = "github"          # "github" | "local"
index_path = "~/.local/share/ghdisk/index.db"
chunk_size = 4194304        # 4 MiB
codec = "zstd"              # "zstd" | "zlib" | "none"
real_quota = 5368709120     # 5 GiB — realny limit GitHuba
mountpoint = "~/ghdisk"
honest_df = false           # true = df pokazuje realny limit
```

Nadpisania ze środowiska (mają priorytet nad plikiem):

| Zmienna | Znaczenie |
|---|---|
| `GITHUB_TOKEN` / `GH_TOKEN` | token GitHub (wymagany dla backendu `github`) |
| `GHDISK_REPO` | `owner/nazwa` |
| `GHDISK_BRANCH` | gałąź (domyślnie `main`) |
| `GHDISK_BACKEND` | `github` lub `local` |
| `GHDISK_REAL_QUOTA` | realny limit w bajtach |
| `GHDISK_CHUNK_SIZE` | rozmiar chunka w bajtach |
| `GHDISK_CODEC` | `zstd` / `zlib` / `none` |
| `GHDISK_MOUNTPOINT` | punkt montowania |
| `GHDISK_INDEX` | ścieżka indeksu SQLite |

### Tryb offline (bez GitHuba)

```bash
export GHDISK_BACKEND=local
ghdisk init
ghdisk put plik.bin /plik.bin
```

Chunki lądują w `~/.local/share/ghdisk/objects/`. Przydatne do testów i do pracy bez sieci.

---

## Testy

```bash
pip install -e ".[dev]"
pytest -q
```

19 testów pokrywa: pojemność/statfs, chunking, kodeki, zapis/odczyt, odczyt zakresowy,
deduplikację (pełną i częściową), katalogi, rename, GC i przekroczenie limitu.

---

## Ograniczenia (uczciwie)

| Ograniczenie | Wpływ |
|---|---|
| Realna pojemność ~5 GB (GitHub) | 1024 PB to widok, nie magazyn — patrz [docs/LIMITS.md](docs/LIMITS.md) |
| Każdy zapis = commit | Historia repo rośnie; rób `git gc` po stronie serwera okresowo |
| Brak blokady między klientami | Dwa laptopy na tym samym repo = konflikt gałęzi |
| Zapis całego pliku w RAM | Plik > ~1 GB może zabraknąć pamięci (chunking jest, bufor nie) |
| Brak szyfrowania | Repo prywatne = dane prywatne; szyfruj przed `put`, jeśli trzeba |
| FUSE tylko POSIX | Windows: użyj CLI (`put`/`get`) albo WSL2 |

---

## Struktura projektu

```
ghdisk/
├── ghdisk/
│   ├── capacity.py      # matematyka 1024 PB, statfs
│   ├── chunker.py       # dzielenie na chunki
│   ├── codec.py         # zstd/zlib + nagłówki
│   ├── index.py         # SQLite: inody, chunki, refcounty
│   ├── store.py         # ChunkStore: dedup, kompresja, GC, limit
│   ├── vfs.py           # wspólna logika ścieżek
│   ├── fusefs.py        # warstwa FUSE
│   ├── config.py        # TOML + env
│   ├── cli.py           # komendy
│   └── backends/
│       ├── base.py      # interfejs
│       ├── local.py     # chunki na dysku
│       └── github.py    # chunki w repo (Git Data API)
├── tests/test_core.py
├── docs/LIMITS.md       # skąd 1024 PB i co realnie zmieścisz
├── docs/INSTALL.md      # instrukcja uruchomienia na laptopie
├── pyproject.toml
└── README.md
```

## Licencja

MIT — patrz [LICENSE](LICENSE).
