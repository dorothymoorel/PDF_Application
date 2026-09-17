# Panduan Pengguna TransLoka

TransLoka adalah workspace lokal untuk satu pengguna. Alur utama yang
ditargetkan adalah:

```text
buat proyek → pilih PDF → analisis → OCR/extraction → review →
terjemahan lokal → reconstruction → validasi → export
```

Gunakan [docs/LIMITATIONS.md](LIMITATIONS.md) untuk membedakan alur yang sudah
terlihat di web saat ini dari komponen yang masih bertahap.

## 1. Buka workspace

1. Jalankan `.\scripts\start.ps1` dari PowerShell.
2. Buka `http://127.0.0.1:3000`.
3. Pastikan halaman **Projects** tampil. Jika gagal, ikuti
   [Troubleshooting](TROUBLESHOOTING.md).

## 2. Buat proyek

Pada **Create project**:

1. isi **Project name**;
2. isi **Description** bila perlu;
3. biarkan **Source language** `English`;
4. biarkan **Target language** `Indonesian`;
5. pilih **Document type** yang paling dekat dengan PDF;
6. pilih **Translation style**: Professional, Academic, Natural, atau Literal;
7. pilih **Reconstruction mode**: Hybrid, Reflow, atau Overlay;
8. pilih **Create project**.

Project card menampilkan status, progress, pasangan bahasa, tipe dokumen, dan
waktu update. Gunakan **Archive** untuk menyembunyikan proyek aktif tanpa
menghapusnya. Gunakan **Restore** pada bagian archived untuk mengaktifkannya
kembali.

## 3. Import PDF

1. Buka project card yang baru dibuat.
2. Pada **Select source PDF**, pilih satu file PDF berbahasa Inggris.
3. Pastikan nama file hanya nama file, bukan path lokal.
4. Pilih **Upload PDF** dan tunggu progress mencapai 100%.

Browser hanya menerima file dengan ekstensi `.pdf` dan MIME PDF. Backend lokal
memeriksa metadata, magic bytes, ukuran, dan ruang penyimpanan sebelum staging.
Upload menggunakan endpoint lokal dan tidak mengirim file ke cloud.

Setelah upload, panel overview menampilkan nama file, ukuran, status analisis,
dan jumlah halaman jika sudah tersedia. Thumbnail akan muncul setelah analisis
lokal selesai. PDF asli disimpan terpisah dari hasil dan tidak ditimpa.

## 4. Analisis dan preview

Tunggu status analisis berubah dari pending/staged ke status terminal. Jika
thumbnail belum muncul, jangan mengunggah ulang berkali-kali; periksa status
API dan worker terlebih dahulu.

Untuk setiap halaman, analisis membedakan halaman digital, scanned, atau hybrid.
Halaman digital menggunakan extraction; halaman scanned dapat diarahkan ke OCR.
Preview dan thumbnail adalah salinan turunan. Sumber asli tetap immutable.

## 5. OCR dan koreksi sumber

OCR yang berhasil mengisi block dan segmen sumber untuk halaman yang belum
memiliki block. Halaman kosong tidak diberi segmen buatan. Hasil mentah tetap
immutable, dan segmen ber-confidence rendah ditandai untuk review.
Artefak raw menyimpan teks provider asli; teks OCR pada segmen dan panel review
merupakan potongan hasil normalisasi, sehingga spasi dan pemisahan kalimat
dapat berbeda. Penandaan review tidak otomatis menyetujui hasil OCR.

Mengulang OCR tidak menggandakan atau menimpa block yang sudah ada, termasuk
extraction digital, correction, dan terjemahan yang sudah direview. Hasil raw
dari job baru tetap disimpan; gunakan koreksi resolved source untuk perubahan
pada segmen yang sudah ada.

Pada halaman yang membutuhkan OCR:

1. bandingkan gambar halaman dengan **Raw OCR**;
2. periksa confidence dan warning;
3. edit hanya **resolved source**, bukan raw OCR;
4. simpan correction;
5. ulangi review untuk segmen ber-confidence rendah.

