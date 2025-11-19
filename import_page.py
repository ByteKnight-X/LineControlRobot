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
        self.btnStartLayering.clicked.connect(self.start_layering)
        self.btnStartLayering.setEnabled(False)

    def open_task_file(self) -> None:
        # Open file dialog to select task file
        task_file_path, _ = QFileDialog.getOpenFileName(self, "选择生产任务单", "", "XML Files (*.xml)")
        if not task_file_path:
            print("No task file selected.")
            return

        # Load and preview the selected task file
        work_order = WorkOrder(task_file_path)
        self.txtInstructions.setPlainText(work_order.get_content_str())
        
        # Load design pattern
        pattern_design_path = work_order.get_content_dict().get("DesignDocument", "")
        pattern_design_path = pattern_design_path.strip().strip('"')
        if not os.path.exists(pattern_design_path):
            QMessageBox.warning(self, "", f"Pa设计文档不存在:\n{pattern_design_path}")
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
        
        self.btnStartLayering.setEnabled(True)
        self.controller.context['work_order'] = work_order.get_content_dict()
        print(self.controller.context['work_order'])

    def start_layering(self) -> None:
        print("Starting layering...")
        self.controller.context['layering_data'] = [
            r"resource\layers\8Pro.svg",
            r"resource\layers\OneItem_1.svg"
        ]
        self.controller.show_page('layering_page', self.controller.btnLayering)
    