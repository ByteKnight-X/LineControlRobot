from typing import List

from PyQt5 import QtWidgets, uic

from import_task import HIGHLIGHT_STYLE, DEFAULT_STYLE


class ProductionPreparationScreen(QtWidgets.QWidget):
    """生产准备界面控制器。"""

    def __init__(self, controller):
        super().__init__()
        uic.loadUi("forms/production_preparation.ui", self)
        self.controller = controller
        self.action_checkboxes: List[QtWidgets.QCheckBox] = []

        self._init_nav()
        self._cache_checkboxes()
        self._init_controls()

    def _init_nav(self) -> None:
        self.navImportButton.clicked.connect(lambda: self.controller.show_screen("import"))
        self.navLayerButton.clicked.connect(lambda: self.controller.show_screen("layering"))
        self.navProcessButton.clicked.connect(lambda: self.controller.show_screen("process"))
        self.navProductionButton.clicked.connect(lambda: self.controller.show_screen("preparation"))

    def _cache_checkboxes(self) -> None:
        self.action_checkboxes = [
            self.actionCheckBox1,
            self.actionCheckBox2,
            self.actionCheckBox3,
            self.actionCheckBox4,
            self.actionCheckBox5,
        ]

    def _init_controls(self) -> None:
        for checkbox in self.action_checkboxes:
            checkbox.stateChanged.connect(self._update_start_button_state)
        self.startProductionButton.clicked.connect(self._start_production)
        self.startProductionButton.setEnabled(False)

    def on_show(self) -> None:
        self._highlight_navigation(self.navProductionButton)
        self._reset_actions()

    def _highlight_navigation(self, active_button: QtWidgets.QPushButton) -> None:
        for button in [self.navImportButton, self.navLayerButton, self.navProcessButton, self.navProductionButton]:
            if button is active_button:
                button.setStyleSheet(HIGHLIGHT_STYLE)
                button.setChecked(True)
            else:
                button.setStyleSheet(DEFAULT_STYLE)
                button.setChecked(False)

    def _reset_actions(self) -> None:
        for checkbox in self.action_checkboxes:
            checkbox.setChecked(False)
        self.startProductionButton.setEnabled(False)

    def _update_start_button_state(self) -> None:
        all_checked = all(box.isChecked() for box in self.action_checkboxes)
        self.startProductionButton.setEnabled(all_checked)

    def _start_production(self) -> None:
        QtWidgets.QMessageBox.information(self, "提示", "所有准备工作完成，可以开始生产。")
        self.controller.show_screen("import")

