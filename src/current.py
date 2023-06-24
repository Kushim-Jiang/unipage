class Current:
    # Unipage 主界面，数据类型 Unipage
    unipage = None
    project = None
    tmp_project = None
    proofs = []

    def files(dct: dict = None):
        if dct is None:
            if Current.project and Current.project.prj_rsc_info != None:
                return (
                    Current.project.prj_rsc_info["upj"]
                    + Current.project.prj_rsc_info["blk"]
                    + Current.project.prj_rsc_info["fnt"]
                    + Current.project.prj_rsc_info["att"]
                )
            else:
                return []
        else:
            return dct["rsc_info"]["upj"] + dct["rsc_info"]["blk"] + dct["rsc_info"]["fnt"] + dct["rsc_info"]["att"]
