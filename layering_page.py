from typing import List, Optional
from PyQt5 import QtWidgets, uic




class LayeringPage(QtWidgets.QWidget):
    """网版分层界面控制器。"""

    def __init__(self, controller):
        super().__init__()
        uic.loadUi("forms/layering_page.ui", self)
        self.controller = controller
        self.current_index = 0

    def _init_nav(self) -> None:
        self.navImportButton.clicked.connect(lambda: self.controller.show_screen("import"))
        self.navLayerButton.clicked.connect(lambda: self.controller.show_screen("layering"))
        self.navProcessButton.clicked.connect(lambda: self.controller.show_screen("process"))
        self.navProductionButton.clicked.connect(lambda: self.controller.show_screen("preparation"))

    def _init_controls(self) -> None:
        self.previousButton.clicked.connect(self.show_previous)
        self.nextButton.clicked.connect(self.show_next)
        self.editButton.clicked.connect(self.toggle_edit)
        self.startProcessPlanningButton.clicked.connect(lambda: self.controller.show_screen("process"))
        self._set_parameters_editable(False)

    def on_show(self) -> None:
        self._highlight_navigation(self.navLayerButton)
        self._refresh_display()

    def _highlight_navigation(self, active_button: QtWidgets.QPushButton) -> None:
        for button in [self.navImportButton, self.navLayerButton, self.navProcessButton, self.navProductionButton]:
            if button is active_button:
                button.setStyleSheet(HIGHLIGHT_STYLE)
                button.setChecked(True)
            else:
                button.setStyleSheet(DEFAULT_STYLE)
                button.setChecked(False)

    def _refresh_display(self) -> None:
        screens: Optional[List[dict]] = self.controller.layering_data
        if not screens:
            self.screenDisplayLabel.setText("暂未导入网版信息")
            self.apertureEdit.setText("")
            self.tensionEdit.setText("")
            self.inkEdit.setText("")
            return

        self.current_index = max(0, min(self.current_index, len(screens) - 1))
        current = screens[self.current_index]
        self.screenDisplayLabel.setText(f"{current['name']}\n({current['svg']})")
        self.apertureEdit.setText(current.get("aperture", ""))
        self.tensionEdit.setText(current.get("tension", ""))
        self.inkEdit.setText(current.get("ink", ""))

    def show_previous(self) -> None:
        if not self.controller.layering_data:
            return
        self.current_index = (self.current_index - 1) % len(self.controller.layering_data)
        self._refresh_display()

    def show_next(self) -> None:
        if not self.controller.layering_data:
            return
        self.current_index = (self.current_index + 1) % len(self.controller.layering_data)
        self._refresh_display()

    def toggle_edit(self) -> None:
        editable = self.apertureEdit.isReadOnly()
        self._set_parameters_editable(editable)
        if editable:
            self.editButton.setText("保存信息")
        else:
            self._save_current_parameters()
            self.editButton.setText("编辑网版")

    def _set_parameters_editable(self, editable: bool) -> None:
        for field in [self.apertureEdit, self.tensionEdit, self.inkEdit]:
            field.setReadOnly(not editable)
            palette = field.palette()
            if editable:
                palette.setColor(field.backgroundRole(), field.palette().color(field.backgroundRole()))
            field.setPalette(palette)

    def _save_current_parameters(self) -> None:
        if not self.controller.layering_data:
            return
        current = self.controller.layering_data[self.current_index]
        current["aperture"] = self.apertureEdit.text()
        current["tension"] = self.tensionEdit.text()
        current["ink"] = self.inkEdit.text()

