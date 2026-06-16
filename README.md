# Unipage — Unicode Code Chart PDF Generator

Generate print-ready Unicode code charts from structured TSV data and
OpenType/TrueType fonts.  Supports both **CJK** (Han ideographs, IVD,
working-set blocks) and **non‑CJK** (NamesList‑based standard blocks)
code charts using a shared fpdf2 rendering engine.

## Quick Start

1. Run `start.bat` — this launches the backend (FastAPI on port 8001) and
   the frontend (Vite on port 5173).
2. Open `http://localhost:5173` in your browser.
3. Click **New Project** and enter a project name.
4. Click **Import Resource** to upload your `.tsv` / `.ttf` / `.otf`
   resource files.
5. Click **Parse Resources** to compile block and attribute files.
   Check the bottom panel for any errors or warnings.
6. Configure per-block settings in the left panel (Print, Columns,
   Format, Title page, Font sources).
7. Click **Check Proofs** to validate all printable blocks.
   If the button turns green, proofs pass.
8. Click **Generate PDF** to produce PDF output files in the project's
   `pdf/` folder.

## Section types

A single `.tsv` file can contain multiple sections, each introduced by a
`#` header line.  The third field of the header is the **type code**.

### Block sections (→ `BlockInfo`)

| Code   | Description | Pipeline |
|--------|-------------|----------|
| `RF-W` | Working set (serial‑numbered source glyphs) | CJK |
| `RF-H` | Han (Unihan IRG sources) | CJK |
| `RF-V` | IVD / variation sequences | CJK |

### Attribute sections (→ `inf_cont` in resource parse data)

| Code   | Description | Pipeline |
|--------|-------------|----------|
| `RS-W` | Radical‑Stroke, Working set (serial → RS values) | CJK |
| `RS-H` | Radical‑Stroke, Han (codepoint → RS values) | CJK |
| `NL`   | NamesList (standard Unicode NamesList.txt format) | non‑CJK |
| `CD`   | Character Data (UnicodeData.txt format) | non‑CJK |
| `FT`   | Font Table (CFL — Character Font List format) | non‑CJK |

### Block Information

```plaintext
# {start_cp:04X}..{end_cp:04X}; {block name}; {type code}
;   codepoints are zero‑padded hex (4 digits for BMP, 5–6 for SMP/SIP)

{
if RF-W (Working set):
  {serial number} \t {source reference} \t {PUA code point in font}
if RF-H (Han):
  format in Unihan_IRGSources.txt
if RF-V (IVD):
  {base cp} SP {selector cp} \t {collection name} \t {source reference}
}

# eof
```

Examples (`\t` should be replaced with a real tab):

```plaintext
# 2EBF0..2EE5F; CJK Unified Ideographs Extension I; RF-W

00001 \t GIDC23-001 \t U+E000
00002 \t GIDC23-003 \t U+E002
00003 \t GIDC23-004 \t U+E003
00004 \t GIDC23-264 \t U+E107
00005 \t GIDC23-005 \t U+E004

# eof
```

```plaintext
# 4E00..9FFF; CJK Unified Ideographs; RF-H

U+4E00 \t kIRG_GSource \t G0-523B
U+4E00 \t kIRG_HSource \t HB1-A440
U+4E00 \t kIRG_JSource \t J0-306C
U+4E00 \t kIRG_KPSource \t KP0-FCD6
U+4E00 \t kIRG_KSource \t K0-6C69

# eof
```

```plaintext
# F0000..FFFFD; CJK Compatibility Ideographs Supplement; RF-V

F0000 E0100 \t PanCJK \t F0000-V
F0000 E0101 \t PanCJK \t F0000-KP
F0000 E0102 \t PanCJK \t F0000-K
F0000 E0103 \t PanCJK \t F0000-J
F0001 E0100 \t PanCJK \t F0001-V
F0001 E0101 \t PanCJK \t F0001-KP
F0001 E0102 \t PanCJK \t F0001-K
F0001 E0103 \t PanCJK \t F0001-J

# eof
```

```plaintext
# 0000..007F; Basic Latin; NL

@@ \t 0000 \t Basic Latin \t 007F
@ \t \t C0 controls
0000 \t <control>
0001 \t <control>
@ \t \t ASCII punctuation and symbols
0020 \t SPACE
0021 \t EXCLAMATION MARK
0022 \t QUOTATION MARK
@ \t \t ASCII digits
0030 \t DIGIT ZERO
0031 \t DIGIT ONE
@ \t \t Uppercase Latin alphabet
0041 \t LATIN CAPITAL LETTER A
0042 \t LATIN CAPITAL LETTER B
0043 \t LATIN CAPITAL LETTER C
\t x (latin small letter a - 0061)
\t x (latin small letter b - 0062)
\t x (latin small letter c - 0063)
@ \t \t Lowercase Latin alphabet
0061 \t LATIN SMALL LETTER A
0062 \t LATIN SMALL LETTER B
0063 \t LATIN SMALL LETTER C

# eof
```

### Attribute Information

