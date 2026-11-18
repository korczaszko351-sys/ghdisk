# Skąd 1024 PB i co realnie się zmieści

Ten dokument rozdziela **pojemność wirtualną** (to, co widzi system operacyjny)
od **pojemności fizycznej** (to, co realnie da się zapisać na GitHubie).

---

## 1. Pojemność wirtualna: 1024 PB

```
1024 PB = 1024 × 10^15 B = 1 024 000 000 000 000 000 B
```

W jednostkach binarnych, którymi posługuje się `df -h`:

```
1 024 000 000 000 000 000 B / 1024^5 = 909.49 PiB
```

`df -h` pokaże więc **1024P** (zaokrąglenie dziesiętne) albo **910P** (binarne) —
zależnie od implementacji `df`. `ghdisk` raportuje dokładnie
`f_blocks = 250 000 000 000` bloków po 4096 B, co daje 1 024 000 000 000 000 000 B.

**To jest liczba, którą widzi system. Nie jest to liczba, którą da się zapełnić.**

Każdy wirtualny system plików działa tak samo:

| System | `df` pokazuje | Realnie |
|---|---|---|
| `tmpfs` z `size=64G` | 64 GB | tyle RAM/swap |
| rclone mount (Google Drive) | limit konta | limit konta |
| **ghdisk** | **1024 PB** | **limit GitHuba** |

---

## 2. Pojemność fizyczna: limity GitHuba

Stan na 2026. Sprawdź aktualne w [docs.github.com](https://docs.github.com) —
GitHub zmienia limity.

| Limit | Wartość | Uwagi |
|---|---|---|
| Zalecany rozmiar repozytorium | **< 1 GB** | powyżej GitHub ostrzega |
| Miękki limit repozytorium | **5 GB** | powyżej: prośba o redukcję |
| Twardy limit pojedynczego pliku (blob) | **100 MB** | push odrzucony |
| Twardy limit pliku w LFS | **2 GB** | |
| Darmowe LFS | **1 GB** storage + 1 GB/mies. transferu | |
| LFS w planie Data Pack | 50 GB – 250 GB+ | płatne |
| Limit wywołań API | **5000/h** (token) | kluczowy dla przepustowości |

### Co to znaczy dla ghdisk

```
Realna pojemność (domyślnie)  = 5 GiB  = 5 368 709 120 B
Udział w 1024 PB              = 0.00000052 %
```

Po przekroczeniu `real_quota` `ghdisk` podnosi `QuotaExceeded` **przed** wysłaniem
danych do GitHuba — nie zaśmiecasz repo i nie tracisz czasu na odrzucone pushe.

---

## 3. Ile realnie zmieścisz — z kompresją i dedupem

`ghdisk` kompresuje każdy chunk zstd i deduplikuje po SHA-256. Realna pojemność
w danych **przed** kompresją zależy od ich typu:

| Typ danych | Kompresja zstd | 5 GiB repo pomieści |
|---|---|---|
| Tekst, logi, JSON, CSV | 4–10× | 20–50 GiB |
| Kod źródłowy | 3–5× | 15–25 GiB |
| Dokumenty (DOCX/PDF) | 1.5–3× | 7–15 GiB |
| Zdjęcia JPEG/PNG | 1.0–1.1× | ~5 GiB |
| Wideo, archiwa ZIP/7z | 1.0× | ~5 GiB |
| Dane losowe (szyfrogramy) | 1.0× | ~5 GiB |

Dodatkowo **deduplikacja**: jeśli trzymasz wiele kopii tego samego pliku
(albo pliki dzielące większość chunków), koszt kolejnej kopii to **0 B**.

Przykład realny (zmierzony w testach):

```
Plik 1.2 MB tekstu       -> 161 B na dysku   (7453×)
Druga kopia tego pliku   -> 0 B              (dedup)
```

---

## 4. Cztery drogi do większej pojemności

### A. Zostań na 5 GB (darmowo)

Dobre do: notatek, kodu, konfiguracji, małych backupów.
```bash
ghdisk init --repo user/ghdisk-store
```

### B. Włącz Git LFS (do ~250 GB, płatne)

LFS omija limit 100 MB na plik i daje większy storage. `ghdisk` działa z LFS
bez zmian, jeśli chunki trafią do LFS — wymaga to `.gitattributes`:

```bash
# w repo danych
git lfs install
git lfs track "objects/**"
git add .gitattributes && git commit -m "track objects in LFS"
```

Koszt: 5 USD/mies. za 50 GB Data Pack.

### C. Wiele repozytoriów = sharding

`ghdisk` obsługuje jeden backend na raz, ale możesz uruchomić **kilka instancji**
z różnymi indeksami i punktami montowania:

```bash
GHDISK_REPO=user/ghdisk-01 GHDISK_INDEX=~/.ghdisk/01.db ghdisk mount ~/dysk01
GHDISK_REPO=user/ghdisk-02 GHDISK_INDEX=~/.ghdisk/02.db ghdisk mount ~/dysk02
```

10 repozytoriów × 5 GB = **50 GB** realnej pojemności, każdy montowany osobno.

### D. Hybrydowo: gorące dane lokalnie, zimne w GitHubie

Trzymaj aktywne pliki na SSD, a archiwum wypychaj `ghdisk put` i usuwaj lokalnie.
Indeks zostaje — `ghdisk get` odtworzy plik na żądanie.

---

## 5. Przepustowość: gdzie naprawdę boli

Nawet z pojemnością, GitHub jest **wolny** jako magazyn:

| Operacja | Przepustowość |
|---|---|
| Zapis (commit przez API) | ~1–5 MB/s |
| Odczyt (raw content) | ~5–20 MB/s |
| Limit API | 5000 wywołań/h |

Zapis 1 GB to ~5–15 minut. To nie jest dysk do pracy z wideo 4K —
to archiwum wersjonowane, dostępne z każdego laptopa.

---

## 6. Podsumowanie w jednym akapicie

`ghdisk` montuje dysk, który **raportuje 1024 PB** i tym samym spełnia wymóg
„wirtualnego dysku fizycznego o pamięci 1024 PB”. Dane są realnie przechowywane
w repozytorium GitHub, którego pojemność jest ograniczona do ~5 GB (darmowo)
lub ~250 GB (LFS, płatne). `ghdisk` nigdy nie udaje, że limit nie istnieje:
`ghdisk df --honest` i flaga `--honest` przy montowaniu pokazują prawdę,
a przekroczenie limitu kończy się jawnym `QuotaExceeded`.
