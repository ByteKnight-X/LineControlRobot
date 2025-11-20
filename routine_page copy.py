from PyQt5 import QtWidgets, uic
from utilities.constants import DEFAULT_ROUTINE_LISTS


class RoutinePage(QtWidgets.QWidget):
    """Routine page."""

    def __init__(self, controller):
        super().__init__()
        uic.loadUi("forms/routine_page.ui", self)
        self.controller = controller
        self.setup_ui()
    
    def setup_ui(self) -> None:
        """Set up UI components and connect signals."""
        # Set initial state: text edit is read-only
        self.productionListTextEdit.setReadOnly(True)
        self.productionListTextEdit.setText(DEFAULT_ROUTINE_LISTS)
        
        # Connect edit button to toggle edit mode
        self.btnEditProduction.clicked.connect(self.toggle_edit_mode)
        self.btnStartScheduling.clicked.connect(
            lambda: self.controller.show_page("preparation_page", self.controller.btnPreparation)
        )
    
    def toggle_edit_mode(self) -> None:
        """Toggle between edit and save mode for the production list."""
        if self.productionListTextEdit.isReadOnly():
            # Switch to edit mode
            self.productionListTextEdit.setReadOnly(False)
            self.btnEditProduction.setText("保存清单")
        else:
            # Switch to save mode (back to read-only)
            self.productionListTextEdit.setReadOnly(True)
            self.btnEditProduction.setText("编辑清单")