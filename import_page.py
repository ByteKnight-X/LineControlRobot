from pathlib import Path
from typing import Optional

from PyQt5 import QtWidgets, uic
from PyQt5.QtWidgets import QFileDialog, QMessageBox


HIGHLIGHT_STYLE = "background-color: #3478f6; color: white;"
DEFAULT_STYLE = ""


class ImportPage(QtWidgets.QWidget):
    """
    Interface for importing production task files and design documents.
    """

    def __init__(self, controller):
        super().__init__()
        uic.loadUi("forms/import_task.ui", self)
        self.controller = controller
        self.selected_task_path: Optional[Path] = None
        self.selected_design_path: Optional[Path] = None
        # self.setup_ui()


    def setup_ui(self) -> None:
        self.selectTaskButton.clicked.connect(self.open_task_file)
        self.startLayerButton.clicked.connect(self.goto_screen_layering)
        self.startLayerButton.setEnabled(False)

    def on_show(self) -> None:
        self._highlight_navigation(self.navImportButton)

    def _highlight_navigation(self, active_button: QtWidgets.QPushButton) -> None:
        for button in [self.navImportButton, self.navLayerButton, self.navProcessButton, self.navProductionButton]:
            if button is active_button:
                button.setStyleSheet(HIGHLIGHT_STYLE)
                button.setChecked(True)
            else:
                button.setStyleSheet(DEFAULT_STYLE)
                button.setChecked(False)

    def open_task_file(self) -> None:
        xml_path, _ = QFileDialog.getOpenFileName(self, "选择生产任务单", "", "XML Files (*.xml)")
        if not xml_path:
            return

        design_path, _ = QFileDialog.getOpenFileName(self, "选择图案设计文档", "", "SVG Files (*.svg)")
        if not design_path:
            QMessageBox.information(self, "提示", "未选择图案设计文档，将使用占位信息展示。")

        self.selected_task_path = Path(xml_path)
        self.selected_design_path = Path(design_path) if design_path else None

        self.taskTextEdit.setPlainText(self._read_file_preview(self.selected_task_path))
        if self.selected_design_path:
            self.designTextEdit.setPlainText(self._read_file_preview(self.selected_design_path))
        else:
            self.designTextEdit.setPlainText("未选择图案设计文档，请稍后补充。")

        self.controller.layering_data = self.controller.layering_data or self._default_layering_data()
        self.controller.production_plan = self.controller.production_plan or self._default_production_plan()
        self.controller.quality_plan = self.controller.quality_plan or self._default_quality_plan()

        self.startLayerButton.setEnabled(True)

    def _read_file_preview(self, file_path: Path) -> str:
        try:
            content = file_path.read_text(encoding="utf-8")
        except Exception as exc:  # pylint: disable=broad-except
            return f"无法读取文件: {exc}"
        if len(content) > 3000:
            return content[:3000] + "\n..."
        return content

    def goto_screen_layering(self) -> None:
        if not self.selected_task_path:
            QMessageBox.warning(self, "提示", "请先选择生产任务单。")
            return
        self.controller.show_screen("layering")

    @staticmethod
    def _default_layering_data():
        return [
            {
                "name": "网版A",
                "aperture": "35 μm",
                "tension": "24 N",
                "ink": "白色油墨",
                "svg": "design_a.svg",
            },
            {
                "name": "网版B",
                "aperture": "30 μm",
                "tension": "26 N",
                "ink": "黑色油墨",
                "svg": "design_b.svg",
            },
            {
                "name": "网版C",
                "aperture": "28 μm",
                "tension": "25 N",
                "ink": "红色油墨",
                "svg": "design_c.svg",
            },
        ]

    @staticmethod
    def _default_production_plan() -> str:
        return (
            "1. 准备印刷工位和夹具\n"
            "2. 按订单顺序排产\n"
            "3. 设置丝印机运行参数\n"
            "4. 准备对应颜色油墨与刮刀"
        )

    @staticmethod
    def _default_quality_plan() -> str:
        return (
            "1. 首件外观检测\n"
            "2. 随机抽检网版完整性\n"
            "3. 出厂前全检确认"
        )
