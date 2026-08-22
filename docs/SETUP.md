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

Jalankan web, API, dan worker:

```powershell
.\scripts\start.ps1
```

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

## 8. Jalankan quality checks

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

## 9. Layout data lokal

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
