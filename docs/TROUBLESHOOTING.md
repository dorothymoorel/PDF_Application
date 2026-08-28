# Troubleshooting TransLoka

Mulai dari pemeriksaan paling kecil. Jangan menghapus database atau project
folder sebelum memastikan backup dan job aktif sudah ditangani.

## Setup script berhenti sebelum start

Jalankan:

```powershell
node --version
pnpm --version
uv --version
uv run python --version
Test-Path -LiteralPath node_modules
Test-Path -LiteralPath .venv
```

Nilai yang diharapkan: Node.js 24.x, pnpm 11.x, dan Python 3.12.x. Jika
`node_modules` atau `.venv` tidak ada, pasang dependency dengan:

```powershell
pnpm install --frozen-lockfile
uv sync --locked
```

Jika PowerShell masih menemukan versi lama setelah instalasi, buka PowerShell
baru dan ulangi pemeriksaan.

## Port 3000 atau 8000 sudah dipakai

Cari process yang mendengarkan port:

```powershell
Get-NetTCPConnection -State Listen -LocalPort 3000,8000 -ErrorAction SilentlyContinue |
    Select-Object LocalPort,OwningProcess
```

Jika process itu milik TransLoka sebelumnya, jalankan `.\scripts\stop.ps1`.
Jangan menghentikan process yang tidak dikenali secara membabi buta. Port API
dan web harus tetap loopback; jangan memindahkan service ke public bind.

## `start.ps1` mengatakan process record sudah ada

Record tersebut dibuat untuk mencegah dua stack memakai data dan port yang sama.
Jalankan `.\scripts\stop.ps1` dari repository yang sama, lalu coba start
lagi. Jika process sudah mati tetapi record tetap ada, periksa process ID dan
file record yang disebut pesan script sebelum menghapus record secara manual.

## Web tidak terbuka

1. Pastikan `start.ps1` menampilkan process ID web, API, dan worker.
2. Buka `http://127.0.0.1:3000` secara langsung.
3. Periksa API dengan:

   ```powershell
   Invoke-RestMethod http://127.0.0.1:8000/health
   ```

4. Jika API sehat tetapi web gagal, lihat output process Next.js dan jalankan
   `pnpm --filter @transloka/web dev` hanya untuk diagnosis foreground.

## API tidak sehat atau `connection refused`

Periksa:

```powershell
Invoke-WebRequest http://127.0.0.1:8000/health
Get-Process | Where-Object { $_.ProcessName -match 'python|uvicorn' }
```

Pastikan `$env:TRANSLOKA_API_HOST` adalah `127.0.0.1` atau `localhost`, dan
`$env:TRANSLOKA_API_PORT` adalah port yang sedang dibuka. Nilai public seperti
`0.0.0.0` sengaja ditolak oleh konfigurasi keamanan.

## Data root ditolak

`TRANSLOKA_DATA_DIR` harus:

- path absolut;
- berada di luar repository Git;
- bukan root drive, home directory, folder sistem, atau network share;
- tidak mengandung `..`;
- dapat dibuat dan ditulis oleh akun Windows saat ini.

Contoh aman:

```powershell
$env:TRANSLOKA_DATA_DIR = "C:\Users\<user>\TransLokaData"
```

Jika environment diubah, hentikan dan start ulang API agar settings baru
dibaca. Jangan memakai `F:\PDF_Application\transloka-data` sebagai data root.

## Database belum siap atau migration gagal

Hentikan stack TransLoka terlebih dahulu, lalu jalankan preparation-only pada
PowerShell yang memiliki `TRANSLOKA_DATA_DIR` yang benar:

```powershell
.\scripts\stop.ps1
.\scripts\start.ps1 -PrepareOnly
uv run transloka db integrity-check
```

Hasil yang diharapkan adalah `Database schema is current` dan seluruh integrity
check berstatus `PASS`. Mode normal menjalankan migration yang sama sebelum web,
API, atau worker dimulai. Jika migration gagal, jangan menghapus
`transloka.db`, jangan menjalankan `create_all`, dan jangan mengubah
`alembic_version` secara manual. Simpan database serta backup yang ada, lalu
catat pesan error sebelum melakukan recovery.

## Upload PDF ditolak

Periksa hal berikut:

1. file benar-benar PDF dan memiliki ekstensi `.pdf`;
2. nama file tidak mengandung path atau karakter path;
3. file tidak kosong dan tidak melebihi batas upload (default 200 MB);
4. ruang disk data root mencukupi;
5. project masih ada dan bukan dalam state deletion;
6. API health tetap `ok` selama upload.

Pesan seperti `Choose a PDF file`, `FILE_TOO_LARGE`, atau
`UPLOAD_INTERRUPTED` menunjukkan input/transport, bukan alasan untuk
mengunggah ulang tanpa memeriksa file.

## Upload berhasil tetapi thumbnail belum ada

Upload pertama kali berstatus staged/queued dan analisis dapat berjalan di
worker. Periksa process worker dan refresh project setelah beberapa saat. Jika
status tidak bergerak:

```powershell
Get-Process | Where-Object { $_.ProcessName -match 'python|uv' }
```

Jangan menghapus folder `temp` saat job masih aktif. Jika worker berhenti,
gunakan recovery/retry yang disediakan setelah aplikasi dijalankan kembali.

## Ollama tidak tersedia

Jalankan pada komputer yang sama:

```powershell
ollama serve
ollama list
Invoke-RestMethod http://127.0.0.1:11434/api/version
```

Jika URL dikonfigurasi ke host remote, provider akan menolaknya. Set kembali:

```powershell
$env:TRANSLOKA_OLLAMA_URL = "http://127.0.0.1:11434"
```

Lalu restart API. Model yang belum terpasang tidak diunduh otomatis; gunakan
`ollama pull <model-id>` secara eksplisit setelah meninjau lisensinya.

## Model tidak muncul atau benchmark gagal

1. Pastikan Ollama health tersedia.
2. Jalankan `ollama list` dan catat nama model persis.
3. Refresh daftar model dari fitur model/API bila tersedia.
4. Pastikan model berstatus installed.
5. Jalankan benchmark dengan batch kecil dan temperature deterministik.

Kode umum:

- `OLLAMA_UNAVAILABLE`: service lokal tidak dapat dijangkau;
- `MODEL_NOT_INSTALLED`: model id tidak ada di Ollama;
- `PLACEHOLDER_MISMATCH`: model tidak mempertahankan placeholder;
- `INVALID_JSON` atau `SCHEMA_VALIDATION_FAILED`: output model bukan structured output yang sah.

Benchmark hanya membantu memilih model untuk hardware saat ini. Jangan
membandingkan hasil dari komputer berbeda sebagai ranking universal.

## OCR kosong atau confidence rendah

Pastikan halaman memang scanned, renderer/OCR runtime tersedia, dan bahasa OCR
sesuai. Confidence rendah bukan berarti raw OCR boleh dihapus. Bandingkan
gambar halaman dengan raw OCR, lalu simpan correction pada resolved source.

## Translation berhenti, dibatalkan, atau perlu retry

Periksa status job dan pesan readiness terlebih dahulu. Penyebab umum:

- model belum dipilih atau tidak terpasang;
- Ollama berhenti;
- worker tidak berjalan;
- glossary/protected content belum valid;
- batch terlalu besar untuk RAM yang tersedia.

Batalkan hanya jika perlu. Setelah worker hidup kembali, gunakan retry pada job
yang memang retryable dan pertahankan idempotency key yang dibuat aplikasi.

## Export diblokir oleh warning

Critical warning, clipping, overflow, collision, atau link/resource error dapat
memblokir export. Buka warning terkait, perbaiki source/translation/layout,
jalankan preview ulang, dan validasi kembali. Jangan memaksa export dengan
menghapus warning dari database.

## Restore atau maintenance tidak berjalan

Restore memakai maintenance mode dan dapat membuat pre-restore backup. Tunggu
job aktif selesai, pastikan archive dapat diverifikasi, dan gunakan konfirmasi
exact `RESTORE` hanya ketika backup serta target sudah diperiksa. Jika restore
gagal, jangan menghapus pre-restore backup; gunakan untuk rollback atau minta
review manual.

## Masih gagal

Kumpulkan informasi yang tidak sensitif:

```powershell
git status --short
uv run python --version
node --version
pnpm --version
uv --version
Invoke-RestMethod http://127.0.0.1:8000/health
```

Jangan mengirim PDF, database, backup, token, password, atau isi log yang
memuat dokumen privat. Sertakan pesan error dan langkah reproduksi minimal.
