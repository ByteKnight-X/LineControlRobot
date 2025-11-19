from typing import List
from utilities.constants import DEFAULT_EQUIPMENT_INSTRUCTION_LISTS
from PyQt5 import QtWidgets, uic


class PreparationPage(QtWidgets.QWidget):
    """生产准备界面控制器。"""

    def __init__(self, controller):
        super().__init__()
        uic.loadUi("forms/preparation_page.ui", self)
        self.controller = controller
        self.action_checkboxes: List[QtWidgets.QCheckBox] = []
        self.setup_ui()
    
    def setup_ui(self) -> None:
        """Set up UI components and connect signals."""
        # Set initial state: text edit is read-only
        self.preparationTextEdit.setReadOnly(True)
        self.preparationTextEdit.setText(DEFAULT_EQUIPMENT_INSTRUCTION_LISTS)
        
        # Connect edit button to toggle edit mode
        self.btnEditList.clicked.connect(self.toggle_edit_mode)
        
        # Connect issue instructions button
        self.btnIssueInstructions.clicked.connect(self.issue_instructions)
    
    def toggle_edit_mode(self) -> None:
        """Toggle between edit and save mode for the preparation list."""
        if self.preparationTextEdit.isReadOnly():
            # Switch to edit mode
            self.preparationTextEdit.setReadOnly(False)
            self.btnEditList.setText("保存清单")
        else:
            # Switch to save mode (back to read-only)
            self.preparationTextEdit.setReadOnly(True)
            self.btnEditList.setText("编辑清单")
    
    def issue_instructions(self) -> None:
        """Issue instructions."""
        pass



