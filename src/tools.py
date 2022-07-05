from copy import deepcopy
from os import remove
from os.path import basename, exists, splitext
from re import sub
from shutil import copyfile

from PySide2.QtCore import Qt
from PySide2.QtWidgets import QTreeWidgetItem

from current import Current
from rsc_parser import Parser, _subsrc_name, _subsrc_no


def _wash_out(string: str) -> str:
    return sub(r"None, ", "", sub(r", None", "", string))


def _check(_check: int) -> Qt.CheckState:
    return ["未编译", "编译未通过", "编译通过"][_check]


def _bug(no: str) -> str:
    return {
        "C000": "未知错误。",
        "C001": "blk 文件格式错误。",
        "C002": "RS 表达式错误。",
        "C003": "块名为空。",
        "C004": "块类为空。",
        "C005": "块范围异常。",
        "C006": "upj 文件格式错误。",
        "C007": "未调用字库。",
        "C008": "缺少字图。",
        "C009": "字库不存在。",
        "J001": "块范围首模 16 不为 0，违反 Unicode Standard Conformance D10b。",
        "J002": "块范围尾模 16 不为 15，违反 Unicode Standard Conformance D10b。",
        "J003": "存在块外字符。",
        "J004": "部首不存在。"
    }[no]


def _yes_no(no: int) -> str:
    return ["否", "是"][no]


def _column(no: int) -> str:
    return ["2 栏，每栏 6 形", "3 栏，每栏 3 形", "4 栏，每栏 2 形", "5 栏，每栏 1 形"][no]


def _format(no: int) -> str:
    return ["居右", "居左", "居中"][no]


def _font(no: int) -> str:
    return (["待选择"] + [fnt[0] for fnt in Current.project.prj_rsc_info["fnt"]])[no]


def input_resource(src: str, des: str, chk: int, par: list, upj: bool):
    ext = splitext(des)[1]
    if upj:
        array_exts = ['.upj', '.blk', '.att', '.ttf', '.otf']
    else:
        array_exts = ['.blk', '.att', '.ttf', '.otf']
    if ext in array_exts and des not in [info[2] for info in Current.files()]:
        if src != des and src is not None:
            if exists(des):
                remove(des)
            copyfile(src, des)

        info = [basename(des), chk, des, par]
        item = QTreeWidgetItem()
        item.setText(0, info[0])
        item.setText(1, _check(info[1]))
        item.setText(2, info[2])
        if ext == '.upj':
            Current.unipage.ui.tree_file.topLevelItem(0).addChild(item)
            Current.project.prj_rsc_info["upj"].append(info)
        elif ext == '.blk':
            Current.unipage.ui.tree_file.topLevelItem(1).addChild(item)
            Current.project.prj_rsc_info["blk"].append(info)
            if info[1] == 2:
                parse_resource(item)
        elif ext == '.ttf' or ext == '.otf':
            Current.unipage.ui.tree_file.topLevelItem(2).addChild(item)
            Current.project.prj_rsc_info["fnt"].append(info)
        elif ext == '.att':
            Current.unipage.ui.tree_file.topLevelItem(3).addChild(item)
            Current.project.prj_rsc_info["att"].append(info)
        Current.unipage.ui.tree_file.expandAll()


def remove_resource(it: QTreeWidgetItem):
    for rscs in [Current.project.prj_rsc_info["blk"], Current.project.prj_rsc_info["fnt"], Current.project.prj_rsc_info["att"]]:
        for rsc in rscs:
            if rsc[2] == it.text(2):
                rscs.remove(rsc)
    it.parent().removeChild(it)


def parse_resource(it: QTreeWidgetItem):
    for rsc in (Current.project.prj_rsc_info["blk"] + Current.project.prj_rsc_info["att"]):
        # it: [basename, _check, url]
        # rsc: [basename, _check, url, parse]
        if rsc[2] == it.text(2):
            if rsc in Current.project.prj_rsc_info["blk"]:
                rsc_parse = Parser.blk(rsc[2])
            else:
                rsc_parse = Parser.att(rsc[2])
            if [i for i in rsc_parse[1] if i[0] == 0]:
                rsc[1] = 1
                it.setText(1, _check(1))
            else:
                rsc[3] = rsc_parse[0]
                rsc[1] = 2
                it.setText(1, _check(2))
            show_bugs(rsc_parse[1])


