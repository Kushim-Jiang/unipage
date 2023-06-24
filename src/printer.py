from copy import deepcopy
from datetime import datetime
from math import ceil
from os import makedirs
from os.path import basename, dirname, exists
from re import sub
from textwrap import dedent

from fontTools import ttLib
from fontTools.pens import boundsPen, svgPathPen
from numpy import mean
from reportlab.graphics import renderPDF, shapes
from reportlab.pdfbase import pdfmetrics, ttfonts
from reportlab.pdfgen import canvas
from svglib.svglib import svg2rlg

from current import Current
from rsc_parser import UniException, _show_rs, _subsrc_name, _subsrc_no


def _build_svg(pages: list) -> dict | tuple[str, str]:
    if not exists(dirname(Current.project.prj_basic_info["project_dir"] + "/svg/")):
        makedirs(dirname(Current.project.prj_basic_info["project_dir"] + "/svg/"))

    glyph_set = set()
    glyph_dict = dict()
    for page in pages:
        for i in range(len(page[2])):
            if page[2][i].__class__.__name__ == "int":
                glyph_set.add(tuple([page[2][i], tuple(page[4][i])]))
            elif page[2][i].__class__.__name__ == "list":
                glyph_set.add(tuple([tuple(page[2][i]), tuple(page[4][i])]))
            elif page[2][i].__class__.__name__ == "tuple":
                glyph_set.add(tuple([page[2][i], tuple(page[4][i])]))

    cp_count = 0
    for fnt in set([item[1] for item in glyph_set if item != ("", "")]):
        cp_count += len([item[0] for item in glyph_set if item[1] == fnt])

    cp_index = 0
    # fnt: (name, url)
    for fnt in set([item[1] for item in glyph_set if item != ("", "")]):
        cps = [item[0] for item in glyph_set if item[1] == fnt]
        fnt_width = []
        try:
            font = ttLib.TTFont(fnt[1])
            font_cmap = font.getBestCmap()
            font_glyph_set = font.getGlyphSet()
            bounds_pen = boundsPen.BoundsPen(font_glyph_set)
            for cp in cps:
                if cp.__class__.__name__ == "int":
                    cp_str = "‹" + str(cp) + " (" + hex(cp).upper().replace("0X", "") + ")›"
                    glyph_name = font_cmap[cp]
                elif cp.__class__.__name__ in ["list", "tuple"]:
                    cp_str = (
                        "‹" + str(cp[1]) + " (" + hex(cp[1]).upper().replace("0X", "") + "), " + str(cp[0]) + " (" + hex(cp[0]).upper().replace("0X", "") + ")›"
                    )
                    glyph_name = [tu for tu in font["cmap"].getcmap(0, 5).uvsDict[cp[0]] if tu[0] == cp[1]][0][1]
                    if glyph_name == None:
                        glyph_name = font_cmap[cp[1]]

                glyph = font_glyph_set[glyph_name]
                svg_pen = svgPathPen.SVGPathPen(font_glyph_set)
                glyph.draw(svg_pen)
                glyph.draw(bounds_pen)
                ascender = font["OS/2"].sTypoAscender
                descender = font["OS/2"].sTypoDescender
                width = glyph.width
                fnt_width.append(width)
                height = ascender - descender
                content = dedent(
                    f"""\
                        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 {-ascender} {width} {height}">
                            <g transform="scale(1, -1)">
                                <path d="{svg_pen.getCommands()}"/>
                            </g>
                        </svg>
                    """
                )
                file_name = sub(r"\.", "_", basename(fnt[1]).strip()) + "_" + sub(r"\.", "_", glyph_name.strip()) + ".svg"
                with open(Current.project.prj_basic_info["project_dir"] + "/svg/" + file_name, "w") as fp:
                    fp.write(content)
                glyph_dict[(cp, fnt)] = (Current.project.prj_basic_info["project_dir"] + "/svg/" + file_name, width)

                cp_index += 1
                Current.unipage.ui.bar.setValue(20 + 80 * cp_index / cp_count)
        except Exception as exc:
            if exc.__class__.__name__ in ["KeyError", "AttributeError"]:
                return (fnt[0], cp_str)
            elif exc.__class__.__name__ == "FileNotFoundError":
                raise UniException([0, "C009", None, fnt[0]])
        if fnt_width:
            glyph_dict[("fix", fnt)] = (bounds_pen.bounds[3] - bounds_pen.bounds[1]) / 2 / mean(fnt_width) - 0.25
        bounds_pen.init()
    return glyph_dict


