# Setup TransLoka

Panduan ini menyiapkan TransLoka untuk penggunaan lokal di Windows. Semua
perintah dijalankan dari PowerShell; jalur repository pada contoh adalah
`F:\PDF_Application`.

## 1. Prasyarat

Pasang dan pastikan perintah berikut dapat dipanggil dari PowerShell baru:

| Komponen | Versi yang diperiksa | Kegunaan |
| --- | --- | --- |
| Windows | Windows 10/11 | platform utama Personal MVP |
| Node.js | 24.x | Next.js web |
| pnpm | 11.x | dependency dan script JavaScript |
| Python | 3.12.x | API, worker, dan package Python |
| uv | versi yang mendukung lockfile | environment dan dependency Python |
| Ollama | versi lokal yang kompatibel | inference terjemahan, opsional saat smoke test |

Periksa versi:

```powershell
node --version
pnpm --version
uv --version
uv run python --version
ollama --version
```

Ollama diperlukan untuk menerjemahkan dengan model lokal. Instalasi dependency
dan test standar tidak mengunduh model Ollama secara diam-diam.

## 2. Masuk ke repository

```powershell
Set-Location -LiteralPath "F:\PDF_Application"
```

Jika repository berada di lokasi lain, gunakan lokasi aktual. Jangan gunakan
folder repository sebagai data root aplikasi.

## 3. Pasang dependency terkunci

```powershell
pnpm install --frozen-lockfile
uv sync --locked
```

`--frozen-lockfile` dan `--locked` memastikan dependency mengikuti lockfile.
Jika perintah gagal karena tool belum ada, pasang tool tersebut lalu buka
PowerShell baru sebelum mencoba lagi.

## 4. Validasi setup

```powershell
.\scripts\setup-local.ps1
```

Script ini bersifat validasi. Script memeriksa versi Node.js/pnpm, file
workspace, `node_modules`, `.venv`, dan import package Python; script tidak
memasang dependency.

## 5. Environment lokal

`.env.example` adalah referensi nama variabel. Runtime membaca environment
process, jadi set variabel pada PowerShell yang akan menjalankan aplikasi.
Gunakan data root absolut dan di luar repository:

```powershell
$env:TRANSLOKA_DATA_DIR = "C:\Users\<user>\TransLokaData"
$env:TRANSLOKA_API_HOST = "127.0.0.1"
$env:TRANSLOKA_API_PORT = "8000"
$env:TRANSLOKA_WEB_ORIGINS = "http://127.0.0.1:3000,http://localhost:3000"
$env:TRANSLOKA_OLLAMA_URL = "http://127.0.0.1:11434"
$env:TRANSLOKA_LOG_LEVEL = "INFO"
$env:TRANSLOKA_DEBUG = "false"
```

`TRANSLOKA_DATA_DIR` harus absolut, tidak mengandung `..`, bukan root user,
bukan network share, dan tidak berada di dalam Git repository. Jika variabel
ini tidak diset pada Windows, default runtime adalah `%LOCALAPPDATA%\TransLoka`.

Environment hanya berlaku pada jendela PowerShell tersebut. Atur ulang setelah
membuka jendela baru. Jangan commit `.env` atau menyimpan secret di repository.

## 6. Jalankan aplikasi

Validasi tanpa menyalakan service:

```powershell
.\scripts\start.ps1 -CheckOnly
```

Siapkan atau perbarui schema database tanpa menyalakan service:

```powershell
.\scripts\start.ps1 -PrepareOnly
```

`-PrepareOnly` menjalankan pemeriksaan prerequisite lalu `alembic upgrade head`
pada data root yang aktif. Perintah ini aman diulang. Gunakan mode ini untuk
memastikan schema siap sebelum trial, diagnosis, atau menjalankan stack penuh.

Jalankan web, API, dan worker:

```powershell
.\scripts\start.ps1
```