def show_bugs(bugs: list):
    # bug = [bug_type, bug_code, basename, line]
    errs = [bug for bug in bugs if bug[0] == 0]
    wars = [bug for bug in bugs if bug[0] == 1]
    infs = [bug for bug in bugs if bug[0] == 2]
    if errs:
        top_item = QTreeWidgetItem()
        top_item.setText(0, errs[0][2])
        Current.unipage.ui.tree_err.addTopLevelItem(top_item)
        for index in range(Current.unipage.ui.tree_err.topLevelItemCount()):
            if Current.unipage.ui.tree_err.topLevelItem(index).text(0) == errs[0][2]:
                for err in errs:
                    child_item = QTreeWidgetItem()
                    child_item.setText(0, err[1])
                    child_item.setText(1, _bug(err[1]))
                    child_item.setText(2, err[3])
                    top_item.addChild(child_item)
    Current.unipage.ui.tree_err.expandAll()
    if wars:
        top_item = QTreeWidgetItem()
        top_item.setText(0, wars[0][2])
        Current.unipage.ui.tree_war.addTopLevelItem(top_item)
        for index in range(Current.unipage.ui.tree_war.topLevelItemCount()):
            if Current.unipage.ui.tree_war.topLevelItem(index).text(0) == wars[0][2]:
                for war in wars:
                    child_item = QTreeWidgetItem()
                    child_item.setText(0, war[1])
                    child_item.setText(1, _bug(war[1]))
                    child_item.setText(2, war[3])
                    top_item.addChild(child_item)
    Current.unipage.ui.tree_war.expandAll()
    if infs:
        top_item = QTreeWidgetItem()
        top_item.setText(0, infs[0][2])
        Current.unipage.ui.tree_inf.addTopLevelItem(top_item)
        for index in range(Current.unipage.ui.tree_inf.topLevelItemCount()):
            if Current.unipage.ui.tree_inf.topLevelItem(index).text(0) == infs[0][2]:
                for inf in infs:
                    child_item = QTreeWidgetItem()
                    child_item.setText(0, inf[1])
                    child_item.setText(1, _bug(inf[1]))
                    child_item.setText(2, inf[3])
                    top_item.addChild(child_item)
    Current.unipage.ui.tree_inf.expandAll()
    count_bugs()


def count_bugs():
    count = 0
    for index in range(Current.unipage.ui.tree_err.topLevelItemCount()):
        count += Current.unipage.ui.tree_err.topLevelItem(index).childCount()
    Current.unipage.ui.tab.setTabText(0, "错误 [" + str(count) + "]")
    count = 0
    for index in range(Current.unipage.ui.tree_war.topLevelItemCount()):
        count += Current.unipage.ui.tree_war.topLevelItem(index).childCount()
    Current.unipage.ui.tab.setTabText(1, "警告 [" + str(count) + "]")
    count = 0
    for index in range(Current.unipage.ui.tree_inf.topLevelItemCount()):
        count += Current.unipage.ui.tree_inf.topLevelItem(index).childCount()
    Current.unipage.ui.tab.setTabText(2, "信息 [" + str(count) + "]")


def build_blocks():
    Current.unipage.ui.tree_out.clear()
    Current.project.prj_blk_info = []
    for blk in Current.project.prj_rsc_info["blk"]:
        if blk[1] == 2:
            for block in blk[3]:
                _build_block(block, False)


def read_blocks():
    Current.unipage.ui.tree_out.clear()
    for block in Current.project.prj_blk_info:
        _build_block(block, True)


def _build_block(blk: dict, flag: bool):
    if flag == False:
        temp_blk = dict()
        temp_blk["blk_name"] = blk["blk_name"]
        temp_blk["blk_type"] = blk["blk_type"]
        temp_blk["blk_initcp"], temp_blk["blk_finacp"] = blk["blk_initcp"], blk["blk_finacp"]
        temp_blk["blk_cont"] = {}
    else:
        temp_blk = blk

    top_item = QTreeWidgetItem()
    top_item.setText(0, temp_blk["blk_name"])
    top_item.setText(1, "[" + str(temp_blk["blk_initcp"]) + " (" + hex(temp_blk["blk_initcp"]).upper().replace("0X", "") + "), " + str(temp_blk["blk_finacp"]) + " (" + hex(temp_blk["blk_finacp"]).upper().replace("0X", "") + ")]")
    Current.unipage.ui.tree_out.addTopLevelItem(top_item)

    if flag == False:
        if temp_blk["blk_type"] in ["H", "W"]:
            for index_cp in range(temp_blk["blk_initcp"], temp_blk["blk_finacp"] + 1):
                temp_blk["blk_cont"][str(index_cp)] = [None, [None] * 12]
            for item in blk["blk_cont"].items():
                if temp_blk["blk_type"] == "H":
                    # "19968　G": [None, None, "G0-523B"] => "19968": [[None, None, "G0-523B"], None, ...]
                    chr_cp, chr_subsrc = item[0].split("　")
                elif temp_blk["blk_type"] == "W":
                    # "1　131072　G": [None, 58997, "GHZ-74352.12"] => "131072": [[None, 58997, "GHZ-74352.12"], None, ...]
                    chr_sq, chr_cp, chr_subsrc = item[0].split("　")
                if int(chr_cp) in range(temp_blk["blk_initcp"], temp_blk["blk_finacp"] + 1):
                    temp_blk["blk_cont"][chr_cp][1][_subsrc_no(chr_subsrc)] = item[1]
            temp_blk["blk_cont"] = {k: temp_blk["blk_cont"][k] for k in temp_blk["blk_cont"].keys() if temp_blk["blk_cont"][k][1] != [None] * 12}
            for att in Current.project.prj_rsc_info["att"]:
                if att[1] == 2:
                    for conts in att[3]:
                        for cont in conts["inf_cont"].items():
                            if int(cont[0]) in range(temp_blk["blk_initcp"], temp_blk["blk_finacp"] + 1):
                                temp_blk["blk_cont"][cont[0]][0] = cont[1]
        elif temp_blk["blk_type"] == "V":
            # "40860　917766　Hanyo-Denshi": [None, None, "JTC0AE"] => "40860": [[917766, None, None, "JTC0AE", "Hanyo-Denshi"]]
            for item in blk["blk_cont"].items():
                chr_cp, chr_slt, chr_set = item[0].split("　")
                chr_slt = int(chr_slt)
                if chr_cp not in temp_blk["blk_cont"].keys():
                    temp_blk["blk_cont"][chr_cp] = [[chr_slt] + item[1] + [chr_set]]
                else:
                    temp_blk["blk_cont"][chr_cp].append([chr_slt] + item[1] + [chr_set])
            for key in temp_blk["blk_cont"].keys():
                temp_blk["blk_cont"][key].sort()

    for item in temp_blk["blk_cont"].items():
        child_item = QTreeWidgetItem()
        child_item.setText(0, str(int(item[0])) + " (" + hex(int(item[0])).upper().replace("0X", "") + ")")
        child_item.setText(1, _wash_out(str(item[1])))
        top_item.addChild(child_item)
    Current.unipage.ui.tree_out.expandAll()

    if flag == False:
        block = deepcopy(temp_blk)
        Current.project.prj_blk_info.append(block)


def build_settings(flag: bool):
    Current.unipage.ui.tree_set.clear()
    Current.project.prj_set_info = []
    for block in Current.project.prj_blk_info:
        _build_setting(block, flag)


def read_settings():
    Current.unipage.ui.tree_set.clear()
    for block in Current.project.prj_set_info:
        _build_setting(block, True)


