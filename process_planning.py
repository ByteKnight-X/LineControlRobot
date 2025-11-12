from PyQt5 import QtWidgets, uic

from import_task import HIGHLIGHT_STYLE, DEFAULT_STYLE


class ProcessPlanningScreen(QtWidgets.QWidget):
    """工艺规划界面控制器。"""

    def __init__(self, controller):
        super().__init__()
        uic.loadUi("forms/process_planning.ui", self)
        self.controller = controller

        self._init_nav()
        self._init_controls()

    def _init_nav(self) -> None:
        self.navImportButton.clicked.connect(lambda: self.controller.show_screen("import"))
        self.navLayerButton.clicked.connect(lambda: self.controller.show_screen("layering"))
        self.navProcessButton.clicked.connect(lambda: self.controller.show_screen("process"))
        self.navProductionButton.clicked.connect(lambda: self.controller.show_screen("preparation"))

    def _init_controls(self) -> None:
        self.editProductionButton.clicked.connect(self.toggle_production_edit)
        self.editQualityButton.clicked.connect(self.toggle_quality_edit)
        self.startProductionButton.clicked.connect(lambda: self.controller.show_screen("preparation"))

    def on_show(self) -> None:
        self._highlight_navigation(self.navProcessButton)
        self._refresh_texts()

    def _highlight_navigation(self, active_button: QtWidgets.QPushButton) -> None:
        for button in [self.navImportButton, self.navLayerButton, self.navProcessButton, self.navProductionButton]:
            if button is active_button:
                button.setStyleSheet(HIGHLIGHT_STYLE)
                button.setChecked(True)
            else:
                button.setStyleSheet(DEFAULT_STYLE)
                button.setChecked(False)

    def _refresh_texts(self) -> None:
        self.productionTextEdit.setPlainText(self.controller.production_plan or "")
        self.qualityTextEdit.setPlainText(self.controller.quality_plan or "")
        self.productionTextEdit.setReadOnly(True)
        self.qualityTextEdit.setReadOnly(True)
        self.editProductionButton.setText("编辑生产清单")
        self.editQualityButton.setText("编辑质检清单")

    def toggle_production_edit(self) -> None:
        editing = self.productionTextEdit.isReadOnly()
        self.productionTextEdit.setReadOnly(not editing)
        if editing:
            self.editProductionButton.setText("保存生产清单")
        else:
            self.controller.production_plan = self.productionTextEdit.toPlainText()
            self.editProductionButton.setText("编辑生产清单")

    def toggle_quality_edit(self) -> None:
        editing = self.qualityTextEdit.isReadOnly()
        self.qualityTextEdit.setReadOnly(not editing)
        if editing:
            self.editQualityButton.setText("保存质检清单")
        else:
            self.controller.quality_plan = self.qualityTextEdit.toPlainText()
            self.editQualityButton.setText("编辑质检清单")

