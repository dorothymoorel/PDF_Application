# Pemilihan Model Lokal

TransLoka memakai Ollama lokal untuk inference. Tidak ada model default universal:
model dipilih berdasarkan hardware, license, structured output, placeholder,
kualitas English → Indonesian, dan resource usage komputer pengguna.

## 1. Siapkan Ollama

Jalankan service pada komputer yang sama:

```powershell
ollama serve
ollama list
Invoke-RestMethod http://127.0.0.1:11434/api/version
```

Jika URL tidak standar, set hanya endpoint loopback:

```powershell
$env:TRANSLOKA_OLLAMA_URL = "http://127.0.0.1:11434"
```

Endpoint remote, network share, atau URL dengan public bind ditolak. Restart
API setelah mengubah environment.

## 2. Pasang kandidat secara sadar

Model tidak diunduh otomatis oleh TransLoka. Setelah memilih kandidat dan
memeriksa license-nya, pasang secara eksplisit:

```powershell
ollama pull <model-id>
ollama show <model-id>
ollama list
```

Catat model ID persis, ukuran, quantization, context, dan license. License
model terpisah dari license Ollama; status `UNKNOWN` harus ditinjau sebelum
penggunaan permanen.

## 3. Health dan discovery

Urutan yang aman:

1. pastikan `ollama serve` hidup;
2. cek endpoint `/api/version`;
3. refresh daftar model lokal dari fitur model/API bila tersedia;
4. pastikan model berstatus installed;
5. pilih model untuk role translation atau validation;
6. jalankan benchmark singkat pada hardware yang sama.

Endpoint model lokal yang tersedia pada API contract meliputi:

```text
GET  /api/v1/models/ollama/health
GET  /api/v1/models
POST /api/v1/models/refresh
POST /api/v1/models/{model_id}/select
```

Panel model belum menjadi bagian dari navigasi web utama pada semua milestone.
Gunakan OpenAPI lokal (`http://127.0.0.1:8000/docs`) hanya bila router tersebut
sudah diaktifkan pada runtime yang sedang dipakai.

## 4. Benchmark model

### Quick model benchmark

Quick benchmark menguji dataset English → Indonesian dengan structured output,
latency, dan placeholder integrity. Konfigurasi awal yang didukung:

```json
{
  "dataset_version": "translation_benchmark_en_id_0.1",
  "temperature": 0.1,
  "batch_sizes": [1, 5]
}
```

Endpoint benchmark:

```text
POST /api/v1/models/{model_id}/benchmarks/quick
```

Request membutuhkan `Idempotency-Key`. Hasil dapat berstatus completed,
partially completed, failed, atau cancelled. Model yang menghasilkan JSON
invalid atau placeholder mismatch tidak boleh direkomendasikan sebagai default.

### Performance pipeline benchmark

Untuk mengukur overhead import/extraction/OCR/reconstruction/RAM/disk/query:

```powershell
.\scripts\benchmark.ps1 --pages 10 50 100 250
```

Runner ini memakai provider fake dan temporary storage. Ia bukan pengganti
benchmark kualitas model dan tidak boleh dibandingkan langsung antar-hardware.

## 5. Cara memilih hasil

Pilih model translation hanya jika:

- health dan model installed;
- structured output valid;
- semua segment ID dipertahankan;
- placeholder, URL, angka, code, dan citation utuh;
- Bahasa Indonesia dapat direview dan makna sumber tidak berubah;
- RAM/VRAM tidak membuat OS tidak responsif;
- latency masih dapat diterima untuk ukuran dokumen pengguna;
- license sesuai rencana penggunaan.

Model yang tidak memenuhi satu syarat critical menjadi rejected/fallback-only,
bukan default. Untuk hardware rendah resource, gunakan batch/context lebih kecil
dan uji ulang; jangan menyimpulkan model terbaik dari ukuran parameter saja.

## 6. Konfigurasi translation

Translation request memilih `model_id`, `batch_size`, `context_mode`, style,
scope, serta apakah semantic validation dijalankan. Mulai dari batch kecil dan
`context_mode=STANDARD`, lalu tingkatkan setelah stabil.

Jangan mengubah source/target language di luar English → Indonesian pada Personal
MVP. Jangan menggunakan model remote atau memberikan tool filesystem, shell,
network, database, atau deletion kepada model.

## 7. Jika model gagal

- `OLLAMA_UNAVAILABLE`: hidupkan Ollama dan cek loopback URL;
- `MODEL_NOT_INSTALLED`: pasang model dengan `ollama pull`;
- `REMOTE_OLLAMA_BLOCKED`: kembalikan URL ke `127.0.0.1`;
- `INVALID_JSON`/`SCHEMA_VALIDATION_FAILED`: pilih model atau setting yang lebih
  stabil;
- `PLACEHOLDER_MISMATCH`: jangan gunakan model untuk dokumen tersebut sebelum
  masalah integrity diselesaikan.

Simpan report benchmark bersama hardware profile dan settings. Report dari
komputer lain adalah bukti terpisah, bukan ranking universal.
