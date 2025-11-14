from PyQt5 import QtWidgets, uic


class ProcessPlanningPage(QtWidgets.QWidget):
    """工艺规划界面控制器。"""

    def __init__(self, controller):
        super().__init__()
        uic.loadUi("forms/process_planning_page.ui", self)
        self.controller = controller
        self.setup_ui()
    
    def setup_ui(self) -> None:
        """Set up UI components and connect signals."""
        self.btnStartProductionPreparation.clicked.connect(
            lambda: self.controller.show_page("production_preparation_page", self.controller.btnProductionPreparation)
        )