# RECONSTRUCTION ENGINE

## TransLoka PDF Layout Preservation and Reconstruction Specification

**Document Name:** `RECONSTRUCTION_ENGINE.md`  
**Document Version:** 0.1  
**Status:** Draft  
**Decision Date:** 2026-07-26  
**Deployment Target:** Local-First Personal MVP  
**Primary Output:** Translated PDF  
**Default Reconstruction Mode:** Hybrid  

**Related Documents:**

- `PRD.md`
- `ARCHITECTURE.md`
- `TECH_STACK_DECISIONS.md`
- `DOCUMENT_IR.md`
- `TRANSLATION_PIPELINE.md`
- `GLOSSARY_ENGINE.md`
- `LOCAL_MODEL_BENCHMARK.md`

---

# 1. Purpose

Reconstruction Engine bertanggung jawab membangun dokumen hasil terjemahan berdasarkan:

- file PDF sumber;
- Document IR;
- teks terjemahan final;
- geometry sumber;
- gambar dan aset;
- tabel;
- font;
- heading;
- header dan footer;
- nomor halaman;
- reconstruction settings.

Tujuan utamanya adalah menghasilkan PDF berbahasa Indonesia yang:

- tetap dapat dibaca;
- tidak kehilangan konten;
- mempertahankan gambar;
- mempertahankan urutan halaman;
- mempertahankan struktur bab;
- mempertahankan tabel sejauh memungkinkan;
- mempertahankan visual sumber secara wajar;
- tidak memiliki teks terpotong;
- tidak memiliki elemen bertumpuk;
- dapat dibuka oleh PDF reader standar.

Reconstruction Engine tidak menjamin hasil pixel-perfect untuk seluruh PDF karena panjang teks Bahasa Indonesia dapat berbeda dari bahasa Inggris.

Prioritas tertinggi adalah:

```text
Kelengkapan isi
→ Keterbacaan
→ Struktur semantik
→ Integritas gambar dan tabel
→ Kemiripan visual
```

---

# 2. Reconstruction Goals

## 2.1 Content Completeness

Seluruh segment yang dipilih harus muncul pada output.

Tidak boleh ada:

- paragraf hilang;
- heading hilang;
- caption hilang;
- footnote hilang tanpa warning;
- tabel hilang;
- halaman sumber terlewat.

## 2.2 Visual Preservation

Sistem harus mempertahankan sejauh memungkinkan:

- ukuran halaman;
- orientasi;
- background;
- gambar;
- diagram;
- logo;
- posisi umum elemen;
- hierarchy heading;
- nomor halaman;
- header dan footer;
- whitespace;
- margin.

## 2.3 Readability

Output tidak boleh memiliki:

- font terlalu kecil;
- text clipping;
- text overlap;
- image overlap;
- line spacing yang tidak terbaca;
- paragraph order yang salah;
- table cell yang tidak dapat dibaca.

## 2.4 Deterministic Reconstruction

Input Document IR dan konfigurasi yang sama harus menghasilkan struktur output yang dapat direproduksi.

Perbedaan minor pada binary PDF dapat diterima, tetapi:

- urutan halaman;
- teks;
- gambar;
- layout decision;
- warning;

harus konsisten.

## 2.5 Partial Reconstruction

Sistem harus dapat membangun ulang:

- satu halaman;
- satu section;
- halaman yang berubah;
- seluruh dokumen.

Perubahan pada satu segment tidak boleh selalu memerlukan reconstruction seluruh dokumen jika mapping halaman tidak berubah.

---

# 3. Non-Goals

Personal MVP tidak bertujuan untuk:

- menghasilkan replika pixel-perfect untuk semua PDF;
- menggambar ulang ilustrasi;
- menerjemahkan teks yang menyatu dalam gambar;
- memulihkan font proprietary yang tidak dapat digunakan;
- merekonstruksi diagram kompleks sebagai vector editable;
- memperbaiki desain sumber;
- menghasilkan file InDesign;
- menghasilkan layout profesional setara typesetting manual;
- menerjemahkan formula;
- menghapus watermark sumber;
- menghapus DRM;
- mengubah identitas visual penerbit.

---

# 4. Reconstruction Modes

Reconstruction Engine mendukung tiga mode.

```text
OVERLAY
REFLOW
HYBRID
```

---

# 5. Overlay Mode

## 5.1 Definition

Overlay Mode mempertahankan halaman sumber sebagai dasar visual, kemudian menempatkan teks terjemahan di area yang sesuai.

Flow:

```text
Source page
    ↓
Hide or cover source text regions
    ↓
Generate translated text overlay
    ↓
Merge overlay with source page
    ↓
Validate result
```

## 5.2 Best Use Cases

Overlay cocok untuk:

- laporan singkat;
- brosur;
- formulir;
- slide export;
- halaman dengan textbox jelas;
- dokumen dengan banyak elemen visual;
- halaman dengan paragraf pendek;
- caption;
- header;
- footer;
- fixed labels.

## 5.3 Advantages

- visual paling dekat dengan sumber;
- gambar dan dekorasi mudah dipertahankan;
- nomor halaman dapat tetap pada posisi asli;
- background tidak perlu dibangun ulang.

## 5.4 Limitations

- rentan text overflow;
- sulit untuk paragraf panjang;
- font sumber mungkin tidak tersedia;
- teks sumber mungkin tidak dapat dihapus bersih;
- halaman multi-column dapat sulit;
- karakter hasil OCR dapat menjadi bagian gambar.

---

# 6. Reflow Mode

## 6.1 Definition

Reflow Mode membangun ulang halaman berdasarkan urutan dan struktur konten, bukan mempertahankan setiap posisi sumber.

Flow:

```text
Document IR
    ↓
Semantic section structure
    ↓
HTML and CSS layout
    ↓
Pagination
    ↓
WeasyPrint PDF
```

## 6.2 Best Use Cases

Reflow cocok untuk:

- ebook;
- buku teknis;
- jurnal;
- dokumen akademik;
- novel;
- paragraf panjang;
- halaman dengan expansion tinggi;
- dokumen yang mengutamakan keterbacaan.

## 6.3 Advantages

- lebih tahan terhadap teks panjang;
- pagination lebih natural;
- paragraph flow lebih baik;
- mudah menambah halaman;
- lebih mudah menghasilkan hasil yang nyaman dibaca.

## 6.4 Limitations

- layout dapat berbeda jauh dari sumber;
- posisi gambar dapat bergeser;
- nomor halaman berubah;
- daftar isi mungkin perlu diperbarui;
- fixed design dapat hilang;
- visual comparison menjadi lebih sulit.

---

# 7. Hybrid Mode

## 7.1 Definition

Hybrid Mode menggabungkan Overlay dan Reflow pada level:

- dokumen;
- halaman;
- region;
- block.

Hybrid Mode merupakan default TransLoka.

## 7.2 Default Mapping

```text
Cover                         → preserve original or overlay
Header                        → overlay
Footer                        → overlay
Page number                   → overlay or regenerated
Short heading                 → overlay
Short caption                 → overlay
Short paragraph               → overlay
Long paragraph                → reflow
Body text in book             → reflow
Image                         → preserve
Simple table                  → reconstruct
Complex table                 → preserve or render as image
Code block                    → reconstruct
Formula                       → preserve
Footnote                      → reflow near reference
```

## 7.3 Hybrid Decision Level

Mode dapat ditentukan pada:

```text
DOCUMENT
PAGE
BLOCK
```

Contoh:

```json
{
  "document_mode": "HYBRID",
  "page_overrides": {
    "page_001": "OVERLAY",
    "page_010": "REFLOW"
  }
}
```

---

# 8. Reconstruction Pipeline

```text
LOAD DOCUMENT IR
        │
        ▼
VALIDATE TRANSLATION STATE
        │
        ▼
LOAD SOURCE PAGE AND ASSETS
        │
        ▼
CLASSIFY PAGE AND BLOCK STRATEGY
        │
        ▼
RESOLVE FONT MAPPING
        │
        ▼
MEASURE TARGET TEXT
        │
        ▼
CALCULATE TARGET GEOMETRY
        │
        ▼
APPLY FITTING STRATEGY
        │
        ▼
GENERATE PAGE LAYERS
        │
        ▼
MERGE PAGE
        │
        ▼
RUN LAYOUT VALIDATION
        │
        ▼
RETRY WITH FALLBACK STRATEGY
        │
        ▼
ASSEMBLE DOCUMENT
        │
        ▼
RESTORE METADATA AND LINKS
        │
        ▼
FINAL PDF VALIDATION
```

---

# 9. Reconstruction Preconditions

Reconstruction hanya boleh dijalankan jika:

1. Document IR tersedia.
2. Seluruh halaman sumber terdaftar.
3. File sumber dapat dibaca.
4. Segment yang dipilih memiliki `final_text`.
5. Protected placeholder telah dipulihkan.
6. Tidak ada critical terminology error.
7. Gambar dan aset utama tersedia.
8. Geometry sumber valid.
9. Reconstruction mode ditentukan.
10. Output directory tersedia.

Jika critical condition tidak terpenuhi:

```text
RECONSTRUCTION_BLOCKED
```

---

# 10. Page Classification

Setiap halaman diklasifikasikan sebelum reconstruction.

```text
FIXED_LAYOUT
REFLOW_FRIENDLY
MIXED_LAYOUT
IMAGE_ONLY
TABLE_HEAVY
CODE_HEAVY
FORMULA_HEAVY
COVER
UNKNOWN
```

## 10.1 Fixed Layout

Ciri:

- banyak textbox;
- gambar dan label;
- layout grafis;
- teks pendek;
- visual positioning penting.

Default:

```text
OVERLAY
```

## 10.2 Reflow Friendly

Ciri:

- satu atau dua kolom;
- paragraf panjang;
- sedikit gambar;
- hierarchy heading jelas.

Default:

```text
REFLOW
```

## 10.3 Mixed Layout

Ciri:

- body text panjang;
- gambar tetap;
- caption;
- sidebar.

Default:

```text
HYBRID
```

---

# 11. Block Strategy Classifier

Setiap block diberi reconstruction strategy.

```text
PRESERVE
OVERLAY
REFLOW
RECONSTRUCT
RENDER_AS_IMAGE
MANUAL_REVIEW
```

Contoh:

| Block Type | Default Strategy |
|---|---|
| DOCUMENT_TITLE | OVERLAY |
| HEADING | OVERLAY atau REFLOW |
| PARAGRAPH | REFLOW |
| CAPTION | OVERLAY |
| HEADER | OVERLAY |
| FOOTER | OVERLAY |
| PAGE_NUMBER | OVERLAY |
| IMAGE | PRESERVE |
| TABLE | RECONSTRUCT |
| FORMULA | PRESERVE |
| CODE_BLOCK | RECONSTRUCT |
| DECORATIVE_TEXT | PRESERVE |
| UNKNOWN | MANUAL_REVIEW |

---

# 12. Source Page Preservation

Source PDF tidak boleh dimodifikasi.

Reconstruction menggunakan:

- read-only source page;
- copied page object;
- page render;
- extracted asset;
- generated overlay.

Output disimpan pada file baru.

Contoh:

