import code
from copy import deepcopy
from json import load
from os.path import basename
from re import match


def _subsrc_name(source: int) -> str:
    return ["G", "H", "M", "T", "K", "KP", "J", "V", "GS", "UK", "UTC", "SAT"][source]


def _subsrc_no(refsrc: str) -> int:
    #   G = 0,  H = 1,  M = 2,    T = 3,
    #   K = 4,  KP = 5, J = 6,    V = 7,
    #   GS = 8, UK = 9, UTC = 10, SAT = 11
    if refsrc[0:3].upper() == "SAT":
        return 11
    elif refsrc[0:3].upper() == "UTC":
        return 10
    elif refsrc[0:2].upper() == "UK":
        return 9
    elif refsrc[0:2].upper() == "GS":
        return 8
    elif refsrc[0].upper() == "V":
        return 7
    elif refsrc[0].upper() == "J":
        return 6
    elif refsrc[0:2].upper() == "KP":
        return 5
    elif refsrc[0].upper() == "K":
        return 4
    elif refsrc[0].upper() == "T":
        return 3
    elif refsrc[0].upper() == "M":
        return 2
    elif refsrc[0].upper() == "H":
        return 1
    elif refsrc[0].upper() == "G":
        return 0


def _show_rs(rs: str) -> (str | None):
    variants = {
        "90'": "⺦",
        "120'": "⺰",
        "147'": "⻅",
        "149'": "⻈",
        "154'": "⻉",
        "159'": "⻋",
        "167'": "⻐",
        "168'": "⻓",
        "169'": "⻔",
        "178'": "⻙",
        "181'": "⻚",
        "182'": "⻛",
        "183'": "⻜",
        "184'": "⻠",
        "187'": "⻢",
        "195'": "⻥",
        "196'": "⻦",
        "197'": "⻧",
        "199'": "⻨",
        "205'": "⻪",
        "210'": "⻬",
        "211'": "⻮",
        "212'": "⻰",
        "213'": "⻳",
        '213"': "⻲",
        '210"': "⻫",
        '211"': "⻭",
        '212"': "⻯",
        '208"': "⻴",
        '182"': "⻵"
    }

    if "'" not in rs.split(".")[0] and '"' not in rs.split(".")[0]:
        if int(rs.split(".")[0]) <= 214 and int(rs.split(".")[0]) >= 1:
            char_rs = chr(12031 + int(rs.split(".")[0]))
            return char_rs + "　" + rs
        else:
            return None
    elif rs.split(".")[0] in variants:
        char_rs = variants[rs.split(".")[0]]
        return char_rs + "　" + rs
    else:
        return None


def _parse_char(s: str) -> str:
    if s.startswith("("):
        #
        return s[:-1].split(" - ")[-1].upper()
    else:
        return s.upper()


class UniException(Exception):

    def __init__(self, arg):
        self.arg = arg


class Parser:

    def blk(url) -> tuple[list, list]:
        cnt = []
        bug = []
        try:
            fp = open(url, 'r', encoding='utf-8')
            line: str = fp.readline().strip()

            while line.lower() != '# eof':
                if line and line[0] == '#':
                    blk_range, blk_name, blk_type = line[1:].strip().split(";")
                    blk_range, blk_name, blk_type = blk_range.strip(), blk_name.strip(), blk_type.strip()
                    blk_init, blk_fina = blk_range.strip().split("..")
                    blk_init, blk_fina = int(blk_init.strip(), 16), int(blk_fina.strip(), 16)
                    blk_cont = {}

                    if blk_name == "":
                        raise UniException([0, "C003", basename(url), line.strip().encode('unicode_escape').decode('utf-8')])
                    if blk_type == "":
                        raise UniException([0, "C004", basename(url), line.strip().encode('unicode_escape').decode('utf-8')])
                    if blk_init >= blk_fina:
                        raise UniException([0, "C005", basename(url), line.strip().encode('unicode_escape').decode('utf-8')])
                    if blk_init % 16 != 0:
                        bug.append([1, "J001", basename(url), line.strip().encode('unicode_escape').decode('utf-8')])
                    if blk_fina % 16 != 15:
                        bug.append([1, "J002", basename(url), line.strip().encode('unicode_escape').decode('utf-8')])

                    line = fp.readline().strip()
                    while 1:
                        if line and line[0] == '#':
                            tmp_dict = dict()
                            tmp_dict["blk_initcp"] = blk_init
                            tmp_dict["blk_finacp"] = blk_fina
                            tmp_dict["blk_name"] = blk_name
                            tmp_dict["blk_type"] = blk_type
                            tmp_dict["blk_cont"] = blk_cont

                            blk = deepcopy(tmp_dict)
                            cnt.append(blk)
                            break
                        elif line:
                            if blk_type == "C":
                                # 111E1 \t SINHALA ARCHAIC DIGIT ONE \t U+E675 => "70113": [None, 58997, "SINHALA ARCHAIC DIGIT ONE"]
                                # 111E1 \t SINHALA ARCHAIC DIGIT ONE => "70113": [None, 70113, "SINHALA ARCHAIC DIGIT ONE"]
                                if len(line.strip().split("\t")) == 3:
                                    chr_cp, chr_name, chr_pua = line.strip().split("\t")
                                    chr_cp, chr_pua = int(chr_cp.strip(), 16), int(chr_pua.strip(), 16)
                                    blk_cont.update({str(chr_cp): [None, chr_pua, chr_name.upper()]})
                                elif len(line.strip().split("\t")) == 2:
                                    chr_cp, chr_name = line.strip().split("\t")
                                    chr_cp = int(chr_cp.strip(), 16)
                                    blk_cont.update({str(chr_cp): [None, chr_cp, chr_name.upper()]})
                            elif blk_type == "W":
                                # 00001 \t GHZ-74352.12 \t U+E675 => "1　131072　G": [None, 58997, "GHZ-74352.12"]
                                # 00001 \t GHZ-74352.12 => "1　131072　G": [None, None, "GHZ-74352.12"]
                                if len(line.strip().split("\t")) == 3:
                                    chr_sq, chr_refsrc, chr_pua = line.strip().split("\t")
                                    chr_sq = int(chr_sq.strip(), 10)
                                    chr_refsrc = chr_refsrc.strip()
                                    chr_pua = int(chr_pua.upper().strip().replace("U+", ""), 16)
                                    blk_cont.update({str(chr_sq) + "　" + str(blk_init + chr_sq - 1) + "　" + _subsrc_name(_subsrc_no(chr_refsrc)): [None, chr_pua, chr_refsrc]})
                                elif len(line.strip().split("\t")) == 2:
                                    chr_sq, chr_refsrc = line.strip().split("\t")
                                    chr_sq = int(chr_sq.strip(), 16)
                                    chr_refsrc = chr_refsrc.strip()
                                    blk_cont.update({str(chr_sq) + "　" + str(blk_init + chr_sq - 1) + "　" + _subsrc_name(_subsrc_no(chr_refsrc)): [None, None, chr_refsrc]})
                                else:
                                    raise ValueError
                            elif blk_type == "H":
                                # U+4E00 \t kIRG_GSource \t G0-523B => "19968　G": [None, None, "G0-523B"]
                                chr_cp, _, chr_refsrc = line.strip().split("\t")
                                chr_cp = int(chr_cp.upper().replace("U+", ""), 16)
                                blk_cont.update({str(chr_cp) + "　" + _subsrc_name(_subsrc_no(chr_refsrc)): [None, None, chr_refsrc]})
                            elif blk_type == "V":
                                # 9F9C E0106 \t Hanyo-Denshi \t JTC0AE => "40860　917766　Hanyo-Denshi": [None, None, "JTC0AE"]
                                chr_ivs, chr_set, chr_cid = line.strip().split("\t")
                                chr_cp, chr_slt = chr_ivs.strip().split(" ")
                                chr_cp, chr_slt = int(chr_cp.strip(), 16), int(chr_slt.strip(), 16)
                                chr_set, chr_cid = chr_set.strip(), chr_cid.strip()
                                blk_cont.update({str(chr_cp) + "　" + str(chr_slt) + "　" + str(chr_set): [None, None, chr_cid]})

                            if chr_cp not in range(blk_init, blk_fina + 1):
                                bug.append([1, "J003", basename(url), line.strip().encode('unicode_escape').decode('utf-8')])
                            line = fp.readline().strip()
                        else:
                            line = fp.readline().strip()
                else:
                    line = fp.readline().strip()
        except Exception as exc:
            if exc.__class__.__name__ == "ValueError":
                bug.append([0, "C001", basename(url), line.strip().encode('unicode_escape').decode('utf-8')])
            elif exc.__class__.__name__ == "UnicodeDecodeError":
                bug.append([0, "C001", basename(url), ""])
            elif exc.__class__.__name__ == "UniException":
                bug.append(exc.arg)
            else:
                bug.append([0, "C000", basename(url), exc.__class__.__name__ + ": " + line.strip().encode('unicode_escape').decode('utf-8')])
            pass
        finally:
            fp.close()
            return (cnt, bug)

    def att(url) -> tuple[list, list]:
        cnt = []
        bug = []
        try:
            fp = open(url, 'r', encoding='utf-8')
            line: str = fp.readline().strip()

            while line.lower() != '# eof':
                if line and line[0] == '#':
                    inf_type = line[1:].strip()
                    set_cont = {}
                    lst_cont = []

                    if inf_type not in ["RS", "NL"]:
                        raise ValueError

                    line = fp.readline().strip()
                    while 1:
                        if line and line[0] == '#':
                            tmp_dict = dict()
                            if set_cont:
                                tmp_dict["inf_cont"] = set_cont
                            else:
                                tmp_dict["inf_cont"] = lst_cont
                            cpy_dict = deepcopy(tmp_dict)
                            cnt.append(cpy_dict)
                            break
                        elif line:
                            if inf_type == "RS":
                                # U+4E2C \t 90.0 90'.0 => "20012": ["90.0", "90'.0"]
                                rs_cp, rs_values = line.strip().split("\t")
                                rs_cp = int(rs_cp.strip().upper().replace("U+", ""), 16)
                                rs_values = rs_values.strip().split(" ")
                                for rs_value in rs_values:
                                    if match("[1-9][0-9]{0,2}[\'\"]?\.-?[0-9]{1,2}", rs_value.strip()) == None or match("[1-9][0-9]{0,2}[\'\"]?\.-?[0-9]{1,2}", rs_value.strip()).group() != rs_value:
                                        raise UniException([0, "C002", basename(url), line.strip().encode('unicode_escape').decode('utf-8')])
                                    if _show_rs(rs_value) == None:
                                        bug.append([1, "J004", basename(url), line.strip().encode('unicode_escape').decode('utf-8')])
                                    _, _ = rs_value.strip().split(".")
                                set_cont.update({str(rs_cp): rs_values})
                            elif inf_type == "NL":
                                name_line: str = line.strip()
                                if name_line.startswith("@"):
                                    # SUBTITLE
                                    if name_line.startswith("@@@+"):
                                        lst_cont.append(["SUBTITLE", name_line.split("\t")[-1]])
                                    # MIXED_SUBHEADER (not used)
                                    elif name_line.startswith("@@@~"):
                                        if name_line == "@@@~":
                                            lst_cont.append(["MIXED_SUBHEADER", ""])
                                        else:
                                            lst_cont.append(["MIXED_SUBHEADER", name_line.split("\t")[-1]])
                                    # TITLE
                                    elif name_line.startswith("@@@"):
                                        lst_cont.append(["TITLE", name_line.split("\t")[-1]])
                                    # INDEX_TAB
                                    elif name_line.startswith("@@+"):
                                        pass
                                    # ALTGLYPH_SUBHEADER (not used)
                                    elif name_line.startswith("@@~"):
                                        if name_line == "@@~":
                                            lst_cont.append(["ALTGLYPH_SUBHEADER", ""])
                                        else:
                                            lst_cont.append(["ALTGLYPH_SUBHEADER", name_line.split("\t")[-1]])
                                    # BLOCKHEADER
                                    elif name_line.startswith("@@"):
                                        block_init, block_name, block_fina = name_line.split("\t")[1:]
                                        # => ["BLOCKHEADER", ["Latin Extended-A", "0100", "017F"]]
                                        lst_cont.append(["BLOCKHEADER", [block_name, block_init, block_fina]])
                                    # NOTICE_LINE
                                    elif name_line.startswith("@+"):
                                        if name_line.startswith("@+\t*"):
                                            # "*" => "•"
                                            lst_cont.append(["NOTICE_LINE (bullet)", name_line.split("\t")[-1][2:]])
                                        else:
                                            lst_cont.append(["NOTICE_LINE", name_line.split("\t")[-1]])
                                    # VARIATION_SUBHEADER (not used)
                                    elif name_line.startswith("@~"):
                                        if name_line == "@~":
                                            lst_cont.append(["VARIATION_SUBHEADER", ""])
                                        else:
                                            lst_cont.append(["VARIATION_SUBHEADER", name_line.split("\t")[-1]])
                                    # SUBHEADER
                                    else:
                                        lst_cont.append(["SUBHEADER", name_line.split("\t")[-1]])
                                elif name_line.startswith("\t"):
                                    # CROSS_REF
                                    if name_line.startswith("\t\tx"):
                                        # "x" => "→"
                                        lst_cont.append(["CROSS_REF (notice)", _parse_char(name_line.split("x ")[-1])])
                                    elif name_line.startswith("\tx"):
                                        # "x" => "→"
                                        lst_cont.append(["CROSS_REF", _parse_char(name_line.split("x ")[-1])])
                                    # ALIAS_LINE
                                    elif name_line.startswith("\t="):
                                        # "=" => "="
                                        lst_cont.append(["ALIAS_LINE", name_line.split("= ")[-1]])
                                    # FORMALALIAS_LINE
                                    elif name_line.startswith("\t%"):
                                        # "#" => "※"
                                        lst_cont.append(["FORMALALIAS_LINE", name_line.split("% ")[-1]])
                                    # VARIATION_LINE
                                    elif name_line.startswith("\t~"):
                                        # "~" => "~"
                                        lst_cont.append(["VARIATION_LINE", name_line.split("~ ")[-1]])
                                    # DECOMPOSITION
                                    elif name_line.startswith("\t:"):
                                        # ":" => "≡"
                                        lst_cont.append(["DECOMPOSITION", name_line.split(": ")[-1]])
                                    # IGNORED_LINE
                                    elif name_line.startswith("\t;"):
                                        pass
                                elif name_line.startswith(";"):
                                    # SIDEBAR_LINE
                                    if name_line.startswith(";;"):
                                        lst_cont.append(["SIDEBAR_LINE", name_line.split(";; ")[-1]])
                                else:
                                    codepoint, name = name_line.strip().split("\t")[0], name_line.strip().split("\t")[-1]
                                    # RESERVED_LINE
                                    if name == "<reserved>":
                                        lst_cont.append(["RESERVED_LINE", [codepoint.upper(), name]])
                                    # NAME_LINE
                                    else:
                                        lst_cont.append(["NAME_LINE", [codepoint.upper(), name.upper()]])
                            line = fp.readline().strip()
                        else:
                            line = fp.readline().strip()
                else:
                    line = fp.readline().strip()
        except Exception as exc:
            if exc.__class__.__name__ == "ValueError":
                bug.append([0, "C001", basename(url), line.strip().encode('unicode_escape').decode('utf-8')])
            elif exc.__class__.__name__ == "UnicodeDecodeError":
                bug.append([0, "C001", basename(url), ""])
            elif exc.__class__.__name__ == "UniException":
                bug.append(exc.arg)
            else:
                bug.append([0, "C000", basename(url), exc.__class__.__name__ + ": " + line.strip().encode('unicode_escape').decode('utf-8')])
            pass
        finally:
            fp.close()
            return (cnt, bug)

    def upj(url) -> tuple[list, list]:
        cnt = []
        bug = []
        try:
            fp = open(url, 'r', encoding='utf-8')
            cnt = load(fp)
        except Exception as exc:
            if exc.__class__.__name__ == "JSONDecodeError":
                bug.append([0, "C006", basename(url), str(exc.args[0])])
            else:
                bug.append([0, "C000", basename(url), str(exc.__class__.__name__ + ": " + exc.args[0])])
            pass
        finally:
            fp.close()
            return (cnt, bug)

        # fp = open(url, 'r', encoding='utf-8')
        # cnt = load(fp)
        # fp.close()
        # return (cnt, bug)
