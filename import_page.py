from pathlib import Path
from typing import Optional
from xml.etree import ElementTree as ET
from PyQt5 import QtWidgets, uic
from PyQt5.QtWidgets import QFileDialog, QMessageBox
from PyQt5.QtGui import QPixmap
from PyQt5.QtCore import Qt
import os


class WorkOrder:
    """
    Data structure to hold information about the imported task file.
    """
    def __init__(self, file_path: str):
        """ Parse the XML file """
        self.file_path = file_path
        try:
            self.tree = ET.parse(file_path)
            self.root = self.tree.getroot()
        except Exception as exc:
            raise RuntimeError(f"无法读取或解析XML文件: {exc}")
        self.__parse_content()

    def __parse_content(self) -> None:
        """ Parse XML content into dictionary and formatted string. """
        self.__content_dict = {}
        lines = []
        for elem in self.root.iter():
            if list(elem):
                continue
            tag = elem.tag.split('}')[-1] # Remove namespace if present
            text = (elem.text or "").strip()
            self.__content_dict[tag] = text
            lines.append(f"{tag.capitalize()}: {text}\n")
            print(f"{tag.capitalize()}: {text}")
        self.__content_str = "".join(lines)
    
    def get_content_dict(self) -> dict:
        """Parse the XML and return content as a dictionary."""
        return self.__content_dict

    def get_content_str(self) -> str:
        """Return content formatted for preview."""
        return self.__content_str
    

class ImportPage(QtWidgets.QWidget):
    """
    Interface for importing production task files and design documents.
    """

    def __init__(self, controller):
        super().__init__()
        uic.loadUi("forms/import_page.ui", self)
        self.controller = controller
        self.setup_ui()


    def setup_ui(self) -> None:
        self.btnSelectTask.clicked.connect(self.open_task_file)
        self.btnNextStep.clicked.connect(self.start_layering)
        self.btnNextStep.setEnabled(False)

        # 编辑/保存按钮状态
        self._is_editing = False
        self.btnEditTask.setText("编辑任务单")
        self.btnEditTask.clicked.connect(self.toggle_edit_mode)

    
    def toggle_edit_mode(self) -> None:
        self._is_editing = not self._is_editing
        # 切换所有 QLineEdit 的只读状态
        form_layout = self.instructionsWidget.layout()
        for i in range(form_layout.rowCount()):
            field = form_layout.itemAt(i, QtWidgets.QFormLayout.FieldRole)
            if field is not None:
                widget = field.widget()
                if isinstance(widget, QtWidgets.QLineEdit):
                    widget.setReadOnly(not self._is_editing)
        # 切换按钮文本
        if self._is_editing:
            self.btnEditTask.setText("保存任务单")
        else:
            self.btnEditTask.setText("编辑任务单")


    def _clear_form_layout(self, form_layout) -> None:
        """Remove all rows/items from a layout (works for QFormLayout and generic QLayout)."""
        # QFormLayout 支持 rowCount/removeRow
        if hasattr(form_layout, "rowCount"):
            while form_layout.rowCount():
                form_layout.removeRow(0)
            return

        # 通用 QLayout 清理逻辑
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


    def _populate_instructions_form(self, content: dict) -> None:
        """Populate the scroll area's form layout with key/value pairs and apply simple styling."""
        form_layout = self.instructionsWidget.layout()
        # clear existing
        self._clear_form_layout(form_layout)

        # layout spacing for cleaner look
        try:
            form_layout.setHorizontalSpacing(4)   # 缩小 label 与 value 的水平间距
            form_layout.setVerticalSpacing(8)
        except Exception:
            pass
        # small inner margin for the container widget
        self.instructionsWidget.setContentsMargins(2, 6, 6, 6)

        for key, value in content.items():
            # name label: centered, no border
            name_lbl = QtWidgets.QLabel(f"{key.capitalize()}")
            name_lbl.setMinimumWidth(80)
            name_lbl.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)  
            name_lbl.setStyleSheet("border: none; font-size: 12px; font-weight: 600; padding: 0 2px;")

            # value editor: single-line editable control, initially read-only, max 80 chars
            val_edit = QtWidgets.QLineEdit(value if value is not None else "")
            val_edit.setMaxLength(80)                
            val_edit.setReadOnly(True)               
            val_edit.setFrame(False)                 
            val_edit.setStyleSheet("background: transparent; font-size: 12px; padding: 0 2px;")
            # val_edit.setToolTip(value if value is not None else "")
            val_edit.setMinimumWidth(80)

            form_layout.addRow(name_lbl, val_edit)


    def open_task_file(self) -> None:
        # Open file dialog to select task file
        task_file_path, _ = QFileDialog.getOpenFileName(self, "选择生产任务单", "", "XML Files (*.xml)")
        if not task_file_path:
            print("No task file selected.")
            return

        # Load and preview the selected task file
        work_order = WorkOrder(task_file_path)
        # Populate form inside QScrollArea for structured display
        try:
            self._populate_instructions_form(work_order.get_content_dict())
        except Exception:
            # fallback to simple text if something unexpected
            # create a single-row display
            form_layout = self.instructionsWidget.layout()
            self._clear_form_layout(form_layout)
            val_lbl = QtWidgets.QLabel(work_order.get_content_str())
            val_lbl.setWordWrap(True)
            form_layout.addRow(QtWidgets.QLabel("Preview:"), val_lbl)
        
        # Load design pattern
        pattern_design_path = work_order.get_content_dict().get("图案设计", "")
        pattern_design_path = pattern_design_path.strip().strip('"')
        if not os.path.exists(pattern_design_path):
            QMessageBox.warning(self, "", f"设计文档不存在:\n{pattern_design_path}")
            return
        pixmap = QPixmap(pattern_design_path)
        if not pixmap.isNull():
            self.patternDesign.setPixmap(
                pixmap.scaled(
                    self.patternDesign.size(),
                    aspectRatioMode=Qt.AspectRatioMode.KeepAspectRatio,
                    transformMode=Qt.TransformationMode.SmoothTransformation
                )
            )
        else:
            QMessageBox.warning(self, "Error", "Image cannot be loaded")
            return
        
        self.btnNextStep.setEnabled(True)
        self.controller.context['work_order'] = work_order.get_content_dict()
        print(self.controller.context['work_order'])

    def start_layering(self) -> None:
        print("Starting layering...")
        pdf_paths = [
            r"resource\layers\8Pro_1.pdf",
            r"resource\layers\OneItem_1.pdf"
        ]
        pdf_contents = []
        for path in pdf_paths:
            try:
                with open(path, "rb") as f:
                    pdf_contents.append(f.read())
            except Exception as e:
                print(f"Failed to read {path}: {e}")
                pdf_contents.append(None)
        self.controller.context['layering_data'] = pdf_contents
        self.controller.show_page('layering_page', self.controller.btnLayering)