Raw OCR dipertahankan untuk audit. Correction dapat membuat revision baru dan
membatalkan terjemahan yang bergantung pada source lama; terjemahkan ulang
setelah koreksi jika UI memberi peringatan tersebut.

## 6. Glossary dan review

Sebelum translation, tinjau istilah kandidat dan glossary proyek bila panelnya
tersedia. Aturan glossary yang didukung mencakup `KEEP_ORIGINAL`, `TRANSLATE_AS`,
`ORIGINAL_THEN_TRANSLATION`, `TRANSLATION_THEN_ORIGINAL`,
`PRESERVE_ABBREVIATION`, dan `IGNORE`.

Terima hanya istilah yang memang ingin diterapkan. Placeholder, URL, angka,
kode, dan protected content tidak boleh diedit secara manual di output model.

## 7. Translation lokal

1. Pilih provider lokal pada panel **Translation setup**:
   - **Ollama (local)** memerlukan service loopback dan model terpasang;
   - **CTranslate2 (offline CPU)** memakai model tetap
     `opus-mt-en-id-ct2-int8` yang sudah diprovision pada API dan worker.
2. Untuk Ollama, pastikan service aktif pada `http://127.0.0.1:11434` dan
   model terpilih lulus health check. CT2 tidak memerlukan Ollama kecuali
   fallback lokal dikonfigurasi secara eksplisit.
3. Periksa translation readiness. CT2 hanya mendukung English → Indonesian.
4. Pilih scope: seluruh dokumen, untranslated only, unreviewed only, section,
   page, atau selected segments jika tersedia.
5. Pilih model, batch size, context mode, dan style.
6. Jalankan translation dan pantau job progress.

Translation menggunakan English → Indonesian, structured output, validasi
segment, glossary protection, placeholder integrity, retry, dan cancellation.
Semua output CT2 tetap review-required; status selesai bukan persetujuan
linguistik otomatis.
Jangan mematikan worker saat batch sedang menulis state kecuali memang ingin
menguji recovery.

## 8. Review hasil

Periksa segmen yang ditandai review-required, low confidence, terminology
conflict, overflow, clipping, atau collision. Simpan perubahan pengguna sebagai
reviewed translation. Jangan menimpa source text atau raw OCR.

Critical warning dapat memblokir export sampai diselesaikan. Jika translation
gagal, gunakan retry hanya setelah membaca error dan memastikan model masih
tersedia.

## 9. Reconstruction dan export

1. Pilih profile reconstruction yang sesuai dengan layout.
2. Gunakan preview satu halaman sebelum menjalankan job penuh.
3. Pilih **Start reconstruction** dan pantau progress.
4. Periksa warning layout, font, overflow, clipping, dan link.
5. Buat export hanya ketika validation lulus dan tidak ada critical warning.
6. Download PDF hasil ke lokasi terpisah dari PDF asli.

Mode umum:

- **Overlay** menjaga posisi tetap untuk halaman fixed-layout;
- **Reflow** memberi ruang lebih untuk teks yang memanjang;
- **Hybrid** memilih strategi per halaman/elemen.

Validasi output harus memastikan PDF dapat dibuka, teks hasil dapat dicari,
jumlah halaman masuk akal, gambar tetap ada, dan checksum PDF asli tidak berubah.

## 10. System health

Buka **System health** atau `http://127.0.0.1:3000/settings/system`.
Halaman ini memeriksa API dengan timeout dan menampilkan status frontend/API.
Status Worker, Database, Filesystem, Ollama, dan OCR dapat ditampilkan sebagai
belum diprobe pada milestone yang belum menghubungkan health probe. Gunakan
`http://127.0.0.1:8000/health` untuk pemeriksaan API langsung.

## 11. Menutup aplikasi

Selesaikan atau batalkan job aktif terlebih dahulu, lalu dari PowerShell lain:

```powershell
.\scripts\stop.ps1
```

Jangan menghapus `temp`, database, atau project folder untuk menghentikan
aplikasi. Gunakan prosedur cleanup/maintenance setelah memastikan tidak ada
restore atau job yang sedang berjalan.
