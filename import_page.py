from pathlib import Path
import os
import logging
import requests
from xml.etree import ElementTree as ET
from PyQt5 import QtWidgets, uic, QtWebEngineWidgets
from PyQt5.QtWidgets import QFileDialog, QMessageBox
from PyQt5.QtCore import Qt, QUrl, QObject, pyqtSignal, QThread

logger = logging.getLogger(__name__)


class LayeringRequestWorker(QObject):
    """
    Worker that posts a layering request without blocking the UI.
    """
    finished = pyqtSignal(dict)
    failed = pyqtSignal(str)

    def __init__(self, backend_url: str, payload: dict):
        super().__init__()
        self.backend_url = backend_url
        self.payload = payload

    def run(self) -> None:
        try:
            resp = requests.post(self.backend_url, json=self.payload, timeout=10)
            if not resp.ok:
                self.failed.emit(f"状态码: {resp.status_code}\n{resp.text}")
                return
            try:
                data = resp.json()
            except Exception:
                self.failed.emit(resp.text)
                return
            self.finished.emit(data)
        except Exception as exc:
            self.failed.emit(str(exc))


class TaskOrder:
    """
    Data structure to hold information about the imported task file.
    """
    def __init__(self, file_path: str):
        """
        Initialize and parse the XML task order file.
        """
        self.file_path = file_path
        try:
            self.tree = ET.parse(file_path)
            self.root = self.tree.getroot()
        except Exception as exc:
            raise RuntimeError(f"无法读取或解析XML文件: {exc}") from exc
        self.__parse_content()

    def __parse_content(self) -> None:
        """
        Parse XML leaf nodes into a dictionary and a preview string.
        """
        self.__content_dict = {}
        lines = []
        for elem in self.root.iter():
            if list(elem):
                continue
            tag = elem.tag.split('}')[-1] # Remove namespace if present
            text = (elem.text or "").strip()
            self.__content_dict[tag] = text
            lines.append(f"{tag}: {text}\n")
        self.__content_str = "".join(lines)
    
    def get_content_dict(self) -> dict:
        """
        Return the parsed XML content as a dict.
        """
        return self.__content_dict

    def get_content_str(self) -> str:
        """
        Return a single-string preview of the parsed content.
        """
        return self.__content_str


class ImportPage(QtWidgets.QWidget):
    """
    Interface for importing production task files and design documents.
    """
    def __init__(self, controller):
        """
        Load UI and initialize the import page with the given controller.
        """
        super().__init__()
        uic.loadUi(str(Path(__file__).resolve().parent / "forms" / "import_page.ui"), self)
        self.controller = controller
        self.setup_ui()

    def setup_ui(self) -> None:
        """
        Connect UI signals and set initial widget states.
        """
        self.btnSelectTask.clicked.connect(self.open_task_file)
        self.btnNextStep.clicked.connect(self.start_layering)
        self.btnNextStep.setEnabled(False)

        # Set up edit mode toggle
        self._is_editing = False
        self.btnEditTask.setText("编辑任务单")
        self.btnEditTask.clicked.connect(self.toggle_edit_mode)
        
        # Disable context menu on pattern design preview
        self.patternDesign.setContextMenuPolicy(Qt.NoContextMenu)

    def toggle_edit_mode(self) -> None:
        """
        Toggle the edit state of instruction fields and update the edit button label.
        """
        self._is_editing = not self._is_editing
        # Toggle read-only state of all QLineEdit widgets
        form_layout = self.instructionsWidget.layout()
        for i in range(form_layout.rowCount()):
            field = form_layout.itemAt(i, QtWidgets.QFormLayout.FieldRole)
            if field is not None:
                widget = field.widget()
                if isinstance(widget, QtWidgets.QLineEdit):
                    widget.setReadOnly(not self._is_editing)
        # Toggle button text
        if self._is_editing:
            self.btnEditTask.setText("保存任务单")
        else:
            self.btnEditTask.setText("编辑任务单")
            # Save edited values to context when exiting edit mode
            self._save_task_order_to_context()


    def open_task_file(self) -> None:
        """
        Prompt the user to select a task XML, parse it, and update the UI preview.
        """
        # Open file dialog to select task file
        task_file_path, _ = QFileDialog.getOpenFileName(self, "选择生产任务单", "", "XML Files (*.xml)")
        if not task_file_path:
            print("No task file selected.")
            return

        # Load and preview the selected task file
        task_order = TaskOrder(task_file_path)
        self._work_order_dir = os.path.dirname(task_file_path)
        
        # Populate form inside QScrollArea for structured display
        try:
            self._populate_instructions_form(task_order.get_content_dict())
        except Exception:
            # Fallback to simple text if something unexpected happens
            form_layout = self.instructionsWidget.layout()
            self._clear_form_layout(form_layout)
            val_lbl = QtWidgets.QLabel(task_order.get_content_str())
            val_lbl.setWordWrap(True)
            form_layout.addRow(QtWidgets.QLabel("Preview:"), val_lbl)
        
        # Load design pattern
        pattern_design_path = task_order.get_content_dict().get("图案设计", "")
        if not self._load_svg_into_pattern_design(pattern_design_path, self._work_order_dir):
            return
        
        self.btnNextStep.setEnabled(True)
        self.controller.context['task_order'] = task_order.get_content_dict()
    

    def start_layering(self) -> None:
        """
        Collect form data, request a layering plan from the backend, and navigate on success.
        """
        edited = self._collect_form_values()
        
        if not edited:
            QMessageBox.warning(self, "缺少任务信息", "请先导入并保存任务单。")
            return

        payload = {
            "Header": {
                "fileId": edited.get("文件编号"),
                "deliveryDate": edited.get("交付日期"),
            },
            "Item": {
                "sku": edited.get("货号"),
                "partName": edited.get("部件"),
                "colorway": edited.get("配色"),
                "sizeRanges": self._split_list(edited.get("码段")),
                "quantities": self._normalize_quantities(edited.get("数量")),
                "fabricMaterial": edited.get("面料材质"),
                "fabricThickness": float(edited.get("面料厚度", 0)),
                "baseLayerThickness": float(edited.get("打底层厚", 0)),
                "inkLayerThickness": float(edited.get("油墨层厚", 0)),
                "designGraphic": edited.get("图案设计"),
            },
            "Quality": {
                "colorFastness": {
                    "dryRubbing": edited.get("干摩擦"),
                    "wetRubbing": edited.get("湿摩擦"),
                    "waterFastness": edited.get("水牢度"),
                },
                "foldResistanceCount": int(edited.get("耐折次数", 0)),
            },
        }

        self._request_layering(payload)


    def _request_layering(self, payload: dict) -> None:
        """
        Dispatch a layering request in a background thread.
        """
        backend_url = "http://127.0.0.1:8000/tasks/import"
        self.btnNextStep.setEnabled(False)
        self._layering_thread = QThread(self)
        self._layering_worker = LayeringRequestWorker(backend_url, payload)
        self._layering_worker.moveToThread(self._layering_thread)
        self._layering_thread.started.connect(self._layering_worker.run)
        self._layering_worker.finished.connect(self._on_layering_success)
        self._layering_worker.failed.connect(self._on_layering_failed)
        self._layering_worker.finished.connect(self._layering_thread.quit)
        self._layering_worker.failed.connect(self._layering_thread.quit)
        self._layering_thread.finished.connect(self._layering_worker.deleteLater)
        self._layering_thread.finished.connect(self._layering_thread.deleteLater)
        self._layering_thread.start()

    def _on_layering_success(self, message: dict) -> None:
        """Switch to the layering page on successful response."""
        self.controller.context["task_id"] = message.get("taskId")
        self.controller.context["separation_plan"] = message.get("separationPlan")
        self.controller.context["sop"] = message.get("sop")                          
        self.controller.show_page('layering_page', self.controller.btnLayering)
        self.btnNextStep.setEnabled(True)

    def _on_layering_failed(self, message: str) -> None:
        """Display an error message on layering failure."""
        QMessageBox.critical(self, "获取分层计划失败", message or "未知错误")
        self.btnNextStep.setEnabled(True)

    def _collect_form_values(self) -> dict:
        """
        Collect values from the instructions form into a dict.
        """
        form_layout = self.instructionsWidget.layout()
        edited = {}
        for i in range(form_layout.rowCount()):
            lbl_item = form_layout.itemAt(i, QtWidgets.QFormLayout.LabelRole)
            val_item = form_layout.itemAt(i, QtWidgets.QFormLayout.FieldRole)
            key = lbl_item.widget().text().strip() if lbl_item and lbl_item.widget() else None
            val = val_item.widget().text().strip() if val_item and val_item.widget() else None
            if key:
                edited[key] = val if val is not None else ""
        return edited
    
    def _save_task_order_to_context(self) -> None:
        """
        Collect edited form values and save to context.
        """
        edited = self._collect_form_values()
        if edited:
            self.controller.context['task_order'] = edited
            logger.info("Task order saved to context: %s", edited)

    def _populate_instructions_form(self, content: dict) -> None:
        """
        Populate the instructions form with key/value rows using QLineEdit widgets.
        """
        # clear existing
        form_layout = self.instructionsWidget.layout()
        self._clear_form_layout(form_layout)

        # layout spacing for cleaner look
        form_layout.setHorizontalSpacing(4)
        form_layout.setVerticalSpacing(8)
        self.instructionsWidget.setContentsMargins(2, 6, 6, 6)


        # Populate entries
        for key, value in content.items():
            # name label: centered, no border
            name_lbl = QtWidgets.QLabel(f"{key}")
            name_lbl.setMinimumWidth(80)
            name_lbl.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)  
            name_lbl.setStyleSheet("border: none; font-size: 12px; font-weight: 600; padding: 0 2px;")
            
            logger.debug("%s = %s", name_lbl.text(), value)

            # value editor: single-line editable control, initially read-only, max 80 chars
            val_edit = QtWidgets.QLineEdit(value if value is not None else "")
            val_edit.setMaxLength(80)                
            val_edit.setReadOnly(True)               
            val_edit.setFrame(False)                 
            val_edit.setStyleSheet("background: transparent; font-size: 12px; padding: 0 2px;")
            # val_edit.setToolTip(value if value is not None else "")
            val_edit.setMinimumWidth(80)

            form_layout.addRow(name_lbl, val_edit)

    def _clear_form_layout(self, form_layout) -> None:
        """
        Remove all widgets and child layouts from the given layout.
        """
        # QFormLayout supports rowCount/removeRow
        if hasattr(form_layout, "rowCount"):
            for row in range(form_layout.rowCount() - 1, -1, -1):
                for role in (QtWidgets.QFormLayout.LabelRole, QtWidgets.QFormLayout.FieldRole):
                    item = form_layout.itemAt(row, role)
                    if item is None:
                        continue
                    widget = item.widget()
                    if widget is not None:
                        widget.setParent(None)
                        widget.deleteLater()
                form_layout.removeRow(row)
            return

        # General QLayout clearing logic
        while form_layout.count():
            item = form_layout.takeAt(0)
            if item is None:
                continue
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
            child_layout = item.layout()
            if child_layout is not None:
                self._clear_form_layout(child_layout)

    def _load_svg_into_pattern_design(self, svg_path: str, base_dir: str = "") -> bool:
        """
        Validate and load an SVG file into the pattern preview widget.
        """
        if not svg_path.lower().endswith(".svg"):
            QMessageBox.warning(self, "格式错误", "仅支持SVG文件。")
            return False
        if svg_path and not os.path.isabs(svg_path) and base_dir:
            svg_path = os.path.join(base_dir, svg_path)
        if not os.path.exists(svg_path):
            QMessageBox.warning(self, "缺失文件", f"SVG不存在:\n{svg_path}")
            return False
        # Use QWebEngineView to load local file (better filter/mask support)
        self.patternDesign.load(QUrl.fromLocalFile(os.path.abspath(svg_path)))
        return True
    
    def _normalize_quantities(self, raw):
        """
        Normalize quantity values into a list with ints when possible.
        """
        items = self._split_list(raw)
        return [int(x) if str(x).isdigit() else x for x in items]

    def _split_list(self, s):
        """
        Split a string or list into a cleaned list using '|' or ',' as separators.
        """
        if not s:
            return []
        if isinstance(s, str):
            for ch in ("，", "、", "；", ";"):
                s = s.replace(ch, ",")
            sep = "|" if "|" in s else ","
            return [p.strip() for p in s.split(sep) if p.strip()]
        if isinstance(s, list):
            return s
        return [s]


