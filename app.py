import sys
from typing import Dict

from PyQt5 import QtWidgets

from import_task import ImportTaskScreen
from process_planning import ProcessPlanningScreen
from production_preparation import ProductionPreparationScreen
from screen_layering import ScreenLayeringScreen


class MainWindow(QtWidgets.QMainWindow):
    """多智能体协作流程主窗口。"""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("运动鞋面丝印协作平台")
        self.resize(1024, 640)

        self.layering_data = []
        self.production_plan = ""
        self.quality_plan = ""

        self._stack = QtWidgets.QStackedWidget()
        self.setCentralWidget(self._stack)

        self._screens: Dict[str, QtWidgets.QWidget] = {
            "import": ImportTaskScreen(self),
            "layering": ScreenLayeringScreen(self),
            "process": ProcessPlanningScreen(self),
            "preparation": ProductionPreparationScreen(self),
        }

        for screen in self._screens.values():
            self._stack.addWidget(screen)

        self.show_screen("import")

    def show_screen(self, screen_name: str) -> None:
        screen = self._screens.get(screen_name)
        if not screen:
            return
        self._stack.setCurrentWidget(screen)
        if hasattr(screen, "on_show"):
            screen.on_show()


def main() -> None:
    app = QtWidgets.QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
