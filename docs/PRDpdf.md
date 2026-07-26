# PRODUCT REQUIREMENTS DOCUMENT

## Aplikasi Penerjemah PDF dan Ebook Berbasis AI

**Working Title:** TransLoka  
**Document Version:** 0.1  
**Status:** Draft  
**Product Type:** Web Application  
**Bahasa Utama Antarmuka:** Bahasa Indonesia  
**Bahasa Terjemahan Awal:** English → Bahasa Indonesia  
**Target Platform Awal:** Desktop Web dan Mobile Web Responsive

---

# 1. Ringkasan Produk

TransLoka adalah aplikasi berbasis AI untuk menerjemahkan dokumen PDF dan ebook dari bahasa Inggris ke bahasa Indonesia dengan mempertahankan struktur, format, gambar, tabel, nomor halaman, heading, catatan kaki, hyperlink, dan elemen visual dokumen sedekat mungkin dengan dokumen asli.

Aplikasi harus mampu mengenali istilah teknis atau istilah penting seperti:

- use case;
- workflow;
- framework;
- endpoint;
- deployment;
- machine learning;
- database;
- stakeholder;
- user interface;
- source code;
- nama produk;
- nama organisasi;
- singkatan;
- istilah akademik atau profesional tertentu.

Istilah tersebut dapat dipertahankan dalam bahasa aslinya berdasarkan glossary bawaan, glossary pengguna, konteks dokumen, atau keputusan pengguna ketika melakukan peninjauan terjemahan.

Produk tidak hanya menerjemahkan teks, tetapi juga melakukan ekstraksi struktur, klasifikasi elemen dokumen, perlindungan istilah, penerjemahan kontekstual, validasi hasil, dan rekonstruksi dokumen.

---

# 2. Latar Belakang

Sebagian besar alat penerjemah dokumen memiliki satu atau beberapa kelemahan berikut:

1. Struktur PDF berubah setelah diterjemahkan.
2. Gambar, tabel, diagram, atau posisi elemen visual rusak.
3. Istilah teknis diterjemahkan secara harfiah dan menjadi tidak alami.
4. Heading, caption, footnote, daftar isi, dan nomor halaman tidak dikenali secara tepat.
5. Dokumen hasil terjemahan sulit diedit atau diperiksa.
6. Konteks antarhalaman dan antarbab tidak konsisten.
7. Nama tokoh, organisasi, teknologi, atau istilah khusus diterjemahkan secara tidak konsisten.
8. PDF hasil pemindaian tidak dapat diproses tanpa OCR.
9. Pengguna tidak mengetahui bagian mana yang diterjemahkan dengan tingkat keyakinan rendah.
10. Dokumen berukuran besar harus diterjemahkan secara manual per bagian.

TransLoka dirancang untuk menyelesaikan masalah tersebut dengan pendekatan document-aware translation dan layout-preserving reconstruction.

---

# 3. Visi Produk

Menjadi platform penerjemahan dokumen yang mampu menghasilkan terjemahan bahasa Indonesia yang natural, akurat, konsisten, dan tetap mempertahankan pengalaman membaca serta struktur visual dokumen asli.

---

# 4. Tujuan Produk

## 4.1 Tujuan Utama

1. Menerjemahkan PDF dan ebook dari bahasa Inggris ke bahasa Indonesia.
2. Mempertahankan layout dan struktur dokumen sedekat mungkin dengan file asli.
3. Mempertahankan istilah penting yang tidak seharusnya diterjemahkan.
4. Menghasilkan terjemahan yang natural dan sesuai konteks, bukan sekadar terjemahan kata per kata.
5. Menyediakan sistem review dan editing sebelum dokumen diekspor.
6. Memungkinkan pengguna mengatur glossary sendiri.
7. Mendukung dokumen digital maupun dokumen hasil pemindaian.
8. Menghasilkan file yang dapat dibaca, dicari, disalin, dan diunduh.

## 4.2 Tujuan MVP

MVP harus mampu:

- menerima file PDF;
- mendeteksi PDF digital atau hasil pemindaian;
- mengekstrak teks dan struktur dasar;
- mempertahankan gambar dari dokumen asli;
- menerjemahkan teks bahasa Inggris ke bahasa Indonesia;
- melindungi istilah dalam glossary;
- mempertahankan heading, paragraf, list, tabel dasar, dan urutan halaman;
- menampilkan perbandingan teks asli dan terjemahan;
- memungkinkan koreksi manual;
- mengekspor hasil sebagai PDF;
- menyimpan riwayat proyek terjemahan.

---

# 5. Sasaran Pengguna

