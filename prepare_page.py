from PyQt5 import QtWidgets, uic
from PyQt5.QtWidgets import QGraphicsScene, QGraphicsRectItem, QGraphicsLineItem, QGraphicsSimpleTextItem
from PyQt5.QtGui import QPen, QBrush, QColor, QPainter, QPolygonF
from PyQt5.QtCore import QRectF, QPointF, Qt
from PyQt5.QtWidgets import QMessageBox
from PyQt5.QtWidgets import QGraphicsSimpleTextItem
from utilities.constants import DEFAULT_ROUTINE_LISTS
import xml.etree.ElementTree as ET
from pathlib import Path
import requests

        


class PreparePage(QtWidgets.QWidget):
    """Routine page."""
    
    def __init__(self, controller):
        super().__init__()
        uic.loadUi("forms/prepare_page.ui", self)
        self.controller = controller
        self.prep = self.controller.context["prep_instructions"]
        if not self.prep:
            raise ValueError("No preparation instructions found in context.")
        self._is_editing = False
        self.setup_ui()
        
    
    def setup_ui(self) -> None:
        # Initialize the four preparation buttons to be checkable and set highlight styles
        self._init_prep_buttons()

        # Connect click events to wrapper methods (handle highlight switch and load content)
        self.btnMeshPreparation.clicked.connect(self.on_click_mesh_prep)
        self.btnInkPreparation.clicked.connect(self.on_click_ink_prep)
        self.btnFabricPreparation.clicked.connect(self.on_click_fabric_prep)
        self.btnEquipmentPreparation.clicked.connect(self.on_click_equipment_prep)
        self.btnEditPlan.clicked.connect(self.toggle_edit_mode)
        self.btnStartMonitoring.clicked.connect(self.next_step)

        # Initial state: keep behavior consistent and show equipment preparation with highlight
        self.on_click_equipment_prep()
        self._active_prep_type = "equipmentPrepInstructions"   # Default active type
    
    
    def toggle_edit_mode(self):
        """Switch between edit/save mode, controlling the editability of prepInfoText."""
        self._is_editing = not self._is_editing
        self.prepInfoText.setReadOnly(not self._is_editing)
        
        if self._is_editing:
            self.btnEditPlan.setText("保存信息")
            self.prepInfoText.setStyleSheet("background-color: #ffffcc;") # Light yellow background to indicate editability
        else:
            self.btnEditPlan.setText("编辑信息")
            self.prepInfoText.setStyleSheet("")
            self._save_edited_text_to_context(self.prepInfoText.toPlainText())

    def _save_edited_text_to_context(self, text: str):
        """Save edited text back to context based on active preparation type."""
        if not text.strip():
            return
        prep = self.controller.context.get("prep_instructions", {})
        key = self._active_prep_type
        steps = prep.get(key, [])
        if steps and isinstance(steps, list) and len(steps) > 0:
            steps[0]["remark"] = text
        else:
            prep[key] = [{"remark": text}]
        
        self.controller.context["prep_instructions"] = prep
        print(f"Saved edited {key} to context:\n{text}")

    def next_step(self):
        """Send prep instructions to backend and proceed to monitoring page."""
        task_id = self.controller.context.get("task_id")
        if not task_id:
            QMessageBox.warning(self, "缺少 task_id", "未找到 task_id，无法分发准备指令。")
            return
        
        prep_instructions = self.controller.context.get("prep_instructions")
        if not prep_instructions:
            QMessageBox.warning(self, "缺少准备指令", "未找到准备指令，无法分发。")
            return
        
        # Package payload for dispatch_prep
        payload = {
            "approved": True,
            "prepInstructions": prep_instructions
        }
        
        url = f"http://127.0.0.1:8000/tasks/{task_id}/dispatch_prep"
        try:
            resp = requests.post(url, json=payload, timeout=10)
        except Exception as exc:
            QMessageBox.critical(self, "请求失败", str(exc))
            return
        
        if not resp.ok:
            print(f"Response error: {resp.status_code}, {resp.text}")
            QMessageBox.critical(self, "分发失败", f"状态码: {resp.status_code}\n{resp.text}")
            return
        
        # Print response
        data = resp.json()
        self.controller.context["dispatch_result"] = data
        print("Dispatch prep response:")
        print(data)
        
        # Update context and navigate to monitoring page
        
        


    def show_equipment_preparation(self):
        """Render equipment preparation from controller.context['prep_instructions'] (fallback to local XML)."""
        lines = []
        steps = self.prep.get("equipmentPrepInstructions")
        if not steps:
            self.prepInfoText.setPlainText("无设备准备指令。")
            return
        for idx, step in enumerate(steps, start=1):
            lines.append(
                f"""
                【步骤{idx}】设备（{step.get('deviceId')}）准备
                 1）网版: {step.get('screenId')}
                 2）印料: 
                    -ID: {step.get('inkMaterialId')}
                    -重量: {step.get('inkWeightPerPiece')} kg
                    -色号: {step.get('inkColorCode')}
                """
            )
        self.prepInfoText.setPlainText("\n".join(lines))
        return
        

    def show_fabric_preparation(self):
        """Render material preparation from context (fallback to local XML)."""
        lines = []
        steps = self.prep.get("materialPrepInstructions")
        if not steps:
            self.prepInfoText.setPlainText("无物料准备指令。")
            return
        for idx, step in enumerate(steps, start=1):
            lines.append(
                f"""
                【步骤{idx}】物料（{step.get('materialName')}）准备
                 -数量: {step.get('quantity')} {step.get('unit')}
                 -目标物料: {step.get('targetMaterial')}
                 -容器: {step.get('container')}
                 -备注: {step.get('remark')}
                """
            )
        self.prepInfoText.setPlainText("\n".join(lines))
        return


    def show_ink_preparation(self):
        """Render ink/paste preparation from context (fallback to local XML)."""
        lines = []
        steps = self.prep.get("inkPastePrepInstructions")
        if not steps:
            self.prepInfoText.setPlainText("无印料准备指令。")
            return
        for idx, step in enumerate(steps, start=1):
            material_id = step.get('materialId')
            color_code = step.get('colorCode')
            weight = step.get('weight')
            lines.append(
                f"""
                【步骤{idx}】印料（{material_id}）准备：\n
                 -色号: {color_code}\n
                 -重量: {weight} kg\n
                """
            ) 
        self.prepInfoText.setPlainText("\n".join(lines))    
        return


    def show_mesh_preparation(self):
        """Render screen preparation from context (fallback to local XML)."""
        lines = []
        steps = self.prep.get("screenPrepInstructions")
        if not steps:
            self.prepInfoText.setPlainText("无网版准备指令。")
            return
        for idx, step in enumerate(steps, start=1):
            lines.append(
                f"""
                【步骤{idx}】网版（{step.get('screenId')}）准备：
                 -图稿文件: {step.get('designFile')}
                 -张力: {step.get('tension')} N
                 -网目数: {step.get('meshCount')}
                 -线径: {step.get('wireDiameter')} mm
                 -感光胶厚度: {step.get('photoEmulsionThickness')} mm
                 -网版数量: {step.get('screenCnt')}
                """
            )
        self.prepInfoText.setPlainText("\n".join(lines))
        return


    def _init_prep_buttons(self):
        """Make preparation buttons checkable and provide highlight styling; only affects left panel buttons."""
        # Only affect QPushButton inside preparationPanel (avoid touching bottom "edit/next" buttons)
        self.preparationPanel.setStyleSheet("""
            QPushButton {
                padding: 6px 12px;
                border: 1px solid #cfd8dc;
                border-radius: 6px;
                background: #fafafa;
                color: #263238;
            }
            QPushButton:hover {
                background: #eceff1;
            }
            QPushButton:checked {
                background: #1976d2;
                color: #ffffff;
                border: 2px solid #0d47a1;
            }
        """)
        for btn in (self.btnMeshPreparation, self.btnInkPreparation,
                    self.btnFabricPreparation, self.btnEquipmentPreparation):
            btn.setCheckable(True)

    def _set_active_prep_button(self, active_btn: QtWidgets.QPushButton):
        """Mutually exclusive selection: highlight the active button."""
        buttons = (self.btnMeshPreparation, self.btnInkPreparation,
                   self.btnFabricPreparation, self.btnEquipmentPreparation)
        for b in buttons:
            b.setChecked(b is active_btn)

    def on_click_mesh_prep(self):
        self._set_active_prep_button(self.btnMeshPreparation)
        self._active_prep_type = "screenPrepInstructions"
        self.show_mesh_preparation()

    def on_click_ink_prep(self):
        self._set_active_prep_button(self.btnInkPreparation)
        self._active_prep_type = "inkPastePrepInstructions"
        self.show_ink_preparation()

    def on_click_fabric_prep(self):
        self._set_active_prep_button(self.btnFabricPreparation)
        self._active_prep_type = "materialPrepInstructions"
        self.show_fabric_preparation()

    def on_click_equipment_prep(self):
        self._set_active_prep_button(self.btnEquipmentPreparation)
        self._active_prep_type = "equipmentPrepInstructions"
        self.show_equipment_preparation()