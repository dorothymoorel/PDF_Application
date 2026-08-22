# Batasan yang Diketahui

Dokumen ini sengaja eksplisit agar status Personal MVP tidak disalahartikan
sebagai produk multi-user atau layanan cloud.

## Batasan produk

- Personal MVP adalah single-user dan localhost-only.
- Tidak ada authentication, account, role reviewer, organization, atau
  collaboration.
- Tidak ada cloud database, cloud storage, remote AI provider, billing,
  subscription, atau advertisement.
- Tidak ada desktop installer atau Windows service.
- Format utama hanya PDF; DOCX, EPUB, MOBI, AZW, PPTX, XLSX, HTML website,
  image folder, CBZ, dan DJVU belum termasuk.
- Pasangan bahasa yang ditargetkan adalah English → Bahasa Indonesia.

## Status integrasi web saat ini

Navigasi web yang terlihat saat ini berfokus pada:

- project dashboard dan create/archive/restore project;
- upload PDF dan progress staging;
- overview/status analisis serta thumbnail ketika tersedia;
- system health untuk frontend dan API.

Komponen OCR review, glossary, translation settings/progress, reconstruction,
export, backup/restore, storage, warning, dan benchmark tersedia bertahap di
repository/API, tetapi belum semuanya terhubung ke navigasi utama pada runtime
Personal MVP saat ini. Jika panel atau endpoint belum muncul, jangan menganggap
fitur tersebut telah siap untuk operasi penuh.

## Dokumen dan layout

PDF digital, scanned, dan hybrid adalah target MVP, tetapi kualitas dapat turun
pada:

- scan buram, miring, atau beresolusi rendah;
- font langka atau embedded font yang tidak lengkap;
- layout dua kolom yang ambigu;
- tabel kompleks, formula, footnote padat, atau text expansion besar;
- active content, annotation, atau resource PDF yang tidak aman.

OCR tidak dijamin sempurna. Raw OCR dipertahankan dan correction manusia tetap
diperlukan. Complex table recreation dan text-in-image translation ditunda.

Reconstruction Overlay/Reflow/Hybrid berusaha menjaga geometry, gambar, link,
dan reading order; hasil tetap harus diperiksa manual sebelum distribusi.
Critical warning dapat memblokir export.

## Model dan resource

- Ollama harus berjalan lokal dan model harus dipasang pengguna secara eksplisit.
- Tidak ada model universal yang dijamin paling cepat atau paling natural.
- RAM, VRAM, CPU, GPU, quantization, context, batch, dan ukuran PDF sangat
  memengaruhi hasil.
- Model benchmark hanya valid untuk hardware dan settings yang dicatat pada
  report tersebut.
- Model license harus ditinjau terpisah dari license Ollama.
- Model output yang invalid, tidak menjaga placeholder, atau tidak menjaga
  segment ID tidak boleh disimpan sebagai successful translation.

## Data, backup, dan recovery

- Data root harus absolut dan berada di luar repository.
- PDF asli disimpan immutable dan tidak ditimpa export.
- Backup dapat memuat seluruh dokumen privat, OCR, database, dan export.
- Restore adalah operasi maintenance yang dapat mengganti state lokal; pre-restore
  backup dan manifest verification wajib dipertahankan.
- Tidak ada sinkronisasi cloud otomatis atau retensi backup universal.
- Aplikasi tidak menggantikan backup OS, antivirus, atau disaster-recovery plan.

## Privasi dan security boundary

- API, web, worker, SQLite, filesystem, OCR, dan Ollama dimaksudkan untuk satu
  komputer.
- Bind public/LAN tidak didukung dan endpoint Ollama remote diblokir.
- Tidak ada authentication karena OS account lokal menjadi trust boundary.
- Siapa pun yang dapat menjalankan akun Windows yang sama pada host dapat
  mengakses data root dan service lokal.
- Jangan membuka port ke internet, memasukkan dokumen rahasia ke test/benchmark,
  atau menyalin backup ke lokasi tanpa access control.
- Jangan memberikan filesystem, shell, network, database, atau deletion tools
  kepada model.

## Operasional

- Job berat berjalan melalui worker lokal dan dapat membutuhkan waktu lama untuk
  PDF besar.
- Concurrency Personal MVP sengaja rendah untuk menjaga resource.
- Stop/restart saat job aktif dapat meninggalkan pekerjaan yang perlu recovery;
  gunakan status, retry, dan maintenance flow.
- Health page saat ini dapat menampilkan komponen Worker, Database, Filesystem,
  Ollama, dan OCR sebagai `Not implemented` karena health probe komponen belum
  terhubung seluruhnya.
- Relative data root dari contoh environment bukan pengganti absolute path yang
  diwajibkan runtime.

## Di luar scope saat ini

Fitur berikut memerlukan keputusan scope baru sebelum dikerjakan:

- authentication dan multi-user;
- public/LAN deployment;
- cloud sync atau remote inference;
- desktop packaging/installer;
- DOCX/EPUB/PPTX/XLSX;
- real-time collaboration;
- automatic model download;
- universal quality/performance leaderboard;
- kompleks table recreation dan text-in-image translation.