```text
original/book.pdf
exports/book-id-v1.pdf
```

---

# 13. Source Text Removal Strategies

Pada Overlay Mode, source text perlu disembunyikan atau ditutup.

Strategi:

```text
REDACTION
BACKGROUND_COLOR_COVER
CLIPPED_REGION_REBUILD
FULL_PAGE_BACKGROUND_RENDER
```

---

# 14. Redaction Strategy

Digunakan jika PDF memiliki text layer yang dapat dihapus atau ditutupi dengan aman.

Risiko:

- vector di bawah teks dapat ikut terdampak;
- redaction behavior berbeda antar-PDF;
- background kompleks dapat rusak.

Redaction harus diuji pada copy halaman, bukan file asli.

---

# 15. Background Color Cover

Sistem menggambar rectangle sesuai background area.

Cocok jika:

- background polos;
- warna dapat dideteksi;
- tidak ada gambar di bawah teks.

Tidak cocok untuk:

- gradient;
- foto;
- texture;
- pola kompleks.

---

# 16. Full-Page Background Render

Halaman sumber dirender menjadi gambar, lalu digunakan sebagai background.

Teks sumber ditutup pada raster background, kemudian teks terjemahan ditambahkan.

Keuntungan:

- struktur visual stabil;
- vector complexity tidak menjadi masalah.

Kekurangan:

- source page menjadi raster;
- text sumber tidak lagi selectable;
- file dapat membesar;
- kualitas zoom menurun;
- accessibility berkurang.

Strategi ini hanya digunakan sebagai fallback.

---

# 17. Region Reconstruction

Untuk background kompleks:

1. render halaman;
2. identifikasi region teks;
3. lakukan inpainting sederhana atau crop background;
4. tempatkan region yang telah dibersihkan;
5. tambahkan teks target.

Personal MVP tidak wajib memiliki AI image inpainting.

Jika background tidak dapat dibersihkan:

```text
PRESERVE_SOURCE_TEXT_WITH_TRANSLATION_CALLOUT
```

atau:

```text
FALLBACK_TO_REFLOW
```

---

# 18. Text Measurement

Sebelum teks ditempatkan, sistem harus mengukur:

- font size;
- line height;
- paragraph spacing;
- available width;
- available height;
- estimated line count;
- word wrapping;
- punctuation;
- bold dan italic spans.

Text measurement harus menggunakan font output yang sebenarnya.

---

# 19. Font Mapping

## 19.1 Font Resolution Order

```text
1. Original embedded font jika legal dan dapat digunakan
2. Same font dari system
3. Metric-compatible font
4. Configured fallback font
5. Universal fallback font
```

## 19.2 Default Fallback Categories

```text
SERIF
SANS_SERIF
MONOSPACE
DISPLAY
SYMBOL
```

Contoh fallback:

```text
Serif      → Noto Serif
Sans Serif → Noto Sans
Monospace  → Noto Sans Mono
```

Font spesifik dapat dikonfigurasi pada fase implementasi.

## 19.3 Font Requirements

Font harus mendukung:

- karakter Latin;
- Bahasa Indonesia;
- punctuation;
- bold;
- italic;
- symbol dokumen.

Jika glyph tidak tersedia:

```text
MISSING_GLYPH_WARNING
```

---

# 20. Font Embedding

Font output sebaiknya di-embed atau subset jika lisensinya memungkinkan.

Sistem harus mencatat:

```text
EMBEDDED
SUBSET_EMBEDDED
SYSTEM_REFERENCE
NOT_EMBEDDED
```

Font proprietary tidak boleh disalin atau didistribusikan tanpa izin.

---

# 21. Text Expansion Ratio

Hitung:

```text
target_character_count / source_character_count
```

dan:

```text
target_rendered_height / source_box_height
```

Kategori awal:

```text
LOW_EXPANSION       ≤ 1.10
MODERATE_EXPANSION  1.11–1.35
HIGH_EXPANSION      1.36–1.75
EXTREME_EXPANSION   > 1.75
```

Character ratio hanya sinyal.

Keputusan akhir berdasarkan rendered geometry.

---

# 22. Text Fitting Strategy

Urutan strategi default:

```text
1. Recalculate word wrapping
2. Use target-language line breaking
3. Expand textbox within safe region
4. Reduce space after paragraph
5. Reduce line spacing
6. Reduce font size within threshold
7. Move following blocks
8. Reflow block
9. Continue on next page
10. Add page
11. Manual review
```

Teks tidak boleh dipotong agar muat.

---

# 23. Safe Font Reduction

Default maksimal pengurangan:

```text
10% dari ukuran sumber
```

Pengaturan advanced dapat mengizinkan:

```text
15%
```

Font tidak boleh kurang dari minimum readable size.

Contoh default:

```text
Body text minimum: 8 pt
Footnote minimum: 6.5 pt
Caption minimum: 7 pt
```

Nilai final dapat disesuaikan berdasarkan dokumen.

Jika kebutuhan lebih kecil dari minimum:

```text
FONT_TOO_SMALL
```

dan strategi harus berubah.

---

# 24. Line Spacing

Line spacing dapat dikurangi, tetapi tidak boleh menyebabkan:

- ascender bertumpuk;
- descender bertumpuk;
- readability buruk.

Minimum awal:

```text
line_height ≥ 1.0 × font_size
```

Recommended body:

```text
1.15–1.4 × font_size
```

---

# 25. Textbox Expansion

Textbox dapat diperluas jika:

- area di bawah kosong;
- tidak melanggar margin;
- tidak menutupi gambar;
- tidak menutupi footer;
- tidak menutupi block lain;
- tidak keluar halaman.