Start normal selalu menjalankan migration sampai head sebelum menyalakan satu
pun component. Jika migration gagal, web, API, dan worker tidak dijalankan.

Script mencatat process ID milik TransLoka dan hanya mengelola process tersebut.
Buka browser:

- `http://127.0.0.1:3000` — Projects;
- `http://127.0.0.1:3000/settings/system` — System health;
- `http://127.0.0.1:8000/health` — health API sederhana;
- `http://127.0.0.1:8000/docs` — OpenAPI lokal.

Hentikan dari PowerShell lain pada repository yang sama:

```powershell
.\scripts\stop.ps1
```

Jangan menghentikan semua process Node atau Python secara global. `stop.ps1`
hanya memakai catatan process yang dibuat `start.ps1`.

### Tanpa PowerShell (Linux/macOS, CI, atau sandbox)

Script `.ps1` membutuhkan PowerShell dan Windows. Pada lingkungan tanpa
PowerShell, jalankan komponen yang sama secara manual dari root repository,
dengan `TRANSLOKA_DATA_DIR` absolut yang sudah di-set pada shell tersebut:

```bash
uv run --no-sync alembic upgrade head                     # migration sampai head
pnpm --filter @transloka/web dev --hostname 127.0.0.1 --port 3000   # web
uv run --no-sync transloka-api                            # API pada 127.0.0.1:8000
uv run --no-sync python -m transloka_worker               # local worker
```

Jalankan migration lebih dulu; jika gagal, jangan menyalakan komponen lain.
Web, API, dan worker masing-masing membutuhkan terminal sendiri, dan dihentikan
dengan `Ctrl+C` pada terminal tersebut (bukan dengan mematikan semua process
Node/Python). Backup restore memakai `fcntl` pada platform non-Windows dan
`msvcrt` pada Windows; keduanya tersedia bawaan Python.

## 7. Jalankan Ollama lokal

Jika Ollama belum berjalan, jalankan pada komputer yang sama:

```powershell
ollama serve
```

Pada jendela PowerShell lain, cek model:

```powershell
ollama list
```

Pasang model hanya setelah memilihnya secara sadar:

```powershell
ollama pull <model-id>
```

Gunakan `docs/MODEL_SELECTION.md` untuk health check, benchmark, dan review
license. Endpoint selain loopback ditolak oleh provider lokal.

## 8. Siapkan OCR lokal

OCR halaman scan memakai PaddleOCR CPU dan dua model bahasa Inggris lokal.
Paket Python terkunci dalam `uv.lock`, tetapi model tidak diunduh saat aplikasi
berjalan. Jalankan setup berikut secara eksplisit sekali sebelum OCR pertama:

```powershell
.\scripts\provision-ocr-models.ps1
```

Model disimpan di `<data-root>\cache\paddleocr\official_models`, di luar
repository. Untuk memakai data root lain, berikan path absolut:

```powershell
.\scripts\provision-ocr-models.ps1 -DataRoot "D:\TransLoka"
```

Setelah script selesai, mulai aplikasi dengan `scripts\start.ps1`. OCR tetap
memproses satu halaman per waktu pada CPU dan tidak mengunduh model saat job
OCR berjalan.

## 9. Jalankan quality checks

```powershell
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy .
pnpm lint
pnpm typecheck
pnpm test
pnpm build
```

Test standar memakai fake provider dan temporary data; test Ollama/PaddleOCR
lokal dapat membutuhkan runtime tambahan.

## 10. Layout data lokal

Runtime membuat subfolder berikut di bawah data root:

```text
database\   SQLite application database
projects\   PDF asli, page assets, OCR, intermediate, dan export
cache\      cache yang dapat dibersihkan
models\     metadata/cache model lokal bila digunakan
logs\       log aplikasi
backups\    arsip backup
temp\       file sementara dan lock/recovery artifacts
```

PDF dan backup dapat berukuran besar. Sisakan ruang disk yang cukup dan jangan
menghapus folder tersebut saat worker atau restore masih berjalan.
