from typing import List

from PyQt5 import QtWidgets, uic



class PreparationPage(QtWidgets.QWidget):
    """生产准备界面控制器。"""

    def __init__(self, controller):
        super().__init__()
        uic.loadUi("forms/preparation_page.ui", self)
        self.controller = controller
        self.action_checkboxes: List[QtWidgets.QCheckBox] = []


    
