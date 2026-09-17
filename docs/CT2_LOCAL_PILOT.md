# Pilot OPUS-MT lokal English → Indonesian

Pilot ini **opt-in**, bukan pengganti default Ollama. Inference CTranslate2
berjalan di CPU tanpa koneksi jaringan, Transformers, atau PyTorch. Model
ditujukan hanya untuk English → Indonesian; hasil tetap perlu review makna,
glossary, dan tata bahasa. Ini bukan bukti bahwa seluruh buku/PDF sudah selesai
diterjemahkan atau benchmark kualitas universal.

## Artifact yang disetujui

| Field | Pin |
| --- | --- |
| Model ID aplikasi | `opus-mt-en-id-ct2-int8` |
| Sumber | [`Helsinki-NLP/opus-mt-en-id`](https://huggingface.co/Helsinki-NLP/opus-mt-en-id/tree/6e4c52d61a6b16fe3509b0267cbfec65011b860b) |
| Revision sumber | `6e4c52d61a6b16fe3509b0267cbfec65011b860b` |
| Lisensi model | Apache-2.0 menurut model card pada revision tersebut |
| Quantization | CTranslate2 `int8` |
| Runtime | `ctranslate2==4.6.0`, `sentencepiece==0.2.1` |
| Konversi saja | `torch==2.8.0` (CPU di Linux/Windows), `transformers==4.56.2` |
| SHA-256 `pytorch_model.bin` sumber | `55cf1d883321cfd3bcfc43ce37fa842fc01690c7cb05afaff0fc9ca2df15f859` |
| SHA-256 `model.bin` hasil | `2b9dc8ce6b00b40a9f1b08457fe0c8abe83b116eb88be5049d26242a41624a1b` |

Pin lengkap semua file berada di
`python/transloka-translation/src/transloka_translation/providers/nmt_model.py`.
Ukuran bobot sumber sekitar 291 MB; hasil INT8 sekitar 74 MB, ditambah tokenizer
dan vocabulary. Provisioning sementara membutuhkan sumber dan hasil sekaligus;
dependency konversi memerlukan ruang tambahan. Konversi/checksum pilot
diverifikasi pada Linux x86_64, Python 3.12. Jangan menganggap checksum identik
di platform lain tanpa menjalankan verifikasi; script berhenti bila berbeda.

## Hasil pilot terverifikasi — 2026-09-09

Pilot memakai bundle lokal `runtime-v1` yang lulus verifikasi manifest dan
checksum di atas. Sampel 300 segmen dipilih lintas jenis halaman dan kelompok
panjang teks dengan seed tetap `4904`; batch adapter berisi 20 segmen. Hanya
agregat yang dicatat di sini, bukan teks dokumen atau hasil terjemahan privat.
Hasil pengukuran terbaru ini memakai provider yang memblokir seluruh 837 token
yang mengandung digit dalam shared vocabulary terverifikasi saat generasi.
Digit sumber tetap diisolasi dan dikembalikan utuh tanpa diterjemahkan; pembatasan tersebut mencegah
model menghasilkan digit baru dari bilangan sumber yang ditulis dengan kata.

| Pengukuran adapter nyata | Hasil |
| --- | --- |
| Segmen sampel / kata sumber | 300 / 4.669 |
| Output nonempty diterima untuk review | 300 dari 300 |
| Output ditolak / critical validation issues | 0 / 0 |
| Inventori digit terjaga pada segmen bernomor | 66 dari 66 |
| Warning semantik heuristik | 34 negation / 11 untranslated / 1 target-language |
| Waktu adapter setelah warm-up | 9,866 detik |
| Throughput kata sumber | 473,25 kata/detik |
| Estimasi linear seluruh korpus, adapter saja | 112,6 detik; **bukan hasil full-book run** |
| Peak RSS proses pilot | sekitar 349 MiB; bukan total RAM aplikasi |

Waktu adapter mencakup proteksi/penggabungan span internal, pemanggilan provider,
parsing, dan validasi pada sampel. Pengambilan segmen serta cold load/warm-up
berada di luar interval tersebut. Estimasi 112,6 detik tidak mencakup import,
extraction/OCR, antrean/worker, persistensi, retry, review manusia, reconstruction,
atau export PDF. Throughput dihitung dari seluruh kata sumber sampel;
angka ini bukan kecepatan menghasilkan terjemahan final yang sudah lolos review.
Estimasi bare inference bukan estimasi durasi produk.

**Seluruh buku belum diterjemahkan melalui jalur ini.** Sampel adapter bersifat
read-only terhadap data aplikasi, tidak menulis hasil ke database, dan tidak
memakai fallback. Diterimanya 300 output bukan skor akurasi makna atau bukti
kesiapan publikasi. Pemeriksaan angka membandingkan inventori digit, bukan
menilai makna, satuan, atau format angka. Masih terdapat 34 warning negation
dan 11 warning untranslated serta 1 target-language yang bersifat heuristik, bukan jumlah kesalahan
semantik yang dikonfirmasi. Semua output NMT wajib direview; nol critical issue
tidak berarti semua makna terjaga atau hasil boleh disetujui otomatis.

### Bukti integrasi yang terpisah

Uji nyata **API → queue → worker → SQLite** berhasil untuk **satu segmen
sintetis** dengan provider `CTRANSLATE2`: hasil tersimpan sebagai `NEEDS_REVIEW`,
angka dan URL terjaga, tanpa automatic approval, tanpa record model Ollama,
dan tanpa layanan cloud. Bukti ini memverifikasi jalur persistensi/provenance,
bukan UI, penerjemahan seluruh buku, atau fidelity PDF akhir. Regresi Python
final (`not slow and not requires_ollama and not requires_gpu`) mencatat
**1.851 passed, 12 skipped**; Ruff, format, mypy, lockfile, dan generated API
schema juga lulus. Tes otomatis tidak menggantikan penilaian kualitas manusia.

### Trial PDF sintetis penuh (2026-09-17)

Trial bounded pada fixture PDF sintetis non-private 12 halaman menjalankan
import → analysis → OCR `AUTO` → translation CT2 → finalisasi prosedural →
reconstruction `HYBRID` → export melalui API, queue, worker, SQLite, dan
filesystem lokal. Analysis menghasilkan 408 segmen tanpa unresolved source;
OCR memilih nol halaman karena seluruh halaman terdeteksi digital.

Translation menyelesaikan 408/408 segmen tanpa provider error dalam 14 detik.
Seluruh hasil tetap review-required dan approval berikutnya hanya finalisasi
prosedural API, bukan review linguistik manusia. Reconstruction menyelesaikan
12/12 halaman tanpa overflow/collision record; export valid memiliki 12 halaman,
text layer selectable, ukuran halaman dan set font yang sama, serta tidak
menyisakan source segment yang terdeteksi oleh validator trial.

Fixture ini tidak mematerialisasi tabel atau asset sebagai entitas analysis,
sehingga trial tersebut bukan bukti pipeline-level preservation untuk tabel,
gambar, atau asset umum. Metrik fidelity hanya berlaku untuk fixture ini dan
tidak menggantikan inspeksi visual maupun review bahasa. Regresi final mencatat
**1.853 passed, 12 skipped**; test web, lint, typecheck, dan production build
juga lulus.

## 1. Pasang dependency konversi secara eksplisit

Dari root repository:

```bash
uv sync --locked --extra ct2 --group ct2-convert
```

`uv sync --locked` biasa **tidak** memasang CT2, SentencePiece, Transformers,
atau PyTorch untuk pilot ini. Extra `ct2` memasang runtime ringan; group
`ct2-convert` memasang alat konversi yang lebih besar. Lockfile menyimpan kedua
set dependency agar version dan hash paket reproducible. Instalasi dependency
dapat memerlukan internet; tidak ada model yang diunduh saat `uv sync`.

## 2. Provision di luar repository

Pilih directory baru yang absolut dan khusus untuk model. Jangan gunakan root
filesystem, home root, repository Git, atau symlink menuju/dari repository.
Script tidak menimpa model yang sudah ada dan tidak menerima model ID/URL
arbitrer.

### Unduh artifact publik yang dipin

Linux:

```bash
export TRANSLOKA_CT2_MODEL_DIR="$HOME/.local/share/TransLoka-models/opus-mt-en-id-ct2-int8"
uv run --no-sync python scripts/provision-ct2-model.py \
  --model-dir "$TRANSLOKA_CT2_MODEL_DIR" --download
```

PowerShell:

```powershell
$env:TRANSLOKA_CT2_MODEL_DIR = Join-Path $env:LOCALAPPDATA "TransLoka\models\opus-mt-en-id-ct2-int8"
uv run --no-sync python scripts/provision-ct2-model.py --model-dir $env:TRANSLOKA_CT2_MODEL_DIR --download
```

Hanya operasi `--download` yang menghubungi Hugging Face melalui HTTPS
(termasuk CDN HTTPS penyedia) untuk file publik pada revision yang dipin.
Tidak ada PDF, teks pengguna, atau credential yang dikirim. Masing-masing file
dibatasi ukurannya dan diverifikasi SHA-256 sebelum konversi dimulai.

### Gunakan sumber yang sudah tersedia, tanpa jaringan

Jika snapshot sumber sudah diprovision di directory lokal di luar Git:

```bash
uv run --no-sync python scripts/provision-ct2-model.py \
  --model-dir "$TRANSLOKA_CT2_MODEL_DIR" \
  --source-dir "$HOME/.local/share/TransLoka-nmt-pilot/opus-mt-en-id-source"
```

`--source-dir` wajib memuat `config.json`, `generation_config.json`,
`pytorch_model.bin`, `source.spm`, `target.spm`, `vocab.json`,
`tokenizer_config.json`, dan `README.md` dengan checksum yang disetujui.
File lain tidak disalin ke staging konversi. Direktori hasil CT2 lama yang hanya
memuat tiga file bukan bundle runtime lengkap: gunakan directory tujuan baru,
jangan membuat manifest sendiri untuk melewati verifikasi.

Konversi menggunakan file lokal saja, `trust_remote_code=False`, dan pemuatan
PyTorch `weights_only=True`. Bobot pickle arbitrer dan kode model jarak jauh
tidak boleh digunakan. Script menulis bundle lengkap ke staging, memeriksa
checksum hasil, lalu memindahkannya ke tujuan. Kegagalan tidak meninggalkan
instalasi parsial. Jika tujuan sudah valid, perintah hanya memverifikasinya;
jika rusak/tidak dikenal, perintah gagal tanpa mengubah tujuan.

Bundle akhir:

```text
opus-mt-en-id-ct2-int8/
  config.json                  # konfigurasi CT2, bukan config Transformers sumber
  model.bin
  shared_vocabulary.json
  source.spm
  target.spm
  vocab.json
  tokenizer_config.json
  README.md                    # model card upstream yang dipin
  manifest.json                # revision, lisensi, versi konverter, semua hash
```

## 3. Jalankan dengan runtime minimal, offline

Setelah konversi berhasil, buang dependency konversi yang tidak diperlukan dari
environment aplikasi dan pertahankan extra runtime:

```bash
uv sync --locked --extra ct2
uv run --no-sync python scripts/provision-ct2-model.py \
  --model-dir "$TRANSLOKA_CT2_MODEL_DIR" --verify
```

`--verify` tidak mengunduh model dan tidak mengimpor runtime/converter. Provider
membaca SentencePiece/vocabulary lokal secara langsung, bukan
`AutoTokenizer.from_pretrained`. Restart API **dan worker** dengan
`TRANSLOKA_CT2_MODEL_DIR` yang sama. Gunakan model ID `opus-mt-en-id-ct2-int8`
untuk jalur pilot yang mendukungnya; tidak ada perubahan model Ollama terpilih
secara otomatis. Jangan aktifkan semantic validation pada pilot ini.

Pertahankan `--extra ct2` pada sync berikutnya: sync standar dapat menghapus
dependency opt-in. Launcher sebaiknya memakai `uv run --no-sync` setelah sync
eksplisit agar tidak mengubah environment yang sudah diverifikasi.

Menyalin bundle lengkap ke komputer offline diperbolehkan setelah ketentuan
lisensi ditinjau. Pasang dependency dari cache/wheelhouse yang sesuai sebelum
memutus jaringan, jalankan `--verify`, lalu gunakan path absolut lokal komputer
tersebut. Tidak ada fallback download dari inference; file hilang, manifest
berubah, atau checksum salah harus diperbaiki lewat provisioning eksplisit.

## Pemilihan provider dan pemulihan

Pada tab translation web, pilih **CTranslate2 (offline CPU)**. UI menampilkan
model ID tetap `opus-mt-en-id-ct2-int8`; model tidak dapat diganti dengan ID
Ollama atau model cloud. Readiness tetap memverifikasi provisioning, runtime,
pasangan bahasa, worker, dan segmen eligible sebelum job dapat dimulai.

Untuk integrasi API, setelah readiness CT2 berhasil gunakan
`translation/start` dengan:

```json
{
  "provider_type": "CTRANSLATE2",
  "model_id": "opus-mt-en-id-ct2-int8",
  "scope": "UNTRANSLATED_ONLY"
}
```

Gunakan idempotency key baru setelah job sebelumnya terminal. `retry-failed`
mempertahankan provider job semula; endpoint itu tidak mengganti Qwen menjadi
CT2. Scope di atas mempertahankan hasil yang sudah diterjemahkan, diedit,
direview, atau dikunci. Semua hasil CT2 baru tetap `NEEDS_REVIEW`.

Fallback **nonaktif secara default**. Untuk mengaktifkannya secara eksplisit,
set `TRANSLOKA_CT2_OLLAMA_FALLBACK_MODEL` ke model Ollama yang sudah terpasang
pada environment API sebelum dispatch. Endpoint `TRANSLOKA_OLLAMA_URL` wajib
loopback dan server Ollama harus dijalankan dengan `OLLAMA_NO_CLOUD=1`;
jangan gunakan alias model cloud. Nama model, endpoint lokal, dan konfigurasi disnapshot bersama job;
perubahan environment setelah dispatch tidak mengubah fallback job itu.
Worker hanya mencoba fallback pada segmen yang tetap gagal setelah retry
CT2. Hasil fallback ditandai `NMT_LOCAL_FALLBACK_USED`; tidak ada fallback cloud.
Periksa kapasitas RAM sebelum mengaktifkannya. Pilot di atas tidak memakai
fallback dan tidak membuktikan throughput atau kualitas fallback.

NMT memakai pemisahan span dan penggabungan deterministik, bukan prompt chat.
Glossary request dicocokkan sebagai frasa whole-word yang case-sensitive;
aturan matching yang lebih kaya belum diteruskan oleh schema request tersebut.
Gaya, konteks antarparagraf, makna negasi, serta kelancaran di sekitar span
terlindungi harus diperiksa manusia. Hasil pilot bukan alasan untuk
menyetujui seluruh buku atau melewati review.

## Diagnosis dan lisensi

- **Path ditolak:** pilih directory khusus yang absolut di luar semua Git repo.
- **Tujuan tidak valid:** pertahankan file lama untuk diagnosis dan pilih tujuan
  baru. Script tidak menghapus atau memperbaiki bundle yang tidak dikenal.
- **Versi converter salah:** jalankan kembali sync dengan `--group ct2-convert`.
- **Checksum sumber/hasil berbeda:** hentikan penggunaan; jangan menyesuaikan
  manifest/hash agar lolos. Periksa pin, platform, dan sumber download.
- **Dependency runtime hilang:** jalankan `uv sync --locked --extra ct2`, lalu
  restart proses lokal dengan environment/path yang sama.

Model card yang disimpan mencatat lisensi Apache-2.0 dan atribusi Helsinki-NLP /
OPUS-MT. Quantization adalah perubahan format/representasi bobot, bukan model
baru tanpa kewajiban lisensi. Sebelum redistribusi, sertakan lisensi Apache-2.0,
pertahankan atribusi/NOTICE upstream yang berlaku, dan nyatakan perubahan INT8.
Lihat [`THIRD_PARTY_LICENSES.md`](../THIRD_PARTY_LICENSES.md). File model dan
document pengguna tidak boleh dikomit ke Git.
