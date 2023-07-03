### Usage

1. Create a project folder like `../prj/`.
2. Run `src > unipage.py`.
3. Create a project (`Ctrl + N` or click `新建项目`) by filling in the the project name (`项目名称`) and the project path (`项目路径`, like `../prj/`). The project file will be `../prj/{project name}.upj`.
4. Import the resources (click `导入资源`) by selecting the resources (in `*.att` attribute file, `*.blk` block file and font file). Files with unrecognized types are ignored.
5. Parse the resources (`F5` or click `解析资源`) and see the compilation results (errors, warnings, information). If errors and warnings exist, you can revise and save the files and parse again.
6. Finish the settings (`Left` and `Right` to change option).
7. Preprint check (click `印前检查`) and see the compilation results. If errors and warnings exist, you can revise the settings and check again (SVG files will be generated in `../prj/svg/` folder).
8. Print (click `打印`) and get the PDF file in `../prj/pdf/{block name}.pdf`.

### Block Information

```plaintext
# {initial code point end with 0}..{final code point end with F}; {block name}; {W for Working set, H for Han, C for non-Han Character (not inplemented)}

{
if is W for Working set,
{serial number} \t {source reference} \t {code point in font file, default for assigned code point calculated from initial code point and serial number}
else if is H for Han,
format in Unihan_IRGSources.txt
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

U+30000 \t 1.1
U+30001 \t 1.2
U+30002 \t 1.2
U+30003 \t 1.2
U+30004 \t 1.2

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
