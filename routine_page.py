from PyQt5 import QtWidgets, uic


class RoutinePage(QtWidgets.QWidget):
    """工艺规划界面控制器。"""

    def __init__(self, controller):
        super().__init__()
        uic.loadUi("forms/routine_page.ui", self)
        self.controller = controller
        self.setup_ui()
    
    def setup_ui(self) -> None:
        """Set up UI components and connect signals."""
        self.btnStartScheduling.clicked.connect(
            lambda: self.controller.show_page("preparation_page", self.controller.btnPreparation)
        )