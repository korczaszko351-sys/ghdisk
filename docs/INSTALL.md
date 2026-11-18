# Instrukcja uruchomienia na laptopie

Krok po kroku, od zera do zamontowanego dysku 1024 PB.

---

## Linux (Ubuntu / Debian / Fedora / Arch)

### 1. Zależności systemowe

```bash
# Debian / Ubuntu
sudo apt update
sudo apt install -y python3 python3-venv python3-pip fuse3 libfuse2 git

# Fedora
sudo dnf install -y python3 python3-pip fuse fuse-libs git

# Arch
sudo pacman -S --needed python python-pip fuse2 git
```

Sprawdź FUSE:

```bash
ls -l /dev/fuse          # powinno istnieć
fusermount --version
```

### 2. Pobierz i zainstaluj ghdisk

```bash
git clone https://github.com/korczaszko351-sys/ghdisk.git
cd ghdisk
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[fuse]"
```

Sprawdź:

```bash
ghdisk --version
ghdisk info
```

### 3. Token GitHub

1. Wejdź na https://github.com/settings/tokens
2. **Generate new token (classic)**
3. Zaznacz zakres **`repo`** (pełna kontrola nad prywatnymi repozytoriami)
4. Skopiuj token (zaczyna się od `ghp_`)

```bash
export GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxx
```

Dodaj do `~/.bashrc` lub `~/.zshrc`, żeby przetrwało restart:

```bash
echo 'export GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxx' >> ~/.bashrc
```

> **Bezpieczeństwo:** token w `~/.bashrc` jest czytelny dla procesów twojego użytkownika.
> Bezpieczniejsza alternatywa: `gh auth login` + `export GITHUB_TOKEN=$(gh auth token)`.

### 4. Repozytorium na dane

https://github.com/new → nazwa np. `ghdisk-store` → **Private** → ✅ *Add a README file* → Create.

> README jest konieczne: `ghdisk` potrzebuje istniejącej gałęzi `main`.

### 5. Konfiguracja

```bash
ghdisk init --repo twoj-user/ghdisk-store
```

Wynik:

```
✓ Konfiguracja zapisana: /home/user/.config/ghdisk/config.toml
✓ Indeks utworzony:     /home/user/.local/share/ghdisk/index.db
  Repo:   twoj-user/ghdisk-store
  Gałąź:  main
  Limit:  5.00 GiB (realny, GitHub)
  Widok:  1024.00 PB = 909.49 PiB (wirtualny)
```

### 6. Montowanie

```bash
mkdir -p ~/ghdisk
ghdisk mount ~/ghdisk
```

W **drugim terminalu**:

```bash
df -h ~/ghdisk
```

```
Filesystem      Size  Used Avail Use% Mounted on
GhDiskFS        910P     0  910P   0% /home/user/ghdisk
```

> `df -h` liczy w potęgach 1024, więc 1 024 000 000 000 000 000 B pokazuje jako **910P**.
> Sprawdź dokładnie: `df -B1 ~/ghdisk` → `1024000000000000000`.

Test zapisu:

```bash
echo "Witaj, 1024 PB!" > ~/ghdisk/test.txt
cat ~/ghdisk/test.txt
ls -la ~/ghdisk
```

### 7. Odmontowanie

```bash
# Ctrl+C w terminalu z mount
# albo:
fusermount -u ~/ghdisk
```

### 8. Autostart (opcjonalnie)

`~/.config/systemd/user/ghdisk.service`:

```ini
[Unit]
Description=ghdisk — wirtualny dysk 1024 PB
After=network-online.target

[Service]
Type=simple
Environment=GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxx
ExecStart=%h/ghdisk/.venv/bin/ghdisk mount %h/ghdisk
ExecStop=/bin/fusermount -u %h/ghdisk
Restart=on-failure

[Install]
WantedBy=default.target
```

```bash
systemctl --user daemon-reload
systemctl --user enable --now ghdisk.service
systemctl --user status ghdisk.service
```

---

## macOS

### 1. Zależności

```bash
brew install python@3.12 macfuse
```

macFUSE wymaga zatwierdzenia rozszerzenia jądra w
*System Settings → Privacy & Security* i restartu.

### 2. Instalacja

```bash
git clone https://github.com/korczaszko351-sys/ghdisk.git
cd ghdisk
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[fuse]"
```

### 3. Dalej jak na Linuksie

```bash
export GITHUB_TOKEN=ghp_xxx
ghdisk init --repo twoj-user/ghdisk-store
ghdisk mount ~/ghdisk
```

Odmontowanie: `umount ~/ghdisk` lub `diskutil unmount ~/ghdisk`.

---

## Windows

FUSE nie działa natywnie. Dwie opcje:

### A. WSL2 (zalecane)

```powershell
wsl --install -d Ubuntu
```

W WSL:

```bash
sudo apt install -y python3-venv fuse3 libfuse2
# dalej jak Linux
```

Dysk będzie widoczny w WSL pod `~/ghdisk`. Z Eksploratora: `\\wsl$\Ubuntu\home\<user>\ghdisk`.

### B. Samo CLI (bez montowania)

```powershell
git clone https://github.com/korczaszko351-sys/ghdisk.git
cd ghdisk
py -3.11 -m venv .venv
.venv\Scripts\activate
pip install -e .
$env:GITHUB_TOKEN="ghp_xxx"
ghdisk init --repo twoj-user/ghdisk-store
ghdisk put C:\dane\plik.bin /plik.bin
ghdisk get /plik.bin C:\dane\odzyskany.bin
```

---

## Rozwiązywanie problemów

| Objaw | Przyczyna | Rozwiązanie |
|---|---|---|
| `Brak pakietu 'fusepy'` | niezainstalowany extra | `pip install -e ".[fuse]"` |
| `fuse: device not found` | brak `libfuse` / kontener bez FUSE | `sudo apt install fuse3 libfuse2`; w Dockerze `--device /dev/fuse --cap-add SYS_ADMIN` |
| `Permission denied` przy montowaniu | brak uprawnień | `sudo usermod -aG fuse $USER` + relogin |
| `Gałąź 'main' nie istnieje` | repo bez README | utwórz repo z *Add a README* |
| `GitHub API 401` | zły/wygasły token | nowy token, `export GITHUB_TOKEN=...` |
| `GitHub API 403` | limit API 5000/h | poczekaj do resetu (godzina) |
| `QuotaExceeded` | przekroczony `real_quota` | `ghdisk df --honest`, `ghdisk gc`, albo podnieś `GHDISK_REAL_QUOTA` |
| `df` pokazuje 1024P, zapis zawodzi | to jest zamierzone | patrz [LIMITS.md](LIMITS.md) |
| `Transport endpoint is not connected` | proces `ghdisk mount` został ubity bez odmontowania | `sudo umount -l ~/ghdisk` (lazy), potem zamontuj ponownie |
| `fusermount: failed to unmount` | to samo, zawieszony wpis w tablicy montowań | `sudo umount -l ~/ghdisk` lub restart |
| Zapis bardzo wolny | GitHub API ~1–5 MB/s | normalne; to archiwum, nie dysk roboczy |

### Diagnostyka

```bash
ghdisk info                 # konfiguracja i dostępne kodeki
ghdisk df --honest          # realne zajęcie
ghdisk bench --size 32      # zmierz kompresję i prędkość
python3 -m pytest -q        # testy (19)
```

---

## Deinstalacja

```bash
fusermount -u ~/ghdisk
pip uninstall ghdisk
rm -rf ~/.config/ghdisk ~/.local/share/ghdisk
```

Dane w repozytorium GitHub pozostają — usuń repo ręcznie, jeśli nie są potrzebne.