## 5.1 Mahasiswa dan Akademisi

Kebutuhan:

- menerjemahkan jurnal;
- menerjemahkan ebook akademik;
- menerjemahkan materi penelitian;
- mempertahankan istilah ilmiah;
- mempertahankan tabel, referensi, citation, dan footnote.

## 5.2 Profesional

Kebutuhan:

- menerjemahkan manual;
- menerjemahkan laporan;
- menerjemahkan proposal;
- menerjemahkan dokumentasi teknis;
- mempertahankan istilah bisnis dan teknologi.

## 5.3 Pembaca Ebook

Kebutuhan:

- membaca buku berbahasa Inggris dalam bahasa Indonesia;
- mempertahankan nama tokoh, lokasi, organisasi, dan istilah khusus;
- memperoleh hasil yang nyaman dibaca;
- mempertahankan bab dan struktur ebook.

## 5.4 Penerjemah dan Editor

Kebutuhan:

- membuat draft terjemahan awal;
- memeriksa teks asli dan hasil terjemahan secara berdampingan;
- menggunakan glossary khusus;
- mengedit hasil sebelum ekspor;
- menjaga konsistensi istilah dalam dokumen panjang.

## 5.5 Perusahaan dan Organisasi

Kebutuhan:

- menerjemahkan dokumen internal;
- mengelola glossary organisasi;
- menjaga kerahasiaan dokumen;
- memproses banyak dokumen;
- mengatur akses anggota tim.

---

# 6. Permasalahan Pengguna

Pengguna membutuhkan cara untuk menerjemahkan dokumen panjang tanpa:

- menyalin teks halaman demi halaman;
- kehilangan gambar dan tabel;
- merusak format dokumen;
- menerjemahkan istilah teknis secara keliru;
- melakukan koreksi istilah yang sama berulang kali;
- kehilangan konsistensi terjemahan antarhalaman;
- membangun ulang dokumen secara manual;
- mengunggah bagian dokumen secara terpisah;
- membaca hasil terjemahan yang kaku dan terlalu literal.

---

# 7. Nilai Utama Produk

## 7.1 Layout Preservation

Sistem mempertahankan:

- ukuran halaman;
- orientasi halaman;
- posisi paragraf;
- heading;
- gambar;
- tabel;
- diagram;
- caption;
- header dan footer;
- nomor halaman;
- hyperlink;
- daftar isi;
- footnote dan endnote;
- pemisahan bab;
- style teks seperti bold, italic, dan underline.

## 7.2 Protected Terminology

Pengguna dapat menentukan istilah yang harus:

- tidak diterjemahkan;
- selalu diterjemahkan dengan padanan tertentu;
- ditampilkan bersama istilah aslinya;
- dipertahankan hanya pada konteks tertentu;
- diperlakukan sebagai nama khusus.

Contoh:

| Istilah Asli | Aturan |
|---|---|
| workflow | Jangan diterjemahkan |
| use case | Jangan diterjemahkan |
| deployment | Jangan diterjemahkan |
| stakeholder | Terjemahkan menjadi “pemangku kepentingan” |
| machine learning | Pertahankan sebagai “machine learning” |
| user interface | Terjemahkan menjadi “antarmuka pengguna” |
| API | Jangan diterjemahkan atau diperluas |
| OpenAI | Perlakukan sebagai nama produk |

## 7.3 Context-Aware Translation

Terjemahan harus mempertimbangkan:

- konteks paragraf;
- konteks halaman;
- konteks bab;
- jenis dokumen;
- domain dokumen;
- glossary;
- gaya bahasa;
- hubungan antara kalimat;
- penggunaan istilah pada bagian sebelumnya.

## 7.4 Human Review

Pengguna tetap memiliki kontrol terhadap:

- istilah;
- gaya bahasa;
- paragraf;
- heading;
- hasil OCR;
- tata letak;
- bagian yang tidak perlu diterjemahkan.

---

# 8. Ruang Lingkup Produk

## 8.1 Termasuk dalam MVP

- Upload PDF.
- PDF digital dan scanned PDF.
- OCR bahasa Inggris.
- Terjemahan Inggris ke Indonesia.
- Deteksi teks, heading, paragraf, list, dan tabel dasar.
- Ekstraksi serta penyimpanan gambar asli.
- Glossary pribadi.
- Deteksi istilah teknis.
- Side-by-side editor.
- Confidence indicator.
- Pencarian teks.
- Replace istilah secara global.
- Preview hasil.
- Ekspor PDF.
- Riwayat proyek.
- Sistem akun pengguna.
- Pembatasan ukuran dan jumlah halaman berdasarkan paket.