def _build_setting(blk: dict, flag: bool):
    if not blk:
        flag = False

    if flag == False:
        temp_blk = dict()
        temp_blk["blk_name"] = blk["blk_name"]
        temp_blk["blk_type"] = blk["blk_type"]
        temp_blk["blk_initcp"], temp_blk["blk_finacp"] = blk["blk_initcp"], blk["blk_finacp"]
        temp_blk["blk_cont"] = {}
    else:
        temp_blk = blk

    top_item = QTreeWidgetItem()
    top_item.setText(0, temp_blk["blk_name"])
    Current.unipage.ui.tree_set.addTopLevelItem(top_item)

    # 无选项信息
    if flag == False:
        temp_blk["blk_cont"]["print"] = 1
        temp_blk["blk_cont"]["column"] = 0
        temp_blk["blk_cont"]["yellow"] = []
        temp_blk["blk_cont"]["blue"] = []

        if temp_blk["blk_type"] in ["H", "W"]:
            temp_blk["blk_cont"]["format"] = 0
            temp_blk["blk_cont"]["font"] = [[0, _font(0)] for _ in range(12)]
        elif temp_blk["blk_type"] == "V":
            temp_blk["blk_cont"]["format"] = 2
            temp_blk["blk_cont"]["font"] = [0, _font(0)]

    child_item = QTreeWidgetItem()
    child_item.setText(0, "是否打印")
    child_item.setText(1, "◁　" + _yes_no(temp_blk["blk_cont"]["print"]) + "　▷")
    top_item.addChild(child_item)
    child_item = QTreeWidgetItem()
    child_item.setText(0, "栏位")
    child_item.setText(1, "◁　" + _column(temp_blk["blk_cont"]["column"]) + "　▷")
    if temp_blk["blk_type"] == "V":
        child_item.setText(1, "◁　2 栏，每栏 4 形　▷")
        child_item.setDisabled(True)
    top_item.addChild(child_item)
    child_item = QTreeWidgetItem()
    child_item.setText(0, "首页版式")
    child_item.setText(1, "◁　" + _format(temp_blk["blk_cont"]["format"]) + "　▷")
    top_item.addChild(child_item)

    # TODO
    child_item = QTreeWidgetItem()
    child_item.setText(0, "标黄")
    top_item.addChild(child_item)
    child_item = QTreeWidgetItem()
    child_item.setText(0, "标蓝")
    top_item.addChild(child_item)

    font_item = QTreeWidgetItem()
    font_item.setText(0, "字库")
    top_item.addChild(font_item)
    if temp_blk["blk_type"] in ["H", "W"]:
        for index_src in range(12):
            child_item = QTreeWidgetItem()
            child_item.setText(0, _subsrc_name(index_src) + " 源字库")
            child_item.setText(1, "◁　" + temp_blk["blk_cont"]["font"][index_src][1] + "　▷")
            font_item.addChild(child_item)
    elif temp_blk["blk_type"] == "V":
        child_item = QTreeWidgetItem()
        child_item.setText(0, "IVD 字库")
        child_item.setText(1, "◁　" + temp_blk["blk_cont"]["font"][1] + "　▷")
        font_item.addChild(child_item)
    Current.unipage.ui.tree_set.expandAll()

    if flag == False:
        block = deepcopy(temp_blk)
        Current.project.prj_set_info.append(block)