def make_pdf(proof: dict):
    if not exists(dirname(Current.project.prj_basic_info["project_dir"] + "/pdf/")):
        makedirs(dirname(Current.project.prj_basic_info["project_dir"] + "/pdf/"))

    date_str = str(datetime.today().date())
    column_count = int(ceil(proof["char_count"] / 20))
    row_count = int(proof["char_count"] / column_count)
    col_count = {24: 4, 40: 6, 60: 3, 80: 2, 100: 1}[proof["char_count"]]

    file_pointer = open(Current.project.prj_basic_info["project_dir"] + "/pdf/" + proof["blk_name"] + ".pdf", "w+")
    file_pointer.close()
    dw = shapes.Drawing(612, 792)
    cv = canvas.Canvas(Current.project.prj_basic_info["project_dir"] + "/pdf/" + proof["blk_name"] + ".pdf")

    pdfmetrics.registerFont(ttfonts.TTFont("Noto Sans Regular", "src/fonts/NotoSans-Regular.ttf"))
    pdfmetrics.registerFont(ttfonts.TTFont("Noto Sans Black", "src/fonts/NotoSans-Black.ttf"))
    pdfmetrics.registerFont(ttfonts.TTFont("Noto Sans Italic", "src/fonts/NotoSans-Italic.ttf"))
    pdfmetrics.registerFont(ttfonts.TTFont("Noto Sans Extra Condensed", "src/fonts/NotoSans-ExtraCondensed.ttf"))
    pdfmetrics.registerFont(ttfonts.TTFont("Noto Sans Light", "src/fonts/NotoSans-Light.ttf"))

    font_set = set()
    for page in proof["print_pages"]:
        for font in page[4]:
            font_set.add(font)
    font_set.remove("")
    for font in font_set:
        pdfmetrics.registerFont(ttfonts.TTFont(font[0], font[1]))

    # ==================================
    # ========  draw first page ========
    # ==================================
    if proof["page_title"]:
        first_page = [
            [proof["blk_name"], 80, 80, 11, "Noto Sans Black"],
            [
                "Range: " + hex(proof["blk_initcp"]).upper().replace("0X", "") + " – " + hex(proof["blk_finacp"]).upper().replace("0X", ""),
                0,
                13,
                9,
                "Noto Sans Black",
            ],
            ["This file contains the codepoints, the reference glyphs and the other information of characters in", 0, 20, 9, "Noto Sans Light"],
        ]
        if proof["char_count"] != 24:
            first_page.append(["the blocks.", 0, 11, 9, "Noto Sans Light"])
        else:
            first_page.append(["the database.", 0, 11, 9, "Noto Sans Light"])
        first_page += [
            ["Disclaimer", 0, 23, 9, "Noto Sans Black"],
            ["These charts are intended to show the distribution of the codespace and partial information of the", 0, 13, 9, "Noto Sans Light"],
            ["characters only, and do not indicate the character set model and exact understanding of each", 0, 11, 9, "Noto Sans Light"],
            ["character for the scripts involved. For a complete understanding of the use of the characters", 0, 11, 9, "Noto Sans Light"],
            ["contained in this file, please consult the specification, the technical notes, the annexes", 0, 11, 9, "Noto Sans Light"],
            ["or the proposals associated.", 0, 11, 9, "Noto Sans Light"],
        ]
        first_page += [
            ["Fonts", 0, 23, 9, "Noto Sans Black"],
            ["The shapes of the reference glyphs used in these code charts are not prescriptive. Considerable", 0, 13, 9, "Noto Sans Light"],
            ["variation is to be expected in actual fonts. The particular fonts used in these charts are shown below:", 0, 11, 9, "Noto Sans Light"],
            ["", 30, 8, 9, "Noto Sans Light"],
        ]
        for font in font_set:
            first_page += [
                [ttLib.TTFont(font[1])["name"].getBestFullName(), -15, 11, 9, "Noto Sans Regular"],
                [ttLib.TTFont(font[1])["name"].names[5].toBytes().decode(ttLib.TTFont(font[1])["name"].names[5].getEncoding()), 15, 11, 9, "Noto Sans Light"],
            ]
        first_page += [["", -30, 3, 9, "Noto Sans Light"]]
        first_page += [
            ["Terms of Use", 0, 23, 9, "Noto Sans Black"],
            ["The code charts are compiled and printed by Unibook software, which does not retain copyright on", 0, 13, 9, "Noto Sans Light"],
            ["the production process. The fonts and font data used in production of these code charts may NOT be", 0, 11, 9, "Noto Sans Light"],
            ["extracted, or used in any other way in any product or publication, without permission or license", 0, 11, 9, "Noto Sans Light"],
            ["granted by the typeface owner(s).", 0, 11, 9, "Noto Sans Light"],
        ]

        writer = (0, 0)
        for line in first_page:
            writer = (writer[0] + line[1], writer[1] + line[2])
            dw.add(shapes.String(writer[0], 792 - writer[1], line[0], textAnchor="start", fillColor="black", fontName=line[4], fontSize=line[3]))

        try:
            renderPDF.draw(dw, cv, 0, 0, showBoundary=False)
        except Exception as _:
            pass

        dw = shapes.Drawing(612, 792)
        cv.showPage()

    # ===================================
    # ========  draw code charts ========
    # ===================================
    for page in range(0, len(proof["print_pages"])):
        Current.unipage.ui.bar.setValue(int(100 * page / len(proof["print_pages"])))
        page_type = proof["page_class"][divmod(page, 2)[1]]

        # =============================
        # ========  draw block ========
        # =============================
        left_x, right_x = 82.80, 529.20
        up_y, down_y = 76.74, 733.08
        block_x = [round(left_x + i * (right_x - left_x) / column_count, 2) for i in range(column_count + 1)]
        # special for char_count == 40
        title_x = [101.96, 166.66, 226.34, 257.52, 287.49, 325.16, 389.86, 449.54, 480.72, 510.69]
        title_y = 90.24
        format_shift = 15.96
        if page_type == "Left":
            title_x = [round(x - format_shift, 2) for x in title_x]
            block_x = [round(x - format_shift, 2) for x in block_x]
        elif page_type == "Right":
            title_x = [round(x + format_shift, 2) for x in title_x]
            block_x = [round(x + format_shift, 2) for x in block_x]

        if proof["char_count"] != 24:
            if proof["print_pages"][page][0][0]:
                dw.add(shapes.Line(block_x[0], 792 - (up_y - 0.5), block_x[0], 792 - (down_y + 0.5), strokeColor="black", strokeWidth=1))
            for i in range(column_count):
                if proof["print_pages"][page][0][row_count * i]:
                    dw.add(shapes.Line(block_x[i + 1], 792 - (up_y - 0.5), block_x[i + 1], 792 - (down_y + 0.5), strokeColor="black", strokeWidth=1))
                    dw.add(shapes.Line(block_x[i], 792 - up_y, block_x[i + 1], 792 - up_y, strokeColor="black", strokeWidth=1))
                    dw.add(shapes.Line(block_x[i], 792 - down_y, block_x[i + 1], 792 - down_y, strokeColor="black", strokeWidth=1))
                    if proof["char_count"] == 40:
                        dw.add(shapes.Line(block_x[i], 792 - title_y, block_x[i + 1], 792 - title_y, strokeColor="black", strokeWidth=1))
                        dw.add(
                            shapes.String(
                                title_x[5 * i + 0], 792 - 86.88, "HEX", textAnchor="middle", fillColor="black", fontName="Noto Sans Regular", fontSize=11
                            )
                        )
                        dw.add(
                            shapes.String(
                                title_x[5 * i + 1], 792 - 86.88, "C", textAnchor="middle", fillColor="black", fontName="Noto Sans Regular", fontSize=11
                            )
                        )
                        dw.add(
                            shapes.String(
                                title_x[5 * i + 2], 792 - 86.88, "J", textAnchor="middle", fillColor="black", fontName="Noto Sans Regular", fontSize=11
                            )
                        )
                        dw.add(
                            shapes.String(
                                title_x[5 * i + 3], 792 - 86.88, "K", textAnchor="middle", fillColor="black", fontName="Noto Sans Regular", fontSize=11
                            )
                        )
                        dw.add(
                            shapes.String(
                                title_x[5 * i + 4], 792 - 86.88, "V", textAnchor="middle", fillColor="black", fontName="Noto Sans Regular", fontSize=11
                            )
                        )

        # =============================
        # ========  draw title ========
        # =============================
        head_x = [83.33, 306.77, 530.21, 538.04]
        head_y = [45, 749, 772]
        if page_type == "Left":
            head_x = [round(x - format_shift, 2) for x in head_x]
        elif page_type == "Right":
            head_x = [round(x + format_shift, 2) for x in head_x]

        dw.add(shapes.String(head_x[1], 792 - head_y[0], proof["blk_name"], textAnchor="middle", fillColor="black", fontName="Noto Sans Black", fontSize=11))
        dw.add(
            shapes.String(
                head_x[0], 792 - head_y[0], proof["print_pages"][page][5], textAnchor="start", fillColor="black", fontName="Noto Sans Black", fontSize=11
            )
        )
        dw.add(
            shapes.String(
                head_x[2], 792 - head_y[0], proof["print_pages"][page][6], textAnchor="end", fillColor="black", fontName="Noto Sans Black", fontSize=11
            )
        )
        dw.add(
            shapes.String(
                head_x[3],
                792 - head_y[1],
                "Printed by Unipage, " + date_str + ".",
                textAnchor="end",
                fillColor="black",
                fontName="Noto Sans Italic",
                fontSize=9,
            )
        )
        dw.add(
            shapes.String(
                head_x[1], 792 - head_y[2], "—  " + str(page + 1) + "  —", textAnchor="middle", fillColor="black", fontName="Noto Sans Regular", fontSize=9
            )
        )

        # ===============================
        # ========  draw content ========
        # ===============================
        # non-IVD: codepoint_x, srcref, glyph
        nonivd_first_x = [101.96, 137.96, 127.96]
        # IVD: codepoint_x, srcref, glyph
        ivd_first_x = [90, 142.40, 132]
        if page_type == "Left":
            nonivd_first_x = [round(x - format_shift, 2) for x in nonivd_first_x]
            ivd_first_x = [round(x - format_shift, 2) for x in ivd_first_x]
        elif page_type == "Right":
            nonivd_first_x = [round(x + format_shift, 2) for x in nonivd_first_x]
            ivd_first_x = [round(x + format_shift, 2) for x in ivd_first_x]
        # non-IVD: srcref, codepoint, radical-stroke, glyph
        nonivd_first_y = [116, 98, 108, 106]
        # IVD: selector, charset, glyphID, codepoint, glyph
        ivd_first_y = [124, 131, 138, 107, 114]
        if proof["char_count"] == 40:
            # non-IVD: main
            nonivd_first_y = [round(x + 8, 2) for x in nonivd_first_y]
        nonivd_subsrc_gap_x = {24: 45, 40: 30.11, 60: 35, 80: 35, 100: 0}[proof["char_count"]]
        nonivd_row_gap_y = 31.8
        ivd_row_gap_y = 54
        nonivd_rs_gap_y = 7
        ivd_block_gap_x = 243

        for block_index in range(0, column_count):
            for line_index in range(0, row_count):
                if proof["char_count"] != 24:
                    # non-IVD codepoint
                    dw.add(
                        shapes.String(
                            nonivd_first_x[0] + block_index * (right_x - left_x) / column_count,
                            792 - (nonivd_first_y[1] + line_index * nonivd_row_gap_y),
                            str(proof["print_pages"][page][0][line_index + block_index * row_count]),
                            textAnchor="middle",
                            fillColor="black",
                            fontName="Noto Sans Regular",
                            fontSize=10,
                        )
                    )
                    # non-IVD radical-stroke
                    for rs_index in range(0, len(proof["print_pages"][page][1][line_index + block_index * row_count])):
                        dw.add(
                            shapes.String(
                                nonivd_first_x[0] + block_index * (right_x - left_x) / column_count,
                                792 - (nonivd_first_y[2] + line_index * nonivd_row_gap_y + rs_index * nonivd_rs_gap_y),
                                _show_rs(proof["print_pages"][page][1][line_index + block_index * row_count][rs_index]),
                                textAnchor="middle",
                                fillColor="black",
                                fontName="Noto Sans Extra Condensed",
                                fontSize=6,
                            )
                        )
                else:
                    # IVD codepoint
                    dw.add(
                        shapes.String(
                            ivd_first_x[0] + block_index * ivd_block_gap_x,
                            792 - (ivd_first_y[3] + line_index * ivd_row_gap_y),
                            str(proof["print_pages"][page][0][line_index + block_index * row_count]),
                            textAnchor="middle",
                            fillColor="black",
                            fontName="Noto Sans Regular",
                            fontSize=10,
                        )
                    )
                for source_index in range(0, col_count):
                    if proof["char_count"] == 24:
                        if proof["print_pages"][page][2][source_index + line_index * col_count + block_index * row_count * col_count] != "":
                            # IVD content
                            dw.add(
                                shapes.String(
                                    ivd_first_x[1] + source_index * nonivd_subsrc_gap_x + block_index * ivd_block_gap_x,
                                    792 - (ivd_first_y[0] + line_index * ivd_row_gap_y),
                                    hex(proof["print_pages"][page][2][source_index + line_index * col_count + block_index * row_count * col_count][0])
                                    .upper()
                                    .replace("0X", ""),
                                    textAnchor="middle",
                                    fillColor="black",
                                    fontName="Noto Sans Regular",
                                    fontSize=6,
                                )
                            )
                        if proof["print_pages"][page][3][source_index + line_index * col_count + block_index * row_count * col_count] != "":
                            dw.add(
                                shapes.String(
                                    ivd_first_x[1] + source_index * nonivd_subsrc_gap_x + block_index * ivd_block_gap_x,
                                    792 - (ivd_first_y[1] + line_index * ivd_row_gap_y),
                                    proof["print_pages"][page][3][source_index + line_index * col_count + block_index * row_count * col_count][1],
                                    textAnchor="middle",
                                    fillColor="black",
                                    fontName="Noto Sans Extra Condensed",
                                    fontSize=6,
                                )
                            )
                            dw.add(
                                shapes.String(
                                    ivd_first_x[1] + source_index * nonivd_subsrc_gap_x + block_index * ivd_block_gap_x,
                                    792 - (ivd_first_y[2] + line_index * ivd_row_gap_y),
                                    proof["print_pages"][page][3][source_index + line_index * col_count + block_index * row_count * col_count][0],
                                    textAnchor="middle",
                                    fillColor="black",
                                    fontName="Noto Sans Extra Condensed",
                                    fontSize=6,
                                )
                            )
                    else:
                        # non-IVD srcref
                        dw.add(
                            shapes.String(
                                nonivd_first_x[1] + source_index * nonivd_subsrc_gap_x + block_index * (right_x - left_x) / column_count,
                                792 - (nonivd_first_y[0] + line_index * nonivd_row_gap_y),
                                proof["print_pages"][page][3][source_index + line_index * col_count + block_index * col_count * row_count],
                                textAnchor="middle",
                                fillColor="black",
                                fontName="Noto Sans Extra Condensed",
                                fontSize=6,
                            )
                        )

        try:
            renderPDF.draw(dw, cv, 0, 0, showBoundary=False)
        except Exception as _:
            pass

        # =============================
        # ========  draw glyph ========
        # =============================
        for block_index in range(0, column_count):
            for line_index in range(0, row_count):
                for source_index in range(0, col_count):
                    if proof["char_count"] == 24:
                        svg, sca = proof["glyph_dict"][
                            tuple(
                                [
                                    tuple(proof["print_pages"][page][2][source_index + line_index * col_count + block_index * col_count * row_count]),
                                    tuple(proof["print_pages"][page][4][source_index + line_index * col_count + block_index * col_count * row_count]),
                                ]
                            )
                        ]
                    else:
                        svg, sca = proof["glyph_dict"][
                            tuple(
                                [
                                    proof["print_pages"][page][2][source_index + line_index * col_count + block_index * col_count * row_count],
                                    tuple(proof["print_pages"][page][4][source_index + line_index * col_count + block_index * col_count * row_count]),
                                ]
                            )
                        ]
                    if svg != None:
                        dw = svg2rlg(svg)
                        dw.scale(21 / sca, 21 / sca)
                        if proof["char_count"] != 24:
                            # non-IVD glyph
                            renderPDF.draw(
                                dw,
                                cv,
                                nonivd_first_x[2] + source_index * nonivd_subsrc_gap_x + block_index * (right_x - left_x) / column_count,
                                792
                                - (
                                    nonivd_first_y[3]
                                    + line_index * nonivd_row_gap_y
                                    + 21
                                    * proof["glyph_dict"][
                                        "fix", proof["print_pages"][page][4][source_index + line_index * col_count + block_index * col_count * row_count]
                                    ]
                                ),
                            )
                        else:
                            # IVD glyph
                            renderPDF.draw(
                                dw,
                                cv,
                                ivd_first_x[2] + source_index * nonivd_subsrc_gap_x + block_index * ivd_block_gap_x,
                                792
                                - (
                                    ivd_first_y[4]
                                    + line_index * ivd_row_gap_y
                                    + 21
                                    * proof["glyph_dict"][
                                        "fix", proof["print_pages"][page][4][source_index + line_index * col_count + block_index * col_count * row_count]
                                    ]
                                ),
                            )

        # ===========================
        # ========  new page ========
        # ===========================
        if page != len(proof["print_pages"]) - 1:
            dw = shapes.Drawing(612, 792)
            cv.showPage()
        else:
            cv.save()
    Current.unipage.ui.bar.setValue(0)