## 8.2 Setelah MVP

- Dukungan EPUB.
- Dukungan DOCX.
- Dukungan MOBI atau AZW melalui konversi yang diizinkan.
- Terjemahan Indonesia ke Inggris.
- Bahasa tambahan.
- Shared glossary untuk tim.
- Kolaborasi editor.
- Translation memory.
- Batch translation.
- API untuk perusahaan.
- Desktop application.
- Integrasi Google Drive dan Dropbox.
- Ekspor DOCX dan EPUB.
- Terjemahan teks di dalam gambar sebagai fitur opsional.
- Mode offline atau private deployment.
- Text-to-speech hasil terjemahan.

## 8.3 Tidak Termasuk dalam MVP

- Menghapus DRM ebook.
- Menerjemahkan file yang terkunci tanpa izin.
- Mengubah atau menggambar ulang ilustrasi.
- Mengubah teks yang menyatu di dalam gambar.
- Menjamin layout identik 100% untuk semua jenis PDF.
- Menerjemahkan tulisan tangan dengan akurasi penuh.
- Menerjemahkan rumus matematika.
- Mengubah kode program di dalam dokumen.
- Menerjemahkan dokumen yang melanggar hak cipta atau hukum.

---

# 9. Alur Pengguna Utama

## 9.1 Membuat Proyek Terjemahan

1. Pengguna login.
2. Pengguna memilih “Buat Terjemahan Baru”.
3. Pengguna mengunggah file PDF.
4. Sistem melakukan validasi file.
5. Sistem memeriksa apakah PDF berupa:
   - PDF digital;
   - scanned PDF;
   - PDF campuran.
6. Sistem menampilkan hasil deteksi dokumen.
7. Pengguna memilih pengaturan terjemahan.
8. Sistem menganalisis struktur dokumen.
9. Sistem menampilkan glossary yang disarankan.
10. Pengguna mengonfirmasi istilah yang harus dipertahankan.
11. Sistem memproses terjemahan.
12. Pengguna meninjau hasil.
13. Pengguna melakukan koreksi.
14. Pengguna mengekspor dokumen.

## 9.2 Pengaturan Sebelum Terjemahan

Pengguna dapat memilih:

- bahasa sumber;
- bahasa target;
- jenis dokumen;
- gaya terjemahan;
- tingkat formalitas;
- pertahankan istilah teknis;
- pertahankan kode program;
- pertahankan kutipan;
- pertahankan nama produk;
- pertahankan nama orang dan lokasi;
- aktifkan OCR;
- halaman yang akan diterjemahkan;
- glossary yang digunakan;
- apakah teks dalam tabel diterjemahkan;
- apakah caption gambar diterjemahkan;
- apakah header dan footer diterjemahkan;
- apakah daftar pustaka diterjemahkan.

## 9.3 Review Terjemahan

Editor menampilkan:

- halaman asli di sisi kiri;
- halaman terjemahan di sisi kanan;
- daftar segmen teks;
- istilah yang dipertahankan;
- bagian dengan confidence rendah;
- peringatan perubahan layout;
- kesalahan OCR;
- hasil validasi angka dan referensi.

---

# 10. Fitur Utama

## 10.1 Upload dan Validasi File

Sistem harus:

- menerima file PDF;
- memeriksa MIME type;
- memeriksa ekstensi;
- memeriksa file corrupt;
- memeriksa password protection;
- memeriksa jumlah halaman;
- memeriksa ukuran file;
- mendeteksi file berbahaya;
- menolak file yang tidak didukung;
- menampilkan estimasi kompleksitas dokumen.

Informasi yang ditampilkan:

- nama file;
- ukuran;
- jumlah halaman;
- jenis PDF;
- bahasa terdeteksi;
- jumlah gambar;
- jumlah tabel;
- perkiraan jumlah kata.

## 10.2 Document Structure Recognition

Sistem harus mengenali:

- title;
- subtitle;
- heading level 1–6;
- paragraf;
- blockquote;
- bullet list;
- numbered list;
- tabel;
- caption;
- header;
- footer;
- footnote;
- endnote;
- daftar isi;
- bibliography;
- code block;
- formula;
- textbox;
- gambar;
- diagram.

Setiap elemen diberi ID agar dapat direkonstruksi setelah terjemahan.

## 10.3 OCR Engine

OCR digunakan jika halaman tidak memiliki text layer yang dapat dibaca.

Sistem harus:

- mendeteksi orientasi halaman;
- memperbaiki rotasi;
- mendeteksi kolom;
- mengenali urutan baca;
- mengenali paragraf;
- mengenali heading;
- mengenali tabel sederhana;
- menyimpan bounding box setiap teks;
- menampilkan confidence OCR;
- memungkinkan pengguna memperbaiki teks OCR.

## 10.4 Translation Engine

Translation engine harus:

- menerjemahkan berdasarkan segmen;
- mempertahankan konteks antarsegmen;
- menggunakan konteks bab;
- menggunakan glossary;
- menjaga konsistensi istilah;
- menjaga angka, tanggal, satuan, URL, dan email;
- tidak menerjemahkan kode;
- tidak menerjemahkan identifier teknis;
- tidak mengubah referensi;
- tidak menghapus informasi;
- tidak menambahkan informasi yang tidak ada dalam sumber.

Sistem harus membedakan antara:

- teks naratif;
- teks teknis;
- kode;
- formula;
- istilah;
- nama khusus;
- citation;
- metadata;
- label diagram.

## 10.5 Terminology Protection Engine

Sumber glossary:

1. Glossary bawaan aplikasi.
2. Glossary khusus domain.
3. Glossary milik pengguna.
4. Istilah hasil deteksi otomatis.
5. Istilah yang pernah dikoreksi pengguna.
6. Nama khusus yang ditemukan dalam dokumen.

Aturan glossary:

- Keep Original.
- Translate As.
- Original + Translation.
- Translation + Original.
- Case Sensitive.
- Case Insensitive.
- Apply Globally.
- Apply to Current Project.
- Apply to Specific Chapter.
- Ignore Recommendation.

Contoh format:

`workflow → Keep Original`

`stakeholder → pemangku kepentingan`

`user journey → user journey`

`neural network → jaringan saraf (neural network)`

## 10.6 Automatic Term Detection

Sistem memberikan rekomendasi istilah berdasarkan:

- frekuensi kemunculan;
- kapitalisasi;
- singkatan;
- nama produk;
- istilah teknis;
- code formatting;
- konteks;
- kata yang tidak tersedia dalam kamus umum;
- penggunaan istilah secara konsisten di seluruh dokumen.

Pengguna harus dapat menerima atau menolak rekomendasi.

## 10.7 Layout Reconstruction

Sistem harus melakukan rekonstruksi berdasarkan elemen asli dan hasil terjemahan.

Prioritas:

1. Tidak kehilangan konten.
2. Tidak menutupi gambar atau elemen lain.
3. Mempertahankan urutan baca.
4. Mempertahankan hierarki heading.
5. Mempertahankan gambar.
6. Mempertahankan tabel.
7. Mempertahankan nomor halaman.
8. Mempertahankan kemiripan layout.

Karena bahasa Indonesia dapat memiliki panjang teks berbeda dari bahasa Inggris, sistem diperbolehkan:

- menyesuaikan line break;
- menyesuaikan tinggi textbox;
- menggeser elemen secara terbatas;
- menambahkan halaman jika diperlukan;
- mengurangi ukuran font dalam batas aman;
- melakukan reflow teks.

Sistem tidak boleh:

- memotong teks;
- membuat teks bertumpuk;
- menutupi gambar;
- menghilangkan halaman;
- menghapus tabel;
- mengubah urutan bab;
- mengubah isi gambar tanpa persetujuan pengguna.

## 10.8 Image Preservation

Gambar harus:

- diambil dari file asli;
- ditempatkan pada halaman hasil;
- mempertahankan aspect ratio;
- tidak dikompresi secara berlebihan;
- tidak diterjemahkan secara otomatis;
- tidak dimodifikasi secara visual.

Caption yang berada di luar gambar dapat diterjemahkan.

Teks yang menyatu dalam gambar tetap menggunakan bahasa asli pada MVP.

## 10.9 Table Preservation

Sistem harus:

- mendeteksi baris dan kolom;
- mempertahankan struktur tabel;
- menerjemahkan isi sel;
- mempertahankan angka;
- mempertahankan satuan;
- mempertahankan alignment jika memungkinkan;
- memberikan peringatan jika tabel terlalu kompleks.

## 10.10 Side-by-Side Editor

Editor harus menyediakan:

- tampilan halaman asli;
- tampilan halaman hasil;
- navigasi halaman;
- sinkronisasi scroll;
- pencarian;
- zoom;
- edit per segmen;
- undo dan redo;
- restore original;
- terjemahkan ulang segmen;
- lock segment;
- komentar;
- replace all;
- daftar warning;
- daftar istilah.

## 10.11 Quality Assurance

Sistem melakukan pemeriksaan otomatis terhadap:

- paragraf yang belum diterjemahkan;
- teks yang hilang;
- angka yang berubah;
- URL yang berubah;
- citation yang berubah;
- istilah yang tidak konsisten;
- halaman kosong;
- text overflow;
- font terlalu kecil;
- gambar hilang;
- tabel rusak;
- heading yang berubah tingkat;
- urutan halaman;
- segmen dengan confidence rendah.

## 10.12 Export

Format MVP:

- PDF hasil terjemahan;
- PDF bilingual opsional;
- file glossary CSV;
- laporan kualitas terjemahan.

Opsi PDF:

- Bahasa Indonesia saja.
- Halaman asli dan terjemahan berdampingan.
- Teks asli diikuti terjemahan.
- Watermark untuk paket gratis.
- Kompresi standar atau kualitas tinggi.

---

# 11. Persyaratan Fungsional

## FR-01 — Akun Pengguna

Pengguna dapat:

- mendaftar;
- login;
- logout;
- reset password;
- menghapus akun;
- melihat penggunaan paket.

## FR-02 — Manajemen Proyek

Pengguna dapat:

- membuat proyek;
- mengganti nama proyek;
- melihat status proses;
- membuka proyek;
- menghapus proyek;
- menduplikasi pengaturan proyek;
- mengunduh hasil.

## FR-03 — Upload File

Sistem menerima PDF sesuai batas paket pengguna.

## FR-04 — Analisis Dokumen

Sistem menganalisis bahasa, struktur, jumlah halaman, teks, gambar, dan tabel.

## FR-05 — OCR

Sistem menjalankan OCR pada halaman yang tidak memiliki text layer.

## FR-06 — Glossary

Pengguna dapat membuat, mengimpor, mengekspor, mengedit, dan menghapus istilah glossary.

## FR-07 — Terjemahan

Pengguna dapat memulai, menghentikan, melanjutkan, atau mengulang proses terjemahan.

## FR-08 — Review

Pengguna dapat membandingkan teks asli dan hasil terjemahan.

## FR-09 — Editing

Pengguna dapat memperbaiki hasil terjemahan secara manual.

## FR-10 — Quality Check

Sistem menampilkan warning sebelum dokumen diekspor.

## FR-11 — Export

Pengguna dapat mengekspor hasil ke PDF.

## FR-12 — Riwayat

Sistem menyimpan riwayat perubahan dan versi ekspor.

---

# 12. Persyaratan Nonfungsional

## 12.1 Performa

- Dashboard terbuka dalam waktu maksimal 3 detik pada koneksi normal.
- Progress proses harus diperbarui secara berkala.
- Dokumen diproses per halaman atau per batch agar kegagalan tidak mengulang seluruh proses.
- Proses dapat dilanjutkan setelah gangguan sistem.
- Preview halaman harus menggunakan lazy loading.

## 12.2 Keamanan

- File dienkripsi saat transit.
- File disimpan secara terenkripsi.
- URL file harus bersifat sementara.
- File pengguna tidak boleh digunakan untuk melatih model tanpa persetujuan eksplisit.
- Pengguna dapat menghapus file dan hasil secara permanen.
- Sistem harus memiliki malware scanning.
- Sistem harus mencatat aktivitas sensitif.
- Admin tidak boleh membaca dokumen pengguna tanpa alasan operasional dan otorisasi.

## 12.3 Privasi

Pengguna harus mengetahui:

- berapa lama file disimpan;
- siapa yang dapat mengakses file;
- layanan pihak ketiga yang digunakan;
- apakah data dikirim ke penyedia AI;
- cara menghapus data;
- kebijakan penggunaan data.

## 12.4 Reliabilitas

- Proses harus memiliki retry mechanism.
- Status pekerjaan tidak boleh hilang.
- File asli tidak boleh dimodifikasi.
- Sistem menyimpan checksum file.
- Kegagalan satu halaman tidak boleh menggagalkan seluruh dokumen.

## 12.5 Skalabilitas

Sistem harus mendukung pemrosesan asynchronous melalui job queue dan dapat menambah worker berdasarkan jumlah pekerjaan.

## 12.6 Kompatibilitas

Aplikasi mendukung versi terbaru:

- Google Chrome;
- Microsoft Edge;
- Mozilla Firefox;
- Safari.

---

# 13. Status Pemrosesan

Setiap proyek memiliki salah satu status berikut:

- Uploaded;
- Validating;
- Analyzing;
- Waiting for Settings;
- Extracting;
- Running OCR;
- Detecting Terms;
- Waiting for Glossary Confirmation;
- Translating;
- Reconstructing;
- Running Quality Check;
- Ready for Review;
- Exporting;
- Completed;
- Partially Completed;
- Failed;
- Cancelled.

