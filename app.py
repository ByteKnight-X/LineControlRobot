import sys
from typing import Dict
from PyQt5 import QtWidgets, uic
from pathlib import Path
from utilities.constants import STYLE
from import_page import ImportPage
from layering_page import LayeringPage
from routine_page import RoutinePage
from preparation_page import PreparationPage



class MainWindow(QtWidgets.QMainWindow):
    """Main application window that manages different screens."""

    def __init__(self) -> None:
        super().__init__()
        uic.loadUi(str(Path(__file__).parent / "forms" / "main_window.ui"), self) # Load main template
        self.setWindowTitle("Versatile Robotics")
        self.context = {}
        self.pages = {}
        self.setStyleSheet(STYLE)
        
        # Connect navigation buttons
        self.btnImport.clicked.connect(lambda: self.show_page('import_page', self.btnImport))
        self.btnLayering.clicked.connect(lambda: self.show_page('layering_page', self.btnLayering))
        self.btnRoutine.clicked.connect(lambda: self.show_page('routine_page', self.btnRoutine))
        self.btnPreparation.clicked.connect(lambda: self.show_page('preparation_page', self.btnPreparation))
        
        self.show_page('import_page', self.btnImport)
        
                
    def show_page(self, page_name, btn):
        # Load dynamic pages
        if page_name not in self.pages:
            if page_name == 'import_page':
                page = ImportPage(controller=self)
            elif page_name == 'layering_page':
                page = LayeringPage(controller=self)
            elif page_name == 'routine_page':
                page = RoutinePage(controller=self)
            elif page_name == 'preparation_page':
                page = PreparationPage(controller=self)
            else:
                return
            self.stackedRight.addWidget(page)
            self.pages[page_name] = page
        self.stackedRight.setCurrentWidget(self.pages[page_name])

        # Update left-side button highlight
        for b in (self.btnImport, self.btnLayering, self.btnRoutine, self.btnPreparation):
            b.setStyleSheet('font-weight: normal;')
        btn.setStyleSheet('font-weight: bold;')

def main() -> None:
    app = QtWidgets.QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