Target geometry baru harus disimpan pada Document IR.

---

# 26. Moving Following Blocks

Jika block diperbesar, block berikutnya dapat dipindahkan.

Syarat:

- reading order tetap;
- tidak menabrak fixed element;
- displacement masih di bawah threshold;
- tidak merusak hubungan caption dan gambar.

Perpindahan besar harus menghasilkan:

```text
SIGNIFICANT_LAYOUT_SHIFT
```

---

# 27. Reflow to Next Page

Block dapat dilanjutkan ke halaman berikutnya.

Segment tetap memiliki ID yang sama, tetapi menghasilkan beberapa fragments.

```json
{
  "segment_id": "segment_001",
  "target_fragments": [
    {
      "target_page_id": "page_target_010",
      "fragment_order": 1
    },
    {
      "target_page_id": "page_target_011",
      "fragment_order": 2
    }
  ]
}
```

---

# 28. Page Addition

Halaman tambahan diperbolehkan jika diperlukan untuk menjaga isi.

Halaman tambahan harus:

- mengikuti ukuran section;
- menggunakan margin yang sesuai;
- mempertahankan header dan footer jika relevan;
- memiliki logical numbering yang jelas;
- dicatat dalam source-target mapping.

Warning:

```text
PAGE_ADDED_DUE_TO_TRANSLATION_EXPANSION
```

---

# 29. Orphan and Widow Control

Pada Reflow Mode, hindari:

- satu baris paragraf tersisa di bawah halaman;
- satu baris paragraf berpindah sendiri ke halaman baru;
- heading berada sendiri tanpa paragraf;
- caption terpisah jauh dari gambar.

Rules:

```text
minimum paragraph lines at page bottom: 2
minimum paragraph lines at page top: 2
heading keep-with-next: true
caption keep-with-object: true
```

---

# 30. Heading Reconstruction

Heading harus mempertahankan:

- hierarchy;
- order;
- numbering;
- emphasis;
- spacing;
- relationship dengan section.

Heading tidak boleh berada sendirian pada akhir halaman.

Jika heading terlalu panjang:

1. wrap;
2. kurangi font terbatas;
3. perluas region;
4. reflow;
5. tambah halaman.

---

# 31. Paragraph Reconstruction

Paragraph harus mempertahankan:

- alignment;
- first-line indent;
- spacing;
- reading order;
- paragraph boundaries;
- inline style.

Justified text dapat menghasilkan spacing buruk pada Bahasa Indonesia.

Sistem dapat mengubah:

```text
JUSTIFY → LEFT
```

jika justification menghasilkan gap ekstrem.

Perubahan harus dicatat.

---

# 32. Inline Styles

Reconstruction harus mempertahankan jika terpetakan:

- bold;
- italic;
- underline;
- superscript;
- subscript;
- inline code;
- hyperlink.

Jika hasil terjemahan tidak memiliki mapping token yang identik, style dapat diterapkan berdasarkan:

- protected item;
- source phrase alignment;
- semantic span;
- manual review.

---

# 33. Image Preservation

Image harus mempertahankan:

- aspect ratio;
- crop;
- rotation;
- opacity;
- z-index;
- caption relation;
- page association.

Gambar tidak boleh diregangkan secara tidak proporsional.

---

# 34. Image Scaling

Image dapat diskalakan jika:

- aspect ratio tetap;
- resolusi masih memadai;
- tidak melebihi halaman;
- tidak menyebabkan caption terpisah.

Maximum default enlargement:

```text
110%
```

Maximum reduction ditentukan berdasarkan readability.

---

# 35. Image Compression

Default:

```text
PRESERVE_ORIGINAL
```

Optional:

```text
LOSSLESS_RECOMPRESS
STANDARD_RECOMPRESS
```

Aplikasi tidak boleh mengompresi gambar secara agresif tanpa pengaturan pengguna.

---

# 36. Text Inside Images

Personal MVP:

```text
PRESERVE_UNCHANGED
```

Teks yang menyatu dalam gambar tetap bahasa sumber.

Sistem dapat menampilkan warning:

```text
UNTRANSLATED_TEXT_INSIDE_IMAGE
```

Fitur translation image ditunda.

---

# 37. Caption Reconstruction

Caption yang terpisah dari gambar:

- diterjemahkan;
- ditempatkan dekat gambar;
- mempertahankan numbering;
- mempertahankan relation;
- mengikuti image movement.

Contoh:

```text
Figure 3. Authentication Workflow
```

menjadi:

```text
Gambar 3. Authentication Workflow
```

atau sesuai glossary dan setting.

---

# 38. Table Reconstruction

Tabel diklasifikasikan:

```text
SIMPLE
MODERATE
COMPLEX
UNRECOGNIZED
```

## 38.1 Simple Table

Ciri:

- grid jelas;
- tidak ada nested table;
- merge terbatas;
- sedikit kolom.

Strategy:

```text
RECONSTRUCT
```

## 38.2 Moderate Table

Ciri:

- merged cell;
- multi-line content;
- continuation page;
- beberapa style.

Strategy:

```text
RECONSTRUCT_WITH_VALIDATION
```

## 38.3 Complex Table

Ciri:

- nested structure;
- irregular boundaries;
- diagram-like layout;
- banyak merged cell;
- layout tidak stabil.

Strategy:

```text
PRESERVE_AS_IMAGE
```

atau:

```text
MANUAL_REVIEW
```

---

# 39. Table Cell Fitting

Urutan:

1. wrap text;
2. expand row height;
3. adjust column width;
4. reduce cell padding;
5. reduce font size terbatas;
6. move table continuation;
7. split table across pages;
8. fallback as image.

Kolom angka tidak boleh berubah alignment tanpa alasan.

