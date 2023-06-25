from os.path import basename, splitext
from re import sub

from PySide6.QtUiTools import QUiLoader
from PySide6.QtWidgets import QFileDialog

from current import Current
from tools import input_resource


def _wash_file(string: str) -> str:
    return sub(r"[\\\/\:\*\?\"\<\>\|]", "", string)


class Project:
    new_ui = None

    # project_name, project_dir, project_file
    prj_basic_info = None
    # project, block, font, attribute
    prj_rsc_info = None
    prj_set_info = None
    prj_blk_info = None

    def __init__(self):
        self.new_ui = QUiLoader().load("src/new_project.ui")
        self.new_ui.btn_file.clicked.connect(self.get_url)
        self.new_ui.btn_box.accepted.connect(self.ok)
        self.new_ui.line_name.textChanged.connect(self.update)

        self.prj_basic_info = {}
        self.prj_rsc_info = {"upj": [], "blk": [], "fnt": [], "att": []}
        self.prj_set_info = []
        self.prj_blk_info = []

    def get_url(self):
        project_dir = QFileDialog.getExistingDirectoryUrl(caption="项目路径").toLocalFile()
        if project_dir:
            self.new_ui.line_url.setText(project_dir)
            if _wash_file(self.new_ui.line_name.text()):
                self.new_ui.line_file.setText(f"{project_dir}/{_wash_file(self.new_ui.line_name.text())}.upj")
                self.new_ui.btn_box.setEnabled(True)

    def update(self):
        if _wash_file(self.new_ui.line_name.text()) and self.new_ui.line_url.text():
            self.new_ui.line_file.setText(f"{self.new_ui.line_url.text()}/{_wash_file(self.new_ui.line_name.text())}.upj")
            self.new_ui.btn_box.setEnabled(True)
        else:
            self.new_ui.line_file.setText("")
            self.new_ui.btn_box.setEnabled(False)

    def ok(self):
        Current.project = Project()
        Current.project.prj_basic_info["project_name"] = _wash_file(self.new_ui.line_name.text())
        Current.project.prj_basic_info["project_dir"] = self.new_ui.line_url.text()
        Current.project.prj_basic_info["project_file"] = self.new_ui.line_file.text()

        open(Current.project.prj_basic_info["project_file"], "w")
        input_resource(Current.project.prj_basic_info["project_file"], Current.project.prj_basic_info["project_file"], 2, None, True)
        Current.unipage.ui.setWindowTitle("Unipage  —  " + splitext(basename(Current.project.prj_basic_info["project_name"]))[0])
        Current.unipage.save_project()
