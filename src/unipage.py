import sys
from functools import partial
from json import dump
from os.path import basename, exists, splitext

from PySide2.QtCore import QEvent, QObject
from PySide2.QtGui import QIcon
from PySide2.QtUiTools import QUiLoader
from PySide2.QtWidgets import QApplication, QFileDialog, QTreeWidgetItem

import printer
import tools
from current import Current
from new_project import Project
from rsc_parser import Parser


class Unipage():

    def __init__(self):
        self.ui = QUiLoader().load('src/unipage.ui')
        self.ui.setWindowIcon(QIcon('src/images/tree.png'))

        self.ui.act_create.triggered.connect(self.create_project)
        self.ui.act_open.triggered.connect(self.open_project)
        self.ui.act_save.triggered.connect(self.save_project)
        self.ui.act_close.triggered.connect(self.close_project)

        self.ui.act_imprsc.triggered.connect(self.import_resources)
        self.ui.act_delrsc.triggered.connect(self.remove_resources)
        self.ui.act_parsc.triggered.connect(partial(self.parse_resources, False))

        self.ui.act_prev.triggered.connect(partial(self.change_options, False))
        self.ui.act_next.triggered.connect(partial(self.change_options, True))
        self.ui.act_yellow.triggered.connect(partial(self.colour_options, "yellow"))
        self.ui.act_blue.triggered.connect(partial(self.colour_options, "blue"))

        self.ui.act_check.triggered.connect(self.check_print)
        self.ui.act_print.triggered.connect(self.print_project)

        self.ui.tree_file.setAcceptDrops(True)
        self.ui.tree_file.installEventFilter(self.ui.tree_file)

    def create_project(self):
        if Current.project is None:
            Current.tmp_project = Project()
            Current.unipage.ui.setMouseTracking(False)
            Current.tmp_project.new_ui.show()

    def save_project(self):
        if Current.project:
            Current.unipage.ui.bar.setValue(50)
            fp = open(Current.project.prj_basic_info["project_file"], "w")
            dump({"basic_info": Current.project.prj_basic_info, "rsc_info": Current.project.prj_rsc_info, "set_info": Current.project.prj_set_info, "blk_info": Current.project.prj_blk_info}, fp)
            fp.close()
            Current.unipage.ui.bar.setValue(0)

    def open_project(self):
        if not Current.project:
            Current.unipage.ui.tree_err.clear()
            Current.unipage.ui.tree_war.clear()
            Current.unipage.ui.tree_inf.clear()
            file_url = QFileDialog.getOpenFileUrl(caption="打开项目", filter="项目文件 (*.upj)")[0].toLocalFile()
            if file_url:
                rsc_parse = Parser.upj(file_url)
                if not [i for i in rsc_parse[1] if i[0] == 0]:
                    # read basic_info
                    Current.project = Project()
                    Current.project.prj_basic_info = rsc_parse[0]["basic_info"]
                    Current.unipage.ui.setWindowTitle("Unipage  —  " + splitext(basename(Current.project.prj_basic_info["project_name"]))[0])
                    # read rsc_info
                    for file in Current.files(rsc_parse[0]):
                        tools.input_resource(None, file[2], file[1], file[3], True)
                    # read blk_info
                    Current.project.prj_blk_info = rsc_parse[0]["blk_info"]
                    tools.read_blocks()
                    # read set_info
                    Current.project.prj_set_info = rsc_parse[0]["set_info"]
                    tools.read_settings()
                    tools.show_options()
                    self.save_project()
                tools.show_bugs(rsc_parse[1])

    def close_project(self):
        if Current.project:
            Current.project = None
            Current.tmp_project = None

            Current.unipage.ui.tree_set.clear()
            Current.unipage.ui.tree_err.clear()
            Current.unipage.ui.tree_war.clear()
            Current.unipage.ui.tree_inf.clear()
            Current.unipage.ui.tree_file.clear()

            head_list = ["项目文件", "块文件", "字库文件", "属性文件"]
            for head in head_list:
                item = QTreeWidgetItem()
                item.setText(0, head)
                Current.unipage.ui.tree_file.addTopLevelItem(item)

            Current.unipage.ui.tree_out.clear()
            tools.count_bugs()
            Current.unipage.ui.setWindowTitle("Unipage")

    def import_resources(self):
        if Current.project:
            files_url = QFileDialog.getOpenFileUrls(caption="导入资源文件")[0]
            if files_url:
                for file_url in files_url:
                    file_url = file_url.toLocalFile()
                    dest_url = Current.project.prj_basic_info["project_dir"] + '/' + basename(file_url)
                    tools.input_resource(file_url, dest_url, 0, None, False)

    def remove_resources(self):
        if Current.project:
            items = {it for it in Current.unipage.ui.tree_file.selectedItems() if splitext(it.text(2))[1] != ".upj"}
            for index_top in range(4):
                if Current.unipage.ui.tree_file.topLevelItem(index_top) in items:
                    items.remove(Current.unipage.ui.tree_file.topLevelItem(index_top))
                    if index_top > 0:
                        for index_child in range(Current.unipage.ui.tree_file.topLevelItem(index_top).childCount()):
                            items.add(Current.unipage.ui.tree_file.topLevelItem(index_top).child(index_child))
            for item in items:
                tools.remove_resource(item)
            tools.build_blocks()
            self.parse_resources(False)

    def parse_resources(self, flag: bool):
        if Current.project:
            items = {it for it in Current.unipage.ui.tree_file.selectedItems() if splitext(it.text(2))[1] != ".upj"}
            for index_top in range(4):
                if Current.unipage.ui.tree_file.topLevelItem(index_top) in items:
                    items.remove(Current.unipage.ui.tree_file.topLevelItem(index_top))
                    if index_top > 0:
                        for index_child in range(Current.unipage.ui.tree_file.topLevelItem(index_top).childCount()):
                            items.add(Current.unipage.ui.tree_file.topLevelItem(index_top).child(index_child))
            if not items:
                items = set()
                for index_top in range(1, 4):
                    for index_child in range(Current.unipage.ui.tree_file.topLevelItem(index_top).childCount()):
                        items.add(Current.unipage.ui.tree_file.topLevelItem(index_top).child(index_child))

            Current.unipage.ui.bar.setValue(0)
            Current.unipage.ui.tree_err.clear()
            Current.unipage.ui.tree_war.clear()
            Current.unipage.ui.tree_inf.clear()
            items = list(items)
            for index_item in range(len(items)):
                if exists(items[index_item].text(2)):
                    tools.parse_resource(items[index_item])
                else:
                    tools.remove_resource(items[index_item])
                Current.unipage.ui.bar.setValue(int(100 * index_item / len(items)))
            Current.unipage.ui.bar.setValue(0)

            tools.build_blocks()
            tools.build_settings(flag)
        tools.count_bugs()

    def change_options(self, flag: bool):
        if Current.project:
            items = {it for it in Current.unipage.ui.tree_set.selectedItems()}
            for index_top in range(Current.unipage.ui.tree_set.topLevelItemCount()):
                if Current.unipage.ui.tree_set.topLevelItem(index_top) in items:
                    items.remove(Current.unipage.ui.tree_set.topLevelItem(index_top))
                    for index_child in range(Current.unipage.ui.tree_set.topLevelItem(index_top).childCount()):
                        items.add(Current.unipage.ui.tree_set.topLevelItem(index_top).child(index_child))
            for index_top in range(Current.unipage.ui.tree_set.topLevelItemCount()):
                if Current.unipage.ui.tree_set.topLevelItem(index_top).child(5) in items:
                    items.remove(Current.unipage.ui.tree_set.topLevelItem(index_top).child(5))
                    for index_child in range(Current.unipage.ui.tree_set.topLevelItem(index_top).child(5).childCount()):
                        items.add(Current.unipage.ui.tree_set.topLevelItem(index_top).child(5).child(index_child))
            items = {it for it in items if it.text(0)[0] != "标"}
            for item in items:
                tools.previous_option(item, flag)

    def colour_options(self, colour: str):
        if Current.project:
            items = {it for it in Current.unipage.ui.tree_out.selectedItems()}
            for index_top in range(Current.unipage.ui.tree_out.topLevelItemCount()):
                if Current.unipage.ui.tree_out.topLevelItem(index_top) in items:
                    items.remove(Current.unipage.ui.tree_out.topLevelItem(index_top))
                    for index_child in range(Current.unipage.ui.tree_out.topLevelItem(index_top).childCount()):
                        items.add(Current.unipage.ui.tree_out.topLevelItem(index_top).child(index_child))
            for item in items:
                tools.colour_option(item, colour)
            tools.show_options()

    def print_project(self):
        if Current.project:
            for proof in Current.proofs:
                printer.make_pdf(proof)

    def check_print(self):
        # self.parse_resources(True)
        if Current.project:
            Current.unipage.ui.tree_err.clear()
            Current.unipage.ui.tree_war.clear()
            Current.unipage.ui.tree_inf.clear()
            Current.proofs = []
            for set in [set for set in Current.project.prj_set_info if set["blk_cont"]["print"] == 1]:
                proof_dic, proof_bugs = printer.make_proof(set["blk_name"])
                for index_top in range(Current.unipage.ui.tree_set.topLevelItemCount()):
                    if Current.unipage.ui.tree_set.topLevelItem(index_top).text(1) == set["blk_name"]:
                        if [i for i in proof_bugs if i[0] == 0]:
                            Current.unipage.ui.tree_set.topLevelItem(index_top).setText(0, "检查未通过")
                        else:
                            Current.unipage.ui.tree_set.topLevelItem(index_top).setText(0, "检查通过")
                            Current.proofs.append(proof_dic)
                tools.show_bugs(proof_bugs)
            if Current.proofs:
                Current.unipage.ui.act_print.setEnabled(True)
            else:
                Current.unipage.ui.act_print.setEnabled(False)

    def eventFilter(self, object: QObject, event: QEvent):
        if object is self.new_ui.tree_file:
            if event.type() == QEvent.DragEnter and Current.project:
                file_exts = set([splitext(file)[1] for file in event.mimeData().urls])
                accept_exts = set(['.blk', '.att', '.ttf', '.otf'])
                if file_exts - accept_exts == file_exts:
                    event.ignore()
                else:
                    event.accept()
            if event.type() == QEvent.Drop and Current.project:
                for file_url in event.mimeData().urls:
                    dest_url = Current.project.prj_basic_info["project_dir"] + '/' + basename(file_url)
                    tools.input_resource(file_url, dest_url, 0, None, False)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    Current.unipage = Unipage()
    Current.unipage.ui.show()
    sys.exit(app.exec_())
