## Quick Start

1. Run `start.bat` — this launches the backend (FastAPI on port 8001) and the frontend (Vite on port 5173).
2. Open `http://localhost:5173` in your browser.
3. Click **New Project** and enter a project name.
4. Click **Import Resource** to upload your `.tsv` / `.ttf` / `.otf` resource files.
5. Click **Parse Resources** to compile block and attribute files. Check the bottom panel for any errors or warnings.
6. Configure per-block settings in the left panel (Print, Columns, Format, Title page, Font sources).
7. Click **Check Proofs** to validate all printable blocks. If the button turns green, proofs pass.
8. Click **Generate PDF** to produce PDF output files in the project's `pdf/` folder.

### Block Information

```plaintext
# {initial code point end with 0}..{final code point end with F}; {block name}; {W for Working set, H for Han, V for IVD, C for non-Han Character (not inplemented)}

{
if is W for Working set,
{serial number} \t {source reference} \t {code point in font file, default for assigned code point calculated from initial code point and serial number}
else if is H for Han,
format in Unihan_IRGSources.txt
else if is V for IVD,
{character code point} space {variation selector code point} \t {collection name} \t {source reference}
else if is C for non-Han Character,
{code point} \t {character name}
}

# eof
```

Examples (`\t` should be replaced with a real tab):

```plaintext
# 2EBF0..2EE5F; CJK Unified Ideograph Extension I; W

00001 \t GIDC23-001 \t U+E000
00002 \t GIDC23-003 \t U+E002
00003 \t GIDC23-004 \t U+E003
00004 \t GIDC23-264 \t U+E107
00005 \t GIDC23-005 \t U+E004

# eof
```

```plaintext
# 4E00..4EFF; CJK Unified Ideographs; H

U+4E00 \t kIRG_GSource \t G0-523B
U+4E00 \t kIRG_HSource \t HB1-A440
U+4E00 \t kIRG_JSource \t J0-306C
U+4E00 \t kIRG_KPSource \t KP0-FCD6
U+4E00 \t kIRG_KSource \t K0-6C69

# eof
```

```plaintext
# 111E0..111FF; Sinhala Archaic Numbers; C

111E1 \t SINHALA ARCHAIC DIGIT ONE
111E2 \t SINHALA ARCHAIC DIGIT TWO
111E3 \t SINHALA ARCHAIC DIGIT THREE
111E4 \t SINHALA ARCHAIC DIGIT FOUR
111E5 \t SINHALA ARCHAIC DIGIT FIVE
111E6 \t SINHALA ARCHAIC DIGIT SIX

# eof
```

```plaintext
# 4E00..9FFF; Obsolete Draft of TH-Ming; V

4E00 E01E5 \t PanCJK \t 4E00-V
4E00 E01E6 \t PanCJK \t 4E00-KP
4E00 E01E7 \t PanCJK \t 4E00-K
4E00 E01E8 \t PanCJK \t 4E00-J
4E01 E01E5 \t PanCJK \t 4E01-V
4E01 E01E6 \t PanCJK \t 4E01-KP
4E01 E01E7 \t PanCJK \t 4E01-K
4E01 E01E8 \t PanCJK \t 4E01-J

# eof
```

### Attribute Information

```plaintext
# {initial code point end with 0}..{final code point end with F}; {block name}; {RSW for Radical-Stroke in Working set, RSH for Radical-Stroke in Han, NL for NameList (not inplemented)}

{
if is RSW for Radical-Stroke in Working set,
{serial number} \t {radical-stroke splited by space}
else if is RSH for Radical-Stroke in Han,
{U+code point} \t {radical-stroke splited by space}
else if is NL for NameList,
format in NamesList.txt
}

# eof
```

Examples (`\t` should be replaced with a real tab):

```plaintext
# 2EBF0..2EE5F; CJK Unified Ideograph Extension I; RSW

00001 \t 1.3 7.2
00002 \t 3.4 137.-1
00003 \t 4.3 93.0
00004 \t 8.12 86.10
00005 \t 9.2

# eof
```

```plaintext
# 30000..3134F; CJK Unified Ideographs Extension G; RSH

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
