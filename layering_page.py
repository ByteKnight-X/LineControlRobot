from typing import List, Optional
from PyQt5 import QtWidgets, uic
from PyQt5.QtGui import QPixmap
from PyQt5.QtCore import Qt


class LayeringPage(QtWidgets.QWidget):
    """
    Layering page.
    """
    def __init__(self, controller):
        super().__init__()
        uic.loadUi("forms/layering_page.ui", self)
        self.controller = controller
        self.layer_data = controller.context.get("layering_data", [])
        self.current_index = 0
        self.setup_ui()
        self.refresh_display()

    def setup_ui(self):
        """
        Set up UI components and connect signals.
        """
        self.btnPrevLayer.clicked.connect(self.show_previous)
        self.btnNextLayer.clicked.connect(self.show_next)
        self.btnStartProcessPlanning.clicked.connect(
                lambda: self.controller.show_page("process_planning_page", self.controller.btnProcessPlanning)
            )
        
    def refresh_display(self) -> None:
        """
        Refresh the layer preview display.
        """
        cur_frame_path = self.layer_data[self.current_index]
        frame = QPixmap(cur_frame_path)
        if not frame.isNull():
            self.layerPreview.setPixmap(
                frame.scaled(
                    self.layerPreview.size(),
                    aspectRatioMode=Qt.AspectRatioMode.KeepAspectRatio,
                )
            )
    
    def show_previous(self) -> None:
        """
        Show the previous layer.
        """
        if not self.layer_data:
            return
        self.current_index = (self.current_index - 1) % len(self.layer_data)
        self.refresh_display()

    def show_next(self) -> None:
        """
        Show the next layer.
        """
        if not self.layer_data:
            return
        self.current_index = (self.current_index + 1) % len(self.layer_data)
        self.refresh_display()


    

