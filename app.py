import sys
from pathlib import Path

from PyQt5 import QtWidgets, uic

from import_page import ImportPage
from monitor_page import MonitorPage
from prepare_page import PreparePage
from routine_page import ProcessRoutePage
from separation_page import SeparationPage
from utilities.backend_client import BackendClient


class PlaceholderPage(QtWidgets.QWidget):
    """Fallback page for areas that do not have a completed implementation yet."""

    def __init__(self, title: str, message: str) -> None:
        super().__init__()
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        title_label = QtWidgets.QLabel(title)
        title_label.setStyleSheet("font-size: 18px; font-weight: 700; color: #262626;")
        body_label = QtWidgets.QLabel(message)
        body_label.setWordWrap(True)
        body_label.setStyleSheet("font-size: 13px; color: #595959;")
        layout.addWidget(title_label)
        layout.addWidget(body_label)
        layout.addStretch(1)


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        uic.loadUi(str(Path(__file__).resolve().parent / "forms" / "main_window.ui"), self)
        self.context = {}  # Shared workflow data across pages.
        self.pages = {}
        self.backend = BackendClient()

        self._nav_buttons = {
            "import_page": self.btnImport,
            "separation_page": self.btnStencil,
            "process_route_page": self.btnRoute,
            "prepare_page": self.btnPrepare,
            "monitor_page": self.btnMonitor,
            "kpi_page": self.btnKpi,
        }
        self._page_factories = {
            "import_page": lambda: ImportPage(controller=self),
            "separation_page": lambda: SeparationPage(controller=self),
            "process_route_page": lambda: ProcessRoutePage(controller=self),
            "prepare_page": lambda: PreparePage(controller=self),
            "monitor_page": lambda: MonitorPage(controller=self),
            "kpi_page": lambda: PlaceholderPage("绩效评估", "绩效评估页面暂未接入新的设计稿。"),
        }

        for page_name, button in self._nav_buttons.items():
            button.clicked.connect(lambda _=False, name=page_name: self.show_page(name))

        self.statusbar.showMessage(f"Backend: {self.backend.base_url}")
        self.show_page("import_page")

    def show_page(self, page_name: str) -> None:
        if page_name == "stencil_page":
            page_name = "separation_page"
        if page_name == "route_page":
            page_name = "process_route_page"
        if page_name not in self.pages:
            factory = self._page_factories.get(page_name)
            if factory is None:
                return
            page = factory()
            self.stackedPages.addWidget(page)
            self.pages[page_name] = page
        page = self.pages[page_name]
        if hasattr(page, "refresh_data"):
            page.refresh_data()
        self.stackedPages.setCurrentWidget(page)

        for name, button in self._nav_buttons.items():
            button.setChecked(name == page_name)

def main() -> None:
    app = QtWidgets.QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