def previous_option(item: QTreeWidgetItem, flag: bool):
    if item.text(0)[-2:] == "字库":
        for set in Current.project.prj_set_info:
            if set["blk_name"] == item.parent().parent().text(0):
                if set["blk_type"] != "V":
                    if flag == False:
                        set["blk_cont"]["font"][item.parent().indexOfChild(item)][0] = (set["blk_cont"]["font"][item.parent().indexOfChild(item)][0] - 1) % (len(Current.project.prj_rsc_info["fnt"]) + 1)
                    else:
                        set["blk_cont"]["font"][item.parent().indexOfChild(item)][0] = (set["blk_cont"]["font"][item.parent().indexOfChild(item)][0] + 1) % (len(Current.project.prj_rsc_info["fnt"]) + 1)
                    set["blk_cont"]["font"][item.parent().indexOfChild(item)][1] = _font(set["blk_cont"]["font"][item.parent().indexOfChild(item)][0])
                    item.setText(1, "◁　" + set["blk_cont"]["font"][item.parent().indexOfChild(item)][1] + "　▷")
                else:
                    if flag == False:
                        set["blk_cont"]["font"][0] = (set["blk_cont"]["font"][0] - 1) % (len(Current.project.prj_rsc_info["fnt"]) + 1)
                    else:
                        set["blk_cont"]["font"][0] = (set["blk_cont"]["font"][0] + 1) % (len(Current.project.prj_rsc_info["fnt"]) + 1)
                    set["blk_cont"]["font"][1] = _font(set["blk_cont"]["font"][0])
                    item.setText(1, "◁　" + set["blk_cont"]["font"][1] + "　▷")
    else:
        for set in Current.project.prj_set_info:
            if set["blk_name"] == item.parent().text(0):
                if flag == False:
                    set["blk_cont"][["print", "column", "format"][item.parent().indexOfChild(item)]] = (set["blk_cont"][["print", "column", "format"][item.parent().indexOfChild(item)]] - 1) % [2, 4, 3][item.parent().indexOfChild(item)]
                else:
                    set["blk_cont"][["print", "column", "format"][item.parent().indexOfChild(item)]] = (set["blk_cont"][["print", "column", "format"][item.parent().indexOfChild(item)]] + 1) % [2, 4, 3][item.parent().indexOfChild(item)]
                item.setText(1, "◁　" + [_yes_no, _column, _format][item.parent().indexOfChild(item)](set["blk_cont"][["print", "column", "format"][item.parent().indexOfChild(item)]]) + "　▷")


def colour_option(item: QTreeWidgetItem, colour: str):
    for block_set in Current.project.prj_set_info:
        if block_set["blk_name"] == item.parent().text(0):
            for block_itidx in range(Current.unipage.ui.tree_set.topLevelItemCount()):
                if Current.unipage.ui.tree_set.topLevelItem(block_itidx).text(0) == block_set["blk_name"]:
                    if int(item.text(0).split(" ")[0]) in block_set["blk_cont"][colour]:
                        block_set["blk_cont"][colour].remove(int(item.text(0).split(" ")[0]))
                    else:
                        block_set["blk_cont"][colour].append(int(item.text(0).split(" ")[0]))


def show_options():
    for block_set in Current.project.prj_set_info:
        for block_itidx in range(Current.unipage.ui.tree_set.topLevelItemCount()):
            if Current.unipage.ui.tree_set.topLevelItem(block_itidx).text(0) == block_set["blk_name"]:
                block_set["blk_cont"]["yellow"].sort()
                for item_index in range(Current.unipage.ui.tree_set.topLevelItem(block_itidx).child(3).childCount() - 1, -1, -1):
                    Current.unipage.ui.tree_set.topLevelItem(block_itidx).child(3).removeChild(Current.unipage.ui.tree_set.topLevelItem(block_itidx).child(3).child(item_index))
                for item in block_set["blk_cont"]["yellow"]:
                    child_item = QTreeWidgetItem()
                    child_item.setText(0, str(item))
                    child_item.setText(1, "标黄")
                    Current.unipage.ui.tree_set.topLevelItem(block_itidx).child(3).addChild(child_item)

                block_set["blk_cont"]["blue"].sort()
                for item_index in range(Current.unipage.ui.tree_set.topLevelItem(block_itidx).child(4).childCount() - 1, -1, -1):
                    Current.unipage.ui.tree_set.topLevelItem(block_itidx).child(4).removeChild(Current.unipage.ui.tree_set.topLevelItem(block_itidx).child(4).child(item_index))
                for item in block_set["blk_cont"]["blue"]:
                    child_item = QTreeWidgetItem()
                    child_item.setText(0, str(item))
                    child_item.setText(1, "标蓝")
                    Current.unipage.ui.tree_set.topLevelItem(block_itidx).child(4).addChild(child_item)
    Current.unipage.ui.tree_set.expandAll()
