import sys
from typing import Dict
from PyQt5 import QtWidgets, uic
from pathlib import Path
from utilities.constants import STYLE
from import_task import ImportPage


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
        self.btnImport.clicked.connect(lambda: self.show_page('import', self.btnImport))
        
        self.show_page('import', self.btnImport)
        
                
        """
        # stacked widget 和页面引用（在 main_window.ui 中定义）
        # 名称为 stackedRight、importPage、layeringPage、processPage、preparationPage
        self._stack = self.findChild(QtWidgets.QStackedWidget, "stackedRight")
        self.importPage = self.findChild(QtWidgets.QWidget, "importPage")
        self.layeringPage = self.findChild(QtWidgets.QWidget, "layeringPage")
        self.processPage = self.findChild(QtWidgets.QWidget, "processPage")
        self.preparationPage = self.findChild(QtWidgets.QWidget, "preparationPage")

        # 每个 page 内部有个占位 widget（在 main_window.ui 中分别命名 importPageContent 等）
        # 把对应的子 UI 加载到这些占位处
        uic.loadUi(str(Path(__file__).parent / "forms" / "import_task.ui"), self.findChild(QtWidgets.QWidget, "importPageContent"))
        uic.loadUi(str(Path(__file__).parent / "forms" / "screen_layering.ui"), self.findChild(QtWidgets.QWidget, "layeringPageContent"))
        uic.loadUi(str(Path(__file__).parent / "forms" / "process_planning.ui"), self.findChild(QtWidgets.QWidget, "processPageContent"))
        uic.loadUi(str(Path(__file__).parent / "forms" / "production_preparation.ui"), self.findChild(QtWidgets.QWidget, "preparationPageContent"))

        # 连接左侧导航按钮，切换 stacked 页
        self.navImportButton.clicked.connect(lambda: self._stack.setCurrentWidget(self.importPage))
        self.navLayerButton.clicked.connect(lambda: self._stack.setCurrentWidget(self.layeringPage))
        self.navProcessButton.clicked.connect(lambda: self._stack.setCurrentWidget(self.processPage))
        self.navPreparationButton.clicked.connect(lambda: self._stack.setCurrentWidget(self.preparationPage))

        # 初始显示
        self._stack.setCurrentWidget(self.importPage)
    
        """
        
    def show_page(self, page_name, btn):
        # Load dynamic pages
        if page_name not in self.pages:
            if page_name == 'import':
                page = ImportPage(controller=self)
            # elif page_name == 'planning':
            #    page = PlanningPage(parent=self)
            # elif page_name == 'execution':
            #    page = ExecutionPage(parent=self)
            # elif page_name == 'planning_progress':
            #    page = PlanningProgressPage(parent=self)
            else:
                return
            self.stackedRight.addWidget(page)
            self.pages[page_name] = page
        self.stackedRight.setCurrentWidget(self.pages[page_name])


def main() -> None:
    app = QtWidgets.QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
