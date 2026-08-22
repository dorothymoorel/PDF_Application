# TransLoka

TransLoka adalah aplikasi lokal satu pengguna untuk menerjemahkan PDF berbahasa
Inggris ke Bahasa Indonesia. Data dokumen, database, cache, log, dan backup
tetap berada di komputer pengguna. Aplikasi tidak membutuhkan akun, database
cloud, atau layanan AI berbayar.

## Mulai cepat di Windows

Prasyarat dan langkah instalasi lengkap ada di [docs/SETUP.md](docs/SETUP.md).
Ringkasnya, dari PowerShell:

```powershell
pnpm install --frozen-lockfile
uv sync --locked
.\scripts\setup-local.ps1
.\scripts\start.ps1
```

Jika dependency belum terpasang, jalankan `pnpm install --frozen-lockfile` dan
`uv sync --locked` terlebih dahulu. Buka:

- Web: <http://127.0.0.1:3000>
- API health: <http://127.0.0.1:8000/health>
- FastAPI docs: <http://127.0.0.1:8000/docs>

Hentikan stack dari PowerShell lain:

```powershell
.\scripts\stop.ps1
```

`setup-local.ps1` hanya memeriksa Node.js 24, pnpm 11, uv, Python 3.12,
lockfile, dan dependency lokal. Script tersebut tidak memasang software.

## Apa yang tersedia sekarang

Navigasi web saat ini menyediakan:

1. membuat proyek dengan pasangan English → Indonesian;
2. memilih tipe dokumen, gaya terjemahan, dan mode reconstruction;
3. melihat proyek aktif atau terarsip;
4. mengarsipkan atau memulihkan proyek;
5. membuka proyek dan memilih PDF sumber;
6. mengunggah PDF ke API lokal dengan progress;
7. melihat status analisis dan thumbnail halaman setelah tersedia;
8. memeriksa API melalui halaman System health.

Komponen backend dan UI untuk OCR, review, glossary, translation, reconstruction,
export, backup, restore, dan benchmark tersedia bertahap. Status integrasi yang
belum muncul di navigasi utama dicatat di [docs/LIMITATIONS.md](docs/LIMITATIONS.md).

## Dokumen pengguna

- [Setup](docs/SETUP.md) — prasyarat, dependency, environment, start/stop.
- [User guide](docs/USER_GUIDE.md) — alur penggunaan Personal MVP.
- [Troubleshooting](docs/TROUBLESHOOTING.md) — diagnosis masalah umum.
- [Backup and restore](docs/BACKUP_AND_RESTORE.md) — backup, verifikasi, dan restore.
- [Model selection](docs/MODEL_SELECTION.md) — Ollama, model lokal, dan benchmark.
- [Limitations](docs/LIMITATIONS.md) — batasan, privasi, dan fitur yang ditunda.

## Batas keamanan penting

- Jalankan API hanya pada `127.0.0.1` atau `localhost`.
- Jangan mengubah bind address menjadi `0.0.0.0` dan jangan membuka port ke LAN.
- Gunakan data root absolut di luar repository.
- Endpoint Ollama remote diblokir; gunakan Ollama lokal saja.
- PDF asli disimpan terpisah dan tidak boleh ditimpa hasil terjemahan.
- Backup dapat berisi dokumen privat. Simpan dan pindahkan backup dengan kontrol akses OS.

## Pengembangan dan verifikasi

Perintah utama:

```powershell
uv run pytest
uv run ruff check .
uv run mypy .
pnpm lint
pnpm typecheck
pnpm test
pnpm build
```

Benchmark resource lokal:

```powershell
.\scripts\benchmark.ps1 --pages 10 50 100 250
```

Benchmark menggunakan provider fake dan temporary storage untuk mengukur
overhead pipeline. Hasil antar-hardware tidak boleh dibandingkan langsung.