---

# 40. Table Pagination

Saat tabel melintasi halaman:

- repeat header row;
- preserve column widths;
- preserve table ID;
- mark continuation;
- avoid splitting row jika memungkinkan.

Contoh continuation:

```text
Table 4 — continued
```

atau sesuai style sumber.

---

# 41. Table Integrity Validation

Validator memeriksa:

- row count;
- column count;
- merged cell;
- header;
- numeric values;
- missing cell;
- overflow;
- alignment;
- continuation.

Critical:

```text
TABLE_CELL_MISSING
TABLE_STRUCTURE_CORRUPTED
```

---

# 42. Code Block Reconstruction

Code block harus mempertahankan:

- whitespace;
- indentation;
- line breaks;
- syntax text;
- line number;
- monospace font;
- background jika ada.

Code tidak boleh di-wrap secara sembarangan.

Jika baris terlalu panjang:

```text
SCALE_CODE_FONT
HORIZONTAL_CLIP_WITH_WARNING
REFLOW_CODE_BOX
```

Default:

- reduce font terbatas;
- allow line wrapping hanya jika setting aktif;
- warning jika line tidak muat.

---

# 43. Formula Reconstruction

Formula:

```text
PRESERVE_UNCHANGED
```

Jika formula berupa vector atau image:

- pertahankan aset;
- pertahankan posisi;
- pertahankan equation number.

Teks penjelasan di sekitarnya tetap diterjemahkan.

---

# 44. Footnote Reconstruction

Footnote harus:

- tetap terhubung dengan marker;
- muncul pada halaman relevan jika memungkinkan;
- menggunakan font footnote;
- tidak hilang;
- tidak bertumpuk dengan footer.

Jika footnote tidak muat:

1. perluas footnote region;
2. pindahkan sebagian body text;
3. pindahkan footnote continuation;
4. beri warning.

---

# 45. Header and Footer

Header dan footer dapat:

```text
PRESERVE
TRANSLATE
REGENERATE
REMOVE
```

Default mengikuti project setting.

Header atau footer berulang tidak boleh menghasilkan segment translation berulang jika teks identik.

---

# 46. Page Numbers

Page number mode:

```text
PRESERVE_SOURCE_LOGICAL_NUMBER
REGENERATE_LOGICAL_NUMBER
REGENERATE_PHYSICAL_NUMBER
HIDE
```

Default:

```text
PRESERVE_SOURCE_LOGICAL_NUMBER
```

Jika halaman tambahan dibuat, sistem harus memutuskan:

- menambahkan suffix;
- memperbarui seluruh numbering;
- menggunakan physical output number;
- meminta user review.

Personal MVP default untuk halaman tambahan:

```text
Regenerate output page numbers
Preserve source-page mapping in metadata
```

---

# 47. Table of Contents

Jika pagination berubah, daftar isi dapat menjadi tidak akurat.

Mode:

```text
PRESERVE_AS_SOURCE
REGENERATE
MARK_AS_POSSIBLY_OUTDATED
```

Personal MVP initial default:

```text
MARK_AS_POSSIBLY_OUTDATED
```

Automatic TOC regeneration dapat ditambahkan setelah heading dan page mapping stabil.

---

# 48. Hyperlink Reconstruction

External hyperlink:

- visible text dapat diterjemahkan;
- target URL tetap.

Internal hyperlink:

- target harus dipetakan ke target page;
- bookmark mapping harus diperbarui;
- broken link diberi warning.

---

# 49. Bookmark Reconstruction

Bookmark dari PDF sumber dapat dipertahankan jika:

- section mapping tersedia;
- target page diketahui;
- title dapat diterjemahkan.

Bookmark status:

```text
PRESERVED
UPDATED
BROKEN
OMITTED
```

---

# 50. Annotation Handling

Annotation mode:

```text
PRESERVE
OMIT
FLATTEN
```

Default Personal MVP:

```text
PRESERVE_WHEN_SAFE
```

Comment dan form annotation kompleks dapat ditunda.

---

# 51. Cover Handling

Cover default:

```text
PRESERVE_SOURCE
```

Judul pada cover yang berupa text layer dapat diterjemahkan jika:

- pengguna mengaktifkan;
- layout dapat dipertahankan;
- font tersedia.

Jika title menyatu dengan gambar:

```text
PRESERVE_UNCHANGED
```

---

# 52. Multi-Column Layout

Reading order harus ditentukan sebelum reconstruction.

Overlay Mode:

- pertahankan kolom sumber.

Reflow Mode:

- dapat mempertahankan jumlah kolom;
- atau mengubah ke single-column berdasarkan setting.

Default buku dan jurnal:

```text
Preserve source column count where stable
Fallback to single-column if overflow is severe
```

Perubahan column count menghasilkan warning.

---

# 53. Vertical Alignment

Vertical alignment:

```text
TOP
MIDDLE
BOTTOM
BASELINE
```

Table cell dan textbox harus mempertahankan alignment jika memungkinkan.

---

# 54. Rotation

Block rotation harus dipertahankan:

```text
0°
90°
180°
270°
arbitrary angle
```

Arbitrary rotation dapat dirasterisasi jika text placement tidak stabil.

---

# 55. Color Preservation

Text color dipertahankan jika:

- contrast cukup;
- background tetap;
- font mapping tidak mengubah readability.

Jika contrast rendah:

```text
LOW_CONTRAST_WARNING
```

Aplikasi dapat menggunakan fallback warna yang lebih terbaca hanya jika user setting mengizinkan.

---

# 56. Layer Model

Generated page dapat memiliki layers:

```text
SOURCE_BACKGROUND
SOURCE_ASSETS
COVER_REGIONS
TARGET_TEXT
ANNOTATIONS
DEBUG_OVERLAY
```

Debug overlay hanya tersedia pada preview, tidak pada final export.

---

# 57. Debug Reconstruction View

Editor development mode dapat menampilkan:

- source bounding box;
- target bounding box;
- overflow region;
- collision;
- reading order;
- block ID;
- strategy;
- confidence.

Ini penting untuk testing dan debugging Codex.

---

# 58. Collision Detection

Setiap target block dibandingkan terhadap:

- block lain;
- image;
- table;
- page margin;
- header;
- footer.

Collision type:

```text
TEXT_TEXT
TEXT_IMAGE
TEXT_TABLE
TEXT_MARGIN
TABLE_IMAGE
BLOCK_FOOTER
BLOCK_HEADER
```

---

# 59. Collision Severity

```text
INFO
LOW
MEDIUM
HIGH
CRITICAL
```

Critical collision:

- teks tidak dapat dibaca;
- gambar penting tertutup;
- tabel hilang;
- halaman tidak dapat diekspor.

---

# 60. Overflow Detection

Overflow terjadi jika rendered content melebihi:

- width;
- height;
- clipping region;
- page boundary;
- table cell.

Overflow object:

```json
{
  "overflow_id": "overflow_001",
  "block_id": "block_001",
  "axis": "VERTICAL",
  "overflow_points": 24.5,
  "severity": "HIGH",
  "resolved": false
}
```

---

# 61. Layout Validation

Validator minimum:

```text
Text overflow
Text clipping
Text overlap
Image overlap
Missing image
Missing block
Table overflow
Font too small
Out-of-page geometry
Broken footnote
Broken hyperlink
Reading-order mismatch
Unexpected blank page
```

---

# 62. Visual Validation

Visual validation membandingkan source dan target untuk:

- major asset presence;
- page dimensions;
- image count;
- blank regions;
- missing element;
- extreme shift.

Visual validation tidak mengharuskan kesamaan pixel.

---

# 63. Text Validation After Reconstruction

Setelah PDF dibuat:

1. ekstrak text dari output;
2. cocokkan dengan final text inventory;
3. periksa segment completeness;
4. periksa angka;
5. periksa URL;
6. periksa code;
7. periksa page count;
8. periksa glyph.

Jika output text tidak dapat diekstrak karena font atau encoding:

```text
OUTPUT_TEXT_EXTRACTION_FAILED
```

---

# 64. Reconstruction Confidence

Score dapat menggunakan:

```text
Block fit success
Overflow absence
Collision absence
Font readability
Asset preservation
Table integrity
Text completeness
Page mapping stability
```

Contoh bobot:

```text
Text completeness          25%
Overflow and clipping      20%
Collision                  15%
Asset preservation         15%
Table integrity            10%
Font readability           10%
Page mapping                5%
```

---

# 65. Reconstruction Status

```text
NOT_STARTED
PREPARING
MEASURING
LAYING_OUT
RENDERING
VALIDATING
COMPLETED
COMPLETED_WITH_WARNINGS
PARTIALLY_COMPLETED
FAILED
CANCELLED
```

---

# 66. Block Reconstruction Status

```text
PENDING
PLACED
REFLOWED
PRESERVED
RENDERED_AS_IMAGE
OVERFLOW
COLLISION
NEEDS_REVIEW
FAILED
```

---

# 67. Fallback Hierarchy

Jika block gagal:

```text
ORIGINAL STRATEGY
        ↓
ADJUSTED GEOMETRY
        ↓
REDUCED FONT WITHIN LIMIT
        ↓
REFLOW
        ↓
MOVE TO NEXT PAGE
        ↓
ADD PAGE
        ↓
PRESERVE SOURCE REGION
        ↓
MANUAL REVIEW
```

---

# 68. Page-Level Failure Handling

Jika satu halaman gagal:

- simpan halaman lain;
- tandai project partially reconstructed;
- retry halaman;
- gunakan fallback mode;
- jangan mengulang semua halaman kecuali pagination global berubah.

---

# 69. Global Pagination Changes

Jika satu page tambahan mengubah:

- TOC;
- page numbering;
- bookmark;
- internal link;

maka document-level final assembly harus dijalankan ulang.

Page rendering individual tetap dapat digunakan kembali.

---

# 70. Incremental Reconstruction

Cache key:

```text
page_id
page_revision
translation_revision_hash
reconstruction_settings_hash
font_mapping_hash
asset_hash
```

Jika tidak berubah, page output dapat digunakan kembali.

---

# 71. Reconstruction Job Payload

```json
{
  "job_id": "job_001",
  "project_id": "project_001",
  "document_id": "document_001",
  "page_ids": [
    "page_001",
    "page_002"
  ],
  "reconstruction_mode": "HYBRID",
  "settings_version": "0.1",
  "idempotency_key": "example"
}
```

---

# 72. Output Directory

```text
projects/{project_id}/intermediate/reconstruction/
├── pages/
├── overlays/
├── html/
├── images/
├── fonts/
├── reports/
└── assembled/
```

Final:

```text
projects/{project_id}/exports/
```

---

# 73. Output Naming

Format:

```text
{safe-source-name}-id-{version}.pdf
```

Contoh:

```text
system-design-id-v1.pdf
```

Filename harus disanitasi.

---

# 74. Export Profiles

## 74.1 Standard

```text
balanced image quality
embedded fonts where allowed
selectable translated text
standard compression
```

## 74.2 High Quality

```text
higher image resolution
minimal compression
larger file
```

## 74.3 Compact

```text
recompressed images
lower preview resolution
smaller file
```