---

# 14. Penanganan Kesalahan

Sistem harus menampilkan pesan yang jelas untuk:

- file terlalu besar;
- jumlah halaman melebihi paket;
- PDF rusak;
- PDF dilindungi password;
- bahasa sumber tidak didukung;
- OCR gagal;
- tabel tidak dapat direkonstruksi;
- font tidak tersedia;
- koneksi terputus;
- proses terjemahan gagal;
- halaman tertentu tidak dapat diproses;
- saldo atau kuota tidak mencukupi.

Sistem tidak boleh hanya menampilkan pesan umum seperti “Terjadi kesalahan”.

---

# 15. Aturan Terjemahan

1. Isi tidak boleh diringkas.
2. Isi tidak boleh diperluas.
3. Informasi baru tidak boleh ditambahkan.
4. Angka harus dipertahankan.
5. Nama orang tidak diterjemahkan.
6. Nama produk tidak diterjemahkan.
7. URL dan alamat email tidak diubah.
8. Citation tidak diubah.
9. Kode program tidak diterjemahkan.
10. Nama fungsi dan variabel tidak diterjemahkan.
11. Formula tidak diterjemahkan.
12. Istilah glossary mengikuti aturan pengguna.
13. Istilah yang ambigu ditandai untuk ditinjau.
14. Gaya bahasa mengikuti jenis dokumen.
15. Istilah yang sama harus diterjemahkan secara konsisten.
16. Terjemahan harus mengikuti Ejaan Bahasa Indonesia yang berlaku, kecuali istilah yang sengaja dipertahankan.
17. Sistem harus menjaga hubungan antara paragraf sebelum dan sesudahnya.

---

# 16. Mode Gaya Terjemahan

## Akademik

- formal;
- objektif;
- mempertahankan istilah ilmiah;
- mempertahankan citation;
- tidak menggunakan bahasa percakapan.

## Profesional

- formal dan jelas;
- cocok untuk laporan, manual, dan dokumen perusahaan;
- mempertahankan terminologi industri.

## Natural

- mengutamakan keterbacaan;
- tidak terlalu literal;
- tetap menjaga makna asli.

## Literal

- mempertahankan struktur kalimat sedekat mungkin;
- digunakan untuk pemeriksaan atau pembelajaran bahasa.

## Sastra

- menjaga tone, emosi, dialog, dan gaya penulis;
- tidak menerjemahkan nama khusus tanpa aturan glossary;
- mempertahankan pembagian bab dan paragraf.

---

# 17. Hak Cipta dan Penggunaan yang Diizinkan

Pengguna harus menyatakan bahwa:

- memiliki hak atas dokumen;
- mendapatkan izin untuk menerjemahkan dokumen;
- menggunakan dokumen untuk penggunaan yang diizinkan;
- tidak mengunggah konten ilegal;
- tidak menggunakan aplikasi untuk mendistribusikan hasil terjemahan secara melanggar hukum.

Sistem tidak boleh menyediakan fitur penghapusan DRM.

Untuk karya berhak cipta, aplikasi berfungsi sebagai alat pemrosesan dokumen milik pengguna dan tidak memberikan kepemilikan atau hak distribusi terhadap karya tersebut.

---

# 18. Model Monetisasi Awal

## Free

- jumlah halaman terbatas;
- ukuran file terbatas;
- antrean standar;
- watermark pada hasil;
- penyimpanan proyek terbatas;
- iklan;
- glossary dasar.

## Pro

- batas halaman lebih tinggi;
- tanpa watermark;
- tanpa iklan;
- prioritas pemrosesan;
- glossary tidak terbatas;
- ekspor kualitas tinggi;
- penyimpanan lebih lama;
- quality report lengkap.

## Pay As You Go

Pengguna membeli kredit berdasarkan:

- jumlah halaman;
- jumlah kata;
- penggunaan OCR;
- tingkat kompleksitas layout;
- kualitas model terjemahan.

## Business

- workspace tim;
- shared glossary;
- role dan permission;
- private processing;
- retention policy;
- audit log;
- volume pricing;
- API access.

---

# 19. Metrik Keberhasilan

## Product Metrics

- jumlah pengguna terdaftar;
- jumlah dokumen diunggah;
- jumlah dokumen selesai diterjemahkan;
- completion rate;
- export rate;
- pengguna aktif bulanan;
- conversion rate Free ke Pro;
- repeat usage rate;
- jumlah halaman diproses.

## Quality Metrics

- persentase teks yang berhasil diekstrak;
- OCR character accuracy;
- terminology consistency rate;
- missing text rate;
- layout warning rate;
- persentase gambar yang berhasil dipertahankan;
- persentase tabel yang berhasil direkonstruksi;
- jumlah koreksi manual per 1.000 kata;
- user-rated translation quality.

## Target Awal MVP

- minimal 95% teks digital berhasil diekstrak;
- minimal 98% gambar asli dipertahankan;
- tidak ada halaman yang hilang;
- tidak ada angka yang berubah tanpa warning;
- istilah glossary diterapkan dengan akurasi minimal 99%;
- minimal 80% dokumen standar dapat diekspor tanpa perbaikan layout mayor;
- minimal 70% pengguna menyelesaikan proses sampai ekspor.

---

# 20. Acceptance Criteria MVP

MVP dianggap memenuhi persyaratan apabila:

1. Pengguna dapat mengunggah PDF digital.
2. Pengguna dapat mengunggah scanned PDF.
3. Sistem dapat mendeteksi kebutuhan OCR.
4. Sistem dapat mengekstrak teks sesuai urutan baca.
5. Sistem mempertahankan seluruh gambar asli.
6. Sistem dapat menerjemahkan bahasa Inggris ke bahasa Indonesia.
7. Pengguna dapat memasukkan istilah yang tidak boleh diterjemahkan.
8. Sistem menerapkan glossary pada seluruh dokumen.
9. Heading dan paragraf tetap dapat dibedakan.
10. Urutan halaman tidak berubah.
11. Pengguna dapat melihat dokumen asli dan hasil terjemahan.
12. Pengguna dapat mengedit hasil.
13. Sistem mendeteksi teks yang belum diterjemahkan.
14. Sistem mendeteksi angka yang berubah.
15. Sistem mendeteksi text overflow.
16. Pengguna dapat mengekspor hasil sebagai PDF.
17. File hasil dapat dibuka menggunakan PDF reader standar.
18. File asli tidak dimodifikasi.
19. Pengguna dapat menghapus proyek.
20. Dokumen pengguna tidak digunakan untuk training tanpa persetujuan.

---

# 21. Edge Cases

Sistem harus mempertimbangkan:

- PDF dua atau tiga kolom;
- PDF dengan teks berputar;
- PDF dengan halaman berbeda ukuran;
- PDF yang sebagian berupa scan;
- PDF dengan font tertanam;
- PDF dengan font yang tidak tersedia;
- tabel melintasi beberapa halaman;
- footnote panjang;
- heading tanpa penomoran;
- teks di atas gambar;
- halaman hanya berisi gambar;
- code block;
- formula matematika;
- bahasa Inggris dan Indonesia dalam satu dokumen;
- dokumen dengan daftar pustaka;
- dokumen dengan nomor halaman Romawi;
- dokumen dengan hyperlink internal;
- teks hasil OCR yang memiliki banyak kesalahan;
- teks sangat kecil;
- karakter khusus;
- simbol ilmiah;
- diagram dengan label berbahasa Inggris;
- kata yang sama memiliki arti berbeda berdasarkan konteks.

---

# 22. Risiko Produk

## Risiko Layout

Terjemahan bahasa Indonesia dapat lebih panjang daripada bahasa Inggris sehingga menyebabkan overflow.

Mitigasi:

- dynamic text box;
- font adjustment terbatas;
- reflow;
- penambahan halaman;
- warning sebelum ekspor.

## Risiko Kualitas Terjemahan

AI dapat salah memahami istilah atau konteks.

Mitigasi:

- glossary;
- domain selection;
- chapter context;
- confidence score;
- human review;
- translation memory.

## Risiko OCR

Scan berkualitas rendah menghasilkan teks yang salah.

Mitigasi:

- image preprocessing;
- deskew;
- denoise;
- OCR confidence;
- manual correction.

## Risiko Biaya Infrastruktur

Dokumen panjang membutuhkan OCR, AI inference, dan penyimpanan besar.

Mitigasi:

- pemrosesan per halaman;
- caching;
- model routing;
- credit system;
- batas ukuran dan halaman;
- kompresi aset.

## Risiko Hak Cipta

Pengguna dapat mengunggah ebook tanpa izin.

Mitigasi:

- terms of service;
- user declaration;
- takedown process;
- larangan DRM removal;
- pembatasan sharing publik.

## Risiko Privasi

Dokumen dapat berisi data pribadi atau rahasia.

Mitigasi:

- encryption;
- retention control;
- permanent deletion;
- private processing option;
- tidak menggunakan data untuk training secara default.

---

# 23. Tahapan Pengembangan

## Phase 1 — Proof of Concept

Fokus:

- upload PDF;
- ekstraksi teks;
- ekstraksi gambar;
- terjemahan;
- glossary sederhana;
- pembuatan PDF hasil.

## Phase 2 — MVP

Fokus:

- OCR;
- analisis struktur;
- editor;
- quality check;
- riwayat proyek;
- akun;
- subscription;
- layout reconstruction.

## Phase 3 — Enhanced Translation

Fokus:

- EPUB;
- translation memory;
- terminology detection;
- domain glossary;
- collaborative review;
- ekspor DOCX dan EPUB.

## Phase 4 — Business Platform

Fokus:

- workspace;
- API;
- batch processing;
- private deployment;
- role management;
- shared glossary;
- audit log.

---

# 24. Prioritas Pengembangan MVP

## Must Have

- akun pengguna;
- upload PDF;
- ekstraksi teks;
- OCR;
- ekstraksi gambar;
- terjemahan Inggris–Indonesia;
- glossary;
- perlindungan istilah;
- editor;
- layout reconstruction;
- quality check dasar;
- ekspor PDF.

## Should Have

- deteksi tabel;
- confidence indicator;
- translate ulang per segmen;
- replace all;
- riwayat versi;
- pilihan gaya terjemahan.

## Could Have

- bilingual PDF;
- deteksi istilah otomatis;
- glossary domain;
- laporan kualitas;
- estimasi biaya sebelum proses.

## Won’t Have in MVP

- DRM removal;
- kolaborasi real-time;
- API publik;
- EPUB export;
- desktop application;
- terjemahan teks di dalam gambar;
- dukungan seluruh bahasa.

---

# 25. User Stories Utama

## US-01

Sebagai mahasiswa, saya ingin menerjemahkan jurnal berbahasa Inggris agar saya dapat membacanya dalam bahasa Indonesia tanpa kehilangan tabel dan referensi.

## US-02

Sebagai developer, saya ingin mempertahankan istilah seperti workflow, use case, deployment, API, dan source code agar dokumentasi tidak menjadi membingungkan.

## US-03

Sebagai pembaca ebook, saya ingin struktur bab dan gambar tetap sama agar pengalaman membaca tidak berubah.

## US-04

Sebagai penerjemah, saya ingin melihat teks asli dan terjemahan berdampingan agar dapat melakukan review secara efisien.

## US-05

Sebagai profesional, saya ingin membuat glossary khusus agar istilah perusahaan diterjemahkan secara konsisten.

## US-06

Sebagai pengguna, saya ingin mengetahui bagian yang memiliki confidence rendah agar saya dapat memeriksanya sebelum ekspor.

## US-07

Sebagai pengguna, saya ingin file asli tidak diubah agar saya selalu memiliki dokumen sumber yang aman.

---

# 26. Keputusan Produk Awal

1. Bahasa sumber MVP adalah bahasa Inggris.
2. Bahasa target MVP adalah bahasa Indonesia.
3. Format utama MVP adalah PDF.
4. EPUB masuk setelah MVP stabil.
5. Gambar dipertahankan tanpa diterjemahkan.
6. Caption di luar gambar dapat diterjemahkan.
7. Istilah teknis dapat dikunci melalui glossary.
8. Pengguna wajib melakukan review sebelum ekspor final.
9. Sistem memprioritaskan kelengkapan konten dibanding kemiripan layout absolut.
10. Rekonstruksi layout bersifat high-fidelity, bukan jaminan pixel-perfect.
11. File pengguna tidak digunakan untuk training secara default.
12. Penghapusan DRM tidak didukung.
13. Model monetisasi dapat menggunakan kombinasi langganan dan kredit halaman.
14. Pengguna Free dapat menerima iklan dan watermark.
15. Proses dokumen dilakukan sebagai pekerjaan terpisah per halaman atau batch agar lebih tahan terhadap kegagalan.

---

# 27. Definisi Selesai

Sebuah proyek terjemahan dinyatakan selesai apabila:

- seluruh halaman yang dipilih telah diproses;
- seluruh segmen memiliki status translated, protected, ignored, atau manually reviewed;
- tidak ada gambar yang hilang;
- tidak ada halaman yang hilang;
- tidak ada critical layout error;
- pemeriksaan angka dan URL selesai;
- glossary telah diterapkan;
- file hasil berhasil dibuat;
- file hasil dapat dibuka;
- pengguna dapat mengunduh hasil;
- status proyek berubah menjadi Completed.