def _extreme_cp(cp_list: list, opt: str) -> str:
    if opt == "min":
        dec_cp = 10000000
        for cp in cp_list:
            if cp != "" and int(cp, 16) < dec_cp:
                dec_cp = int(cp, 16)
        return str(hex(dec_cp)).upper().replace("0X", "")
    elif opt == "max":
        dec_cp = 0
        for cp in cp_list:
            if cp != "" and int(cp, 16) > dec_cp:
                dec_cp = int(cp, 16)
        return str(hex(dec_cp)).upper().replace("0X", "")


def _get_font(font_info: tuple[str, str]) -> tuple[str, str]:
    if font_info[0] == None:
        font_name = font_info[1]
    else:
        font_name = font_info[0]
    if font_name == "待选择":
        return (None, None)
    else:
        font_dir = [it[2] for it in Current.project.prj_rsc_info["fnt"] if it[0] == font_name][0]
        return (font_name, font_dir)


def _get_glyph(glyph_info: tuple[int, int], blk_type: str) -> int | tuple[int, int]:
    if blk_type != "V":
        if glyph_info[0] != None:
            return glyph_info[0]
        else:
            return glyph_info[1]
    else:
        return glyph_info


def make_proof(name: str):
    Current.unipage.ui.bar.setValue(0)

    cnt = None
    bugs = []

    try:
        blk_set = [set for set in Current.project.prj_set_info if set["blk_name"] == name][0]
        blk_info = [info for info in Current.project.prj_blk_info if info["blk_name"] == name][0]
        blk_type = blk_info["blk_type"]

        if blk_type != "C":
            if blk_type in ["H", "W"]:
                c_count = [40, 60, 80, 100][blk_set["blk_cont"]["column"]]
                g_count = [240, 180, 160, 100][blk_set["blk_cont"]["column"]]
            elif blk_type == "V":
                c_count = 24
                g_count = 96

            c_index = 0
            # 0: 增页, 1: 本列满, 2: 都没满, 3: 本页满
            flag = 2
            print_pages = []

            list_cp = ["" for _ in range(c_count)]
            list_rs = ["" for _ in range(c_count)]
            list_gl = ["" for _ in range(g_count)]
            list_sr = ["" for _ in range(g_count)]
            list_ft = ["" for _ in range(g_count)]

            cps = [int(key) for key in blk_info["blk_cont"].keys()]
            cps.append(cps[-1])
            # cp_count = len(cps)
            cps.sort(reverse=True)
            cp_count = len(cps)

            while len(cps):
                cp = str(cps.pop())
                if blk_type != "V":
                    cp_subsrc = {}
                    for it in blk_info["blk_cont"][cp][1]:
                        if it != None:
                            cp_subsrc[_subsrc_no(it[-1])] = it

                Current.unipage.ui.bar.setValue(int(20 * (cp_count - len(cps)) / cp_count))

                line_one = 0
                line_two = 0
                if c_count == 40:
                    line_one = int(0 in cp_subsrc or 1 in cp_subsrc or 3 in cp_subsrc or 4 in cp_subsrc or 6 in cp_subsrc or 7 in cp_subsrc)
                    line_two = int(2 in cp_subsrc or 5 in cp_subsrc or 8 in cp_subsrc or 9 in cp_subsrc or 10 in cp_subsrc or 11 in cp_subsrc)
                    line_use = line_one + line_two
                elif c_count == 24:
                    line_use = int(ceil(round(sum([int(bool(i)) for i in blk_info["blk_cont"][cp]]) / g_count * c_count, 2)))
                else:
                    line_use = int(ceil(round(sum([int(bool(i)) for i in blk_info["blk_cont"][cp][1]]) / g_count * c_count, 2)))

                if c_count != 24:
                    if divmod(c_index + line_use - 1, c_count)[-1] < c_index or c_index > c_count:
                        flag = 0
                    elif divmod(divmod(c_index, 20)[-1] + line_use - 1, 20)[-1] < divmod(c_index, 20)[-1]:
                        flag = 1
                    elif len(cps):
                        flag = 2
                    else:
                        flag = 3
                else:
                    if divmod(c_index + line_use - 1, c_count)[-1] < c_index or c_index > c_count:
                        flag = 0
                    elif divmod(divmod(c_index, 12)[-1] + line_use - 1, 12)[-1] < divmod(c_index, 12)[-1]:
                        flag = 1
                    elif len(cps):
                        flag = 2
                    else:
                        flag = 3

                if flag == 0:
                    min_cp = _extreme_cp(list_cp, "min")
                    max_cp = _extreme_cp(list_cp, "max")
                    print_pages.append([list_cp, list_rs, list_gl, list_sr, list_ft, min_cp, max_cp])
                    list_cp = ["" for _ in range(c_count)]
                    list_rs = ["" for _ in range(c_count)]
                    list_gl = ["" for _ in range(g_count)]
                    list_sr = ["" for _ in range(g_count)]
                    list_ft = ["" for _ in range(g_count)]
                    c_index = 0
                    cps.append(cp)
                elif flag == 1:
                    if blk_type == "V":
                        c_index = 12 * ceil(c_index / 12)
                    else:
                        c_index = 20 * ceil(c_index / 20)
                    cps.append(cp)
                elif flag == 2:
                    list_cp[c_index] = hex(int(cp)).upper().replace("0X", "")
                    if blk_type != "V":
                        list_rs[c_index] = blk_info["blk_cont"][cp][0]
                        if list_rs[c_index] is None:
                            raise UniException([0, "C002", name, cp + " (" + hex(int(cp)).upper().replace("0X", "") + ") 缺少对应的 RS。"])
                    if c_count == 40:
                        if line_one == 1 and line_two == 0:
                            subsrc_list = [0, 1, 3, 6, 4, 7]
                        elif line_one == 0 and line_two == 1:
                            subsrc_list = [2, 10, 9, 11, 5, 8]
                        elif line_one == 1 and line_two == 1:
                            subsrc_list = [0, 1, 3, 6, 4, 7, 2, 10, 9, 11, 5, 8]
                        for i in range(len(subsrc_list)):
                            if subsrc_list[i] in cp_subsrc.keys():
                                temp_fnt, temp_gly, temp_src = cp_subsrc[subsrc_list[i]]
                                inpt_fnt, inpt_gly, inpt_src = (
                                    _get_font((temp_fnt, blk_set["blk_cont"]["font"][subsrc_list[i]][1])),
                                    _get_glyph((temp_gly, int(cp)), blk_type),
                                    temp_src,
                                )
                                if inpt_fnt == (None, None):
                                    raise UniException([0, "C007", name, _subsrc_name(subsrc_list[i]) + " 源"])
                                list_gl[round(c_index * g_count / c_count) + i] = inpt_gly
                                list_sr[round(c_index * g_count / c_count) + i] = inpt_src
                                list_ft[round(c_index * g_count / c_count) + i] = inpt_fnt
                    elif c_count == 24:
                        g_info = []
                        for it in blk_info["blk_cont"][cp]:
                            temp_fnt, temp_gly, temp_src = it[1], it[2], [it[3], it[4]]
                            inpt_fnt, inpt_gly, inpt_src = (
                                _get_font((temp_fnt, blk_set["blk_cont"]["font"][1])),
                                _get_glyph((it[0], int(cp)), blk_type),
                                temp_src,
                            )
                            if inpt_fnt == (None, None):
                                raise UniException([0, "C007", name, "IVD"])
                            g_info.append([inpt_gly, inpt_src, inpt_fnt])
                        for i in range(0, round(line_use * g_count / c_count)):
                            if i < len(g_info):
                                list_gl[round(c_index * g_count / c_count + i)] = g_info[i][0]
                                list_sr[round(c_index * g_count / c_count + i)] = g_info[i][1]
                                list_ft[round(c_index * g_count / c_count + i)] = g_info[i][2]
                    else:
                        g_info = []
                        subsrc_list = [0, 3, 1, 2, 6, 4, 5, 7, 8, 9, 10, 11]
                        for i in subsrc_list:
                            if i in cp_subsrc.keys():
                                temp_fnt, temp_gly, temp_src = cp_subsrc[i]
                                inpt_fnt, inpt_gly, inpt_src = (
                                    _get_font((temp_fnt, blk_set["blk_cont"]["font"][i][1])),
                                    _get_glyph((temp_gly, int(cp)), blk_type),
                                    temp_src,
                                )
                                if inpt_fnt == (None, None):
                                    raise UniException([0, "C007", name, _subsrc_name(subsrc_list[i]) + " 源"])
                                g_info.append([inpt_gly, inpt_src, inpt_fnt])
                        for i in range(0, round(line_use * g_count / c_count)):
                            if i < len(g_info):
                                list_gl[round(c_index * g_count / c_count + i)] = g_info[i][0]
                                list_sr[round(c_index * g_count / c_count + i)] = g_info[i][1]
                                list_ft[round(c_index * g_count / c_count + i)] = g_info[i][2]
                    c_index += line_use
                elif flag == 3:
                    min_cp = _extreme_cp(list_cp, "min")
                    max_cp = _extreme_cp(list_cp, "max")
                    if int(max_cp, 16) > 0:
                        print_pages.append([list_cp, list_rs, list_gl, list_sr, list_ft, min_cp, max_cp])
        else:
            # TODO

            # parse blk_info["blk_cont"]["names_list"]
            parsed_list = []
            for line in blk_info["blk_cont"]["names_list"]:
                parsed_list += []

            # r_count = 64
            # list_nl = [["", "", ""] for _ in range(r_count)]

        # from json import dump
        # fp = open('E:/Unipage/_ws2017/res.json', 'w')
        # dump(print_pages, fp)
        # fp.close()

        page_class = [("Right", "Left"), ("Left", "Right"), ("Center", "Center")][blk_set["blk_cont"]["format"]]
        glyph_dict = _build_svg(print_pages)
        if glyph_dict.__class__.__name__ == "tuple":
            raise UniException([0, "C008", name, "字库 " + glyph_dict[0] + " 缺少 " + glyph_dict[1] + " 对应的字图。"])
        glyph_dict[("", ())] = (None, None)
        glyph_dict[((), ())] = (None, None)

        temp_dict = dict()
        temp_dict["blk_name"] = blk_info["blk_name"]
        temp_dict["blk_initcp"] = blk_info["blk_initcp"]
        temp_dict["blk_finacp"] = blk_info["blk_finacp"]
        temp_dict["page_title"] = blk_set["blk_cont"]["title"]
        temp_dict["print_pages"] = print_pages
        temp_dict["page_class"] = page_class
        temp_dict["char_count"] = c_count
        temp_dict["glyph_dict"] = glyph_dict
        cnt = deepcopy(temp_dict)
    except Exception as exc:
        if exc.__class__.__name__ == "UniException":
            bugs.append([exc.arg[0], exc.arg[1], name, exc.arg[3]])
        else:
            bugs.append([0, "C000", name, exc.__class__.__name__ + ": " + str(exc.args[0])])
        pass
    finally:
        Current.unipage.ui.bar.setValue(0)
        return cnt, bugs


# if __name__ == "__main__":
#     # print(_show_rs("1\'.2").encode("utf-8"))

#     font = ttLib.TTFont("E:/Unipage/_main/FZSS.otf")
#     glyphset = font.getGlyphSet()
#     cps = font.getBestCmap().keys()

#     from fontTools.pens.boundsPen import BoundsPen
#     bp = BoundsPen(glyphset)
#     widths = []

#     for cp in range(0x4E00, 0xA000):
#         if cp in cps:
#             widths.append(glyphset["uni" + hex(cp).upper().replace("0X", "")].width)
#     import numpy
#     print(numpy.mean(widths))
