# Backup dan Restore

Backup TransLoka dapat berisi database, metadata proyek, PDF, OCR, intermediate
files, dan export. Perlakukan archive sebagai data privat dan simpan di media
yang dikontrol oleh akun OS.

## Jenis backup

Scope yang tersedia di model backup:

| Scope | Isi umum | Kapan digunakan |
| --- | --- | --- |
| `DATABASE_ONLY` | SQLite dan metadata database | pemulihan state database |
| `METADATA` | metadata proyek dan konfigurasi yang dipilih | snapshot ringan |
| `FULL_PROJECTS` | database terkait proyek dan file proyek | pemindahan/pemulihan proyek |
| `FULL_APPLICATION` | state aplikasi lokal yang termasuk manifest | disaster recovery lokal |
| `PRE_RESTORE` | snapshot otomatis sebelum restore | rollback jika restore gagal |

Isi aktual ditentukan oleh manifest. Jangan mengasumsikan database-only
mengandung PDF atau export.

## Lokasi dan privasi

Backup berada di subfolder `backups` pada data root, bukan di repository.
Data root Windows default adalah `%LOCALAPPDATA%\TransLoka` jika
`TRANSLOKA_DATA_DIR` tidak diatur. Jika menggunakan data root custom, catat
lokasinya dan pastikan backup ikut tercakup dalam rencana pencadangan OS.

Manifest menyimpan ukuran dan SHA-256 setiap file serta privacy warning. Jangan
menaruh archive pada folder publik, cloud sync, atau network share tanpa
persetujuan pemilik data.

## Sebelum membuat backup

1. Pastikan API dan worker sehat.
2. Tunggu upload, translation, reconstruction, export, atau maintenance aktif
   selesai; atau catat job yang memang ingin dipulihkan.
3. Pastikan ruang disk cukup untuk archive dan salinan sementara.
4. Pilih scope yang benar-benar diperlukan.
5. Jangan mengubah PDF asli sebelum checksum tercatat.

## Membuat dan memverifikasi backup

Jika panel **Backup and restore** tersedia di UI:

1. buka panel backup;
2. pilih **Backup scope**;
3. pilih **Create backup**;
4. tunggu job selesai dan catat backup ID serta ukuran;
5. pilih **Verify** pada backup yang selesai;
6. pastikan status verifikasi berhasil sebelum memindahkan archive.

Verifikasi membaca manifest, memastikan setiap file ada di bawah root archive,
lalu membandingkan ukuran dan checksum SHA-256. Backup yang belum diverifikasi
tidak boleh digunakan sebagai sumber restore.

Jika UI belum menampilkan panel tersebut, backup API tetap memerlukan endpoint
lokal dan idempotency key; gunakan OpenAPI lokal pada
`http://127.0.0.1:8000/docs` hanya untuk deployment lokal yang sudah diaktifkan.

## Restore yang aman

Restore mengganti state lokal dan karena itu merupakan operasi destruktif.
Urutan aman:

1. hentikan perubahan pengguna dan tunggu job aktif;
2. pastikan backup berstatus completed dan manifest sudah diverifikasi;
3. buat atau izinkan **pre-restore backup**;
4. mulai restore dari panel atau endpoint lokal;
5. konfirmasi exact string `RESTORE`;
6. pilih apakah file proyek ikut dipulihkan;
7. tunggu maintenance mode selesai;
8. jalankan health check, buka project, dan verifikasi export/checksum.

API restore menggunakan `POST /api/v1/backups/{backup_id}/restore` dan
mengharuskan header `Idempotency-Key` serta body berikut:

```json
{
  "confirmation": "RESTORE",
  "create_pre_restore_backup": true,
  "restore_files": true
}
```

Response memberi job ID, backup ID, backup type, dan pre-restore backup ID.
Jangan mengulang request dengan idempotency key berbeda hanya karena browser
belum memperbarui status.

## Saat restore berjalan

- API dapat menolak mutasi lain dengan status maintenance;
- health endpoint tetap boleh dibaca;
- jangan menghapus marker maintenance, database, atau archive secara manual;
- jangan mematikan process sebelum workflow menyelesaikan commit/rollback.

Restore memvalidasi path archive, zip slip, symlink, checksum, dan schema
manifest sebelum mengganti state. Jika validasi gagal, state aktif tidak boleh
diganti.

## Jika restore gagal

Restore membuat pre-restore backup sebelum mengganti state jika opsi default
dipertahankan. Simpan archive tersebut. Workflow berusaha melakukan rollback
otomatis jika langkah restore gagal; jika rollback juga gagal, hentikan aplikasi
dan lakukan review manual terhadap backup serta log tanpa menghapus bukti.

## Setelah restore

1. Jalankan `Invoke-RestMethod http://127.0.0.1:8000/health`.
2. Buka web dan pastikan project, revision, glossary, serta export yang
   diharapkan ada.
3. Verifikasi checksum file penting.
4. Pastikan PDF asli tetap immutable dan hasil export dapat dibuka.
5. Buat backup baru setelah state dinyatakan benar.

## Retensi dan pemindahan

Tidak ada sinkronisasi cloud otomatis. Tentukan sendiri retensi backup dengan
kebijakan OS, tetapi jangan menghapus backup yang masih menjadi satu-satunya
salinan atau pre-restore rollback point. Saat memindahkan archive, pertahankan
manifest dan jangan mengubah isi file di dalamnya.