## 74.4 Bilingual

```text
source and translation
```

Bilingual export dapat ditunda jika memperbesar scope MVP.

---

# 75. Searchable Text Requirement

Translated PDF harus memiliki selectable and searchable text.

Image-only PDF tidak dianggap hasil final normal.

Image-only output hanya boleh menjadi fallback dengan warning:

```text
OUTPUT_RASTERIZED
```

---

# 76. PDF Metadata

Output metadata dapat mencakup:

```text
Title
Author
Subject
Keywords
Source language
Target language
TransLoka version
Reconstruction mode
Creation date
```

Metadata tidak boleh mengklaim pengguna sebagai pemilik hak cipta.

---

# 77. PDF Version

Gunakan PDF version yang kompatibel dengan library output dan PDF reader umum.

Versi final ditentukan saat implementation test.

Hindari fitur PDF yang tidak didukung luas tanpa kebutuhan.

---

# 78. File Integrity

Setelah export:

- buka ulang PDF;
- verifikasi page count;
- hitung checksum;
- periksa corruption;
- ekstrak text sample;
- render halaman sample;
- simpan validation report.

---

# 79. Cancellation

Jika pengguna membatalkan:

- hentikan page baru;
- biarkan atomic page operation selesai;
- simpan page yang valid;
- tandai job cancelled;
- hapus temporary incomplete file;
- jangan menghapus hasil reconstruction lama.

---

# 80. Resource Management

Reconstruction harus membatasi:

- jumlah page render bersamaan;
- image memory;
- temporary file;
- font object;
- HTML page size;
- WeasyPrint process.

Default:

```text
reconstruction concurrency = 1
```

---

# 81. Temporary File Cleanup

Temporary files dapat dihapus setelah:

- final export valid;
- retention period berlalu;
- pengguna memilih cleanup.

Jangan menghapus:

- original;
- final translation;
- approved revisions;
- final exports;
- active reconstruction cache.

---

# 82. Local Security

Reconstruction Engine harus:

- hanya membaca dari data directory;
- hanya menulis ke data directory;
- menolak path traversal;
- menolak remote URL pada HTML;
- menolak `file://` di luar allowed directory;
- menolak arbitrary CSS import;
- tidak menjalankan script;
- tidak menjalankan macro;
- tidak menjalankan embedded PDF JavaScript.

---

# 83. WeasyPrint Resource Policy

HTML reflow hanya boleh memuat:

- approved local images;
- approved local fonts;
- generated CSS;
- generated HTML.

Tidak boleh memuat:

```text
http://
https://
ftp://
arbitrary file://
```

Custom URL fetcher harus membatasi akses.

---

# 84. Reconstruction Settings Schema

```json
{
  "mode": "HYBRID",
  "preserve_page_size": true,
  "preserve_images": true,
  "preserve_headers": true,
  "preserve_footers": true,
  "preserve_page_numbers": true,
  "translate_captions": true,
  "minimum_body_font_pt": 8,
  "maximum_font_reduction_percent": 10,
  "allow_page_addition": true,
  "allow_column_change": false,
  "table_complexity_fallback": "PRESERVE_AS_IMAGE",
  "image_quality": "STANDARD",
  "output_profile": "STANDARD"
}
```

---

# 85. User Review Settings

Sebelum export pengguna dapat memilih:

```text
Preserve original page numbering
Regenerate page numbering
Allow added pages
Use single-column fallback
Preserve complex tables as images
Use high-quality image export
Show layout warnings
Block export on critical errors
```

Default:

```text
Block export on critical errors = true
```

---

# 86. API Endpoints

```text
POST /api/v1/projects/{projectId}/reconstruction/preview
POST /api/v1/projects/{projectId}/reconstruction/start
POST /api/v1/projects/{projectId}/reconstruction/cancel
POST /api/v1/projects/{projectId}/reconstruction/retry
GET  /api/v1/projects/{projectId}/reconstruction/status
GET  /api/v1/projects/{projectId}/reconstruction/warnings
GET  /api/v1/projects/{projectId}/reconstruction/pages/{pageId}
POST /api/v1/projects/{projectId}/exports
```

---

# 87. Database Records

## reconstruction_jobs

```text
id
project_id
document_id
mode
settings_json
status
progress
started_at
completed_at
error_code
created_at
```

## reconstruction_pages

```text
id
job_id
source_page_id
target_page_number
strategy
status
output_path
warning_count
reconstruction_hash
created_at
```

## reconstruction_blocks

```text
id
reconstruction_page_id
block_id
strategy
source_geometry_json
target_geometry_json
fit_strategy
status
warning_count
```

## layout_warnings

```text
id
project_id
page_id
block_id
warning_type
severity
details_json
status
created_at
resolved_at
```

---

# 88. Reconstruction Pseudocode

```text
function reconstruct_document(project_id, settings):
    document = load_document_ir(project_id)
    validate_reconstruction_preconditions(document)

    font_map = resolve_document_fonts(document)

    for page in document.pages:
        strategy = classify_page_strategy(page, settings)

        reconstructed_page = create_target_page(
            page,
            strategy
        )

        for block in page.blocks_by_reading_order:
            block_strategy = classify_block_strategy(
                block,
                strategy,
                settings
            )

            target_text = resolve_final_text(block)

            layout_result = layout_block(
                block,
                target_text,
                font_map,
                block_strategy
            )

            if layout_result.failed:
                layout_result = apply_fallback_chain(
                    block,
                    target_text,
                    layout_result,
                    settings
                )

            save_block_reconstruction(layout_result)

        render_page(reconstructed_page)
        validate_page(reconstructed_page)
        save_reconstructed_page(reconstructed_page)

    output = assemble_document()
    restore_links_and_metadata(output)
    validate_final_pdf(output)

    return output
```