```plaintext
# {start_cp:04X}..{end_cp:04X}; {section name}; {type code}
;   codepoints are zero‑padded hex (4 digits for BMP, 5–6 for SMP/SIP)

{
if RS-W (Radical-Stroke, Working set):
  {serial number} \t {radical-stroke values separated by space}
if RS-H (Radical-Stroke, Han):
  {U+code point} \t {key} \t {radical-stroke value}
if NL (NamesList):
  format in NamesList.txt
if CD (Character Data):
  format in UnicodeData.txt
if FT (Font Table):
  format in CFL (Character Font List)
}
;   NL / CD / FT are parsed by the shared parser in non_cjk_generation.parsers

# eof
```

Examples (`\t` should be replaced with a real tab):

```plaintext
# 2EBF0..2EE5F; CJK Unified Ideographs Extension I; RS-W

00001 \t 1.3 7.2
00002 \t 3.4 137.-1
00003 \t 4.3 93.0
00004 \t 8.12 86.10
00005 \t 9.2

# eof
```

```plaintext
# 30000..3134F; CJK Unified Ideographs Extension G; RS-H

U+30000 \t kRSUnicode \t 1.1
U+30001 \t kRSUnicode \t 1.2
U+30002 \t kRSUnicode \t 1.2
U+30003 \t kRSUnicode \t 1.2
U+30004 \t kRSUnicode \t 1.2

# eof
```

```plaintext
# 111E0..111FF; Sinhala Archaic Numbers; NL

@@ \t 111E0 \t Sinhala Archaic Numbers \t 111FF
@+ \t \t This number system is also known as Sinhala Illakkam. This number system does not have a zero place holder concept, unlike the Sinhala astrological numbers, Sinhala Lith Illakkam, encoded in the range 0DE6-0DEF.
@ \t \t Historical digits
111E1 \t SINHALA ARCHAIC DIGIT ONE
111E2 \t SINHALA ARCHAIC DIGIT TWO
111E3 \t SINHALA ARCHAIC DIGIT THREE
111E4 \t SINHALA ARCHAIC DIGIT FOUR

# eof
```

```plaintext
# 0000..FFFF; Unicode Character Database; CD

0000;NULL;Cc;0;BN;;;;;N;;;;;
0041;LATIN CAPITAL LETTER A;Lu;0;L;;;;;N;;;;0061;
0042;LATIN CAPITAL LETTER B;Lu;0;L;;;;;N;;;;0062;
0043;LATIN CAPITAL LETTER C;Lu;0;L;;;;;N;;;;0063;
0300;COMBINING GRAVE ACCENT;Mn;230;NSM;;;;;N;NON-SPACING GRAVE;;;;
0301;COMBINING ACUTE ACCENT;Mn;230;NSM;;;;;N;NON-SPACING ACUTE;;;;

# eof
```

```plaintext
# 0020..007F; Basic Latin Fonts; FT

; ---- Common fonts (used for all blocks) ----
OpenSans-Regular, 22, /R=0020-007F
LiberationSerif-Regular, 20, /R=0020-007F, /Q=F0000

; ---- Variation Selectors block (FE00–FE0F) ----
OpenSans-Regular, 18, /R=FE00-FE0F
LiberationSerif-Regular, 16, /R=FE00-FE0F, /X=FE00-FE01

# eof
```

## Architecture

```
backend/
├── cjk_generation/          CJK code-chart pipeline
│   ├── layout.py            Computes glyph placement per page (→ ProofLayout)
│   ├── pdf_builder.py       Produces PDF via fpdf2 (shared engine)
│   ├── svg_builder.py       Extracts glyph outlines from fonts as SVG
│   └── fonts.py             fpdf2 font-name ↔ family mapping
├── non_cjk_generation/      Non‑CJK (NamesList) code-chart pipeline
│   ├── layout.py            Title page, chart grid, info-section layout
│   ├── renderer.py          PDF output via fpdf2 (font registration, drawing)
│   ├── parsers.py           CFL + NamesList parsers (full Unicode spec)
│   └── models.py            Page / TextSpan / Drawing data model
├── file_management/         Resource parsing & validation
│   ├── parser.py            TSV block / attribute parsers
│   └── resource_manager.py  Build blocks, merge data, manage settings
├── models/                  Shared data classes (Project, ProofLayout, …)
└── api/                     FastAPI routes (CJK + non‑CJK endpoints)
```

### Shared components

- **fpdf2** — both CJK and non-CJK pipelines use the same PDF engine.
  CJK glyphs are rendered by converting SVG outlines to PNG via cairosvg,
  then embedding with `pdf.image()`.
- **NamesList parser** (`non_cjk_generation/parsers.py`) — used by both
  the non‑CJK pipeline and the NL attribute parser in `file_management`.
- **Page / TextSpan / Drawing model** (`non_cjk_generation/models.py`) —
  shared data format for layout computation and rendering.
- **Title page, header, footer** — CJK and non‑CJK charts share the same
  layout code (`compute_title_page`, header/footer rects, copyright line).