---

# 89. Testing Strategy

## 89.1 Unit Tests

- text measurement;
- expansion ratio;
- font mapping;
- geometry;
- collision;
- overflow;
- fitting strategy;
- page mapping;
- table split;
- filename sanitization.

## 89.2 Integration Tests

- Document IR to overlay;
- Document IR to reflow;
- hybrid reconstruction;
- pypdf merge;
- ReportLab page;
- WeasyPrint export;
- image preservation;
- metadata;
- hyperlinks.

## 89.3 Golden Document Tests

Minimum:

```text
single-column
two-column
image-heavy
table-heavy
code-heavy
footnote-heavy
cover
mixed-layout
scanned-background
```

## 89.4 Visual Regression

Bandingkan:

- page dimension;
- image placement;
- missing block;
- overlap;
- blank page;
- text clipping.

## 89.5 Text Extraction Regression

Ekstrak output PDF dan bandingkan dengan:

- final text inventory;
- number inventory;
- URL inventory;
- code inventory.

---

# 90. Test Assertions

Setiap golden document harus memastikan:

1. PDF dapat dibuka.
2. Jumlah source page tercatat.
3. Seluruh source page terpetakan.
4. Seluruh final text muncul.
5. Gambar utama muncul.
6. Tidak ada critical clipping.
7. Tidak ada critical overlap.
8. Nomor tidak berubah.
9. URL tidak berubah.
10. Code tidak berubah.
11. Output text selectable.
12. Checksum output tersedia.

---

# 91. Quality Targets

Target awal Personal MVP:

```text
Missing translated segment       0%
Missing source page mapping      0%
Missing major image              < 1%
Critical text clipping           0%
Critical overlap                 0%
Output PDF open success          100%
Output text extraction success   ≥ 99%
Simple table reconstruction      ≥ 95%
Standard-page automatic success  ≥ 80%
```

Dokumen kompleks dapat memerlukan manual review.

---

# 92. Acceptance Criteria

Reconstruction Engine siap digunakan jika:

1. Dapat menerima Document IR.
2. Dapat memuat final text.
3. Dapat menjalankan Overlay Mode.
4. Dapat menjalankan Reflow Mode.
5. Dapat menjalankan Hybrid Mode.
6. Dapat mempertahankan source page size.
7. Dapat mempertahankan gambar.
8. Dapat memetakan font.
9. Dapat mengukur target text.
10. Dapat mendeteksi overflow.
11. Dapat mendeteksi collision.
12. Dapat mengurangi font secara terbatas.
13. Dapat memperluas textbox.
14. Dapat memindahkan block.
15. Dapat me-reflow paragraph.
16. Dapat menambahkan halaman.
17. Dapat merekonstruksi simple table.
18. Dapat mempertahankan complex table sebagai image.
19. Dapat mempertahankan code.
20. Dapat mempertahankan formula.
21. Dapat memproses footnote.
22. Dapat mempertahankan hyperlink eksternal.
23. Dapat membuat source-target page mapping.
24. Dapat menghasilkan searchable PDF.
25. Dapat memvalidasi output.
26. Dapat menghasilkan warning.
27. Dapat memproses ulang satu halaman.
28. Dapat membatalkan job.
29. Dapat membersihkan temporary file.
30. Tidak mengubah file sumber.

---

# 93. Recommended Implementation Order

1. Reconstruction settings schema.
2. Page strategy classifier.
3. Block strategy classifier.
4. Font resolver.
5. Text measurement.
6. ReportLab overlay generator.
7. pypdf page merge.
8. Basic overflow detector.
9. Basic collision detector.
10. Image preservation.
11. Page assembly.
12. Final PDF validation.
13. WeasyPrint reflow.
14. Hybrid page support.
15. Table reconstruction.
16. Page addition.
17. Page mapping.
18. Footnote support.
19. Hyperlink restoration.
20. Incremental reconstruction cache.
21. Visual regression tests.
22. Advanced fitting strategies.

---

# 94. Open Decisions

1. Default fallback fonts.
2. Maximum font reduction final.
3. Minimum readable font sizes final.
4. Whether original page is preserved as vector or raster fallback.
5. Source text removal technique per PDF type.
6. Background color detection method.
7. Whether table cell content may reduce font more than body text.
8. How additional pages are numbered.
9. Whether TOC regeneration enters Personal MVP.
10. How internal links are remapped.
11. Whether bilingual export enters Personal MVP.
12. Whether page-specific mode can be edited manually.
13. Whether complex table OCR is reconstructed or preserved.
14. Whether annotation is preserved.
15. Whether PDF forms are flattened.
16. Whether source bookmarks are translated.
17. Whether font download is allowed.
18. Whether accessibility tags are preserved.
19. Whether cover title translation is enabled.
20. Whether output PDF/A is required.

---

# 95. Definition of Done

Implementasi Reconstruction Engine dinyatakan selesai apabila:

- Overlay Mode menghasilkan PDF valid;
- Reflow Mode menghasilkan PDF valid;
- Hybrid Mode dapat memilih strategi per block;
- gambar sumber dapat dipertahankan;
- final text dapat ditempatkan;
- overflow dapat dideteksi;
- collision dapat dideteksi;
- fallback dapat dijalankan;
- simple table dapat direkonstruksi;
- complex table dapat dipertahankan secara aman;
- halaman tambahan dapat dibuat;
- page mapping tersedia;
- text hasil dapat dicari;
- final PDF dapat dibuka;
- output tidak mengubah file asli;
- automated test utama lulus;
- critical layout error dapat memblokir export.
