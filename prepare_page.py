from PyQt5 import QtWidgets, uic
from PyQt5.QtWidgets import QGraphicsScene, QGraphicsRectItem, QGraphicsLineItem, QGraphicsSimpleTextItem
from PyQt5.QtGui import QPen, QBrush, QColor, QPainter, QPolygonF
from PyQt5.QtCore import QRectF, QPointF, Qt
from utilities.constants import DEFAULT_ROUTINE_LISTS
import xml.etree.ElementTree as ET
from pathlib import Path
from PyQt5.QtWidgets import QGraphicsSimpleTextItem


class PreparePage(QtWidgets.QWidget):
    """Routine page."""
    
    def __init__(self, controller):
        super().__init__()
        uic.loadUi("forms/prepare_page.ui", self)
        self.controller = controller
        self.setup_ui()
        
    
    def setup_ui(self) -> None:
        # Initialize the four preparation buttons to be checkable and set highlight styles
        self._init_prep_buttons()

        # Connect click events to wrapper methods (handle highlight switch and load content)
        self.btnMeshPreparation.clicked.connect(self.on_click_mesh_prep)
        self.btnInkPreparation.clicked.connect(self.on_click_ink_prep)
        self.btnFabricPreparation.clicked.connect(self.on_click_fabric_prep)
        self.btnEquipmentPreparation.clicked.connect(self.on_click_equipment_prep)

        # Initial state: keep behavior consistent and show equipment preparation with highlight
        self.on_click_equipment_prep()


    def show_equipment_preparation(self):
        """Render equipment preparation from controller.context['prep_instructions'] (fallback to local XML)."""
        try:
            prep = self._get_prep_from_context()
            if prep:
                lines = []
                items = prep.get("equipmentPrepInstructions") or prep.get("equipment_prep_instructions") or []
                for idx, it in enumerate(items, start=1):
                    lines.append(f"【步骤 {idx}】 设备准备")
                    lines.append(f"    工位: {it.get('workstation') or it.get('workstation')}")
                    lines.append(f"    物料/设备: {it.get('material')}")
                    if it.get("colorCode") or it.get("color_code"):
                        lines.append(f"    色号: {it.get('colorCode') or it.get('color_code')}")
                    if it.get("weight"):
                        lines.append(f"    重量: {it.get('weight')}")
                    if it.get("quantity"):
                        lines.append(f"    数量: {it.get('quantity')}")
                    if it.get("unit"):
                        lines.append(f"    单位: {it.get('unit')}")
                    if it.get("remark"):
                        lines.append(f"    备注: {it.get('remark')}")
                    lines.append("")
                self.prepInfoText.setPlainText("\n".join(lines))
                return

        except Exception:
            pass

        # fallback to original XML loader
        xml_path = Path(__file__).resolve().parent / "resource" / "human_instructions" / "设备准备指令.xml"
        try:
            tree = ET.parse(str(xml_path))
            root = tree.getroot()
            ns = {'ns': 'urn:linecontrol:screen-prep'}
            steps = root.find(".//ns:Steps", ns)
            if steps is None:
                self.prepInfoText.setPlainText("未找到设备准备指令内容。")
                return
            lines = []
            for step in steps.findall("ns:Step", ns):
                sid = step.get("id", "")
                instr = step.findtext("ns:Instruction", "", ns)
                params = step.find("ns:Parameters", ns)
                lines.append(f"【步骤 {sid}】{instr}")
                if params is not None:
                    for p in params:
                        tag = p.tag.split('}', 1)[-1]
                        val = p.text
                        if tag in ("工作站", "物料", "色号", "重量", "数量", "单位"):
                            lines.append(f"    {tag}: {val}  ←")
                        else:
                            lines.append(f"    {tag}: {val}")
                lines.append("")  # Blank line separator
            text = "\n".join(lines)
            self.prepInfoText.setPlainText(text)
        except Exception as e:
            self.prepInfoText.setPlainText(f"设备准备指令加载失败：{e}")

    def show_fabric_preparation(self):
        """Render material preparation from context (fallback to local XML)."""
        try:
            prep = self._get_prep_from_context()
            if prep:
                lines = []
                items = prep.get("materialPrepInstructions") or prep.get("material_prep_instructions") or []
                for idx, it in enumerate(items, start=1):
                    lines.append(f"【步骤 {idx}】 物料准备")
                    lines.append(f"    物料: {it.get('materialName') or it.get('material_name')}")
                    lines.append(f"    数量: {it.get('quantity')}")
                    if it.get("unit"):
                        lines.append(f"    单位: {it.get('unit')}")
                    if it.get("operation"):
                        lines.append(f"    操作: {it.get('operation')}")
                    if it.get("targetMaterial") or it.get("target_material"):
                        lines.append(f"    目标物料: {it.get('targetMaterial') or it.get('target_material')}")
                    if it.get("container"):
                        lines.append(f"    容器: {it.get('container')}")
                    if it.get("remark"):
                        lines.append(f"    备注: {it.get('remark')}")
                    lines.append("")
                self.prepInfoText.setPlainText("\n".join(lines))
                return
        except Exception:
            pass
        # fallback to XML loader (existing code)
        xml_path = Path(__file__).resolve().parent / "resource" / "human_instructions" / "面料准备指令.xml"
        try:
            tree = ET.parse(str(xml_path))
            root = tree.getroot()
            ns = {'ns': 'urn:linecontrol:screen-prep'}
            steps = root.find(".//ns:Steps", ns)
            if steps is None:
                self.prepInfoText.setPlainText("未找到面料准备指令内容。")
                return
            lines = []
            for step in steps.findall("ns:Step", ns):
                sid = step.get("id", "")
                instr = step.findtext("ns:Instruction", "", ns)
                params = step.find("ns:Parameters", ns)
                lines.append(f"【步骤 {sid}】{instr}")
                if params is not None:
                    for p in params:
                        tag = p.tag.split('}', 1)[-1]
                        val = p.text
                        if tag in ("物料名称", "数量", "单位", "操作", "目标物料", "容器"):
                            lines.append(f"    {tag}: {val}  ←")
                        else:
                            lines.append(f"    {tag}: {val}")
                lines.append("")  # Blank line separator
            text = "\n".join(lines)
            self.prepInfoText.setPlainText(text)
        except Exception as e:
            self.prepInfoText.setPlainText(f"面料准备指令加载失败：{e}")

    def show_ink_preparation(self):
        """Render ink/paste preparation from context (fallback to local XML)."""
        prep = self.controller.context["prep_instructions"]
        if prep:
            lines = []
            items = prep.get("inkPastePrepInstructions")
            for idx, it in enumerate(items, start=1):
                color_code = it.get('colorCode')
                weight = it.get('weight')
                material_type = it.get('materialType')
                remark = it.get('remark')
                lines.append(
                    f"【步骤 {idx}】 {material_type}准备:\n-色号: {color_code}\n-重量: {weight}\n-备注: {remark}\n"
                ) 
            self.prepInfoText.setPlainText("\n".join(lines))
        return

        

    def show_mesh_preparation(self):
        """Render screen preparation from context (fallback to local XML)."""
        try:
            prep = self._get_prep_from_context()
            if prep:
                lines = []
                items = prep.get("screenPrepInstructions") or prep.get("screen_prep_instructions") or []
                for idx, it in enumerate(items, start=1):
                    lines.append(f"【步骤 {idx}】 网版准备")
                    lines.append(f"    网版编号: {it.get('screenId') or it.get('screen_id')}")
                    lines.append(f"    图稿文件: {it.get('designFile') or it.get('design_file')}")
                    if it.get("tension"):
                        lines.append(f"    张力: {it.get('tension')}")
                    if it.get("meshCount") or it.get("mesh_count"):
                        lines.append(f"    网目数: {it.get('meshCount') or it.get('mesh_count')}")
                    if it.get("wireDiameter") or it.get("wire_diameter"):
                        lines.append(f"    线径: {it.get('wireDiameter') or it.get('wire_diameter')}")
                    if it.get("photoEmulsionThickness") or it.get("photo_emulsion_thickness"):
                        lines.append(f"    感光胶厚度: {it.get('photoEmulsionThickness') or it.get('photo_emulsion_thickness')}")
                    lines.append("")
                # append execution instructions if present
                execs = prep.get("executionInstructions") or prep.get("execution_instructions")
                if execs and execs.get("steps"):
                    lines.append("执行步骤：")
                    for s in execs["steps"]:
                        lines.append(f"    步骤 {s.get('sequence')}: {s.get('workstation')} - {s.get('action')} ({s.get('expectedDuration')})")
                self.prepInfoText.setPlainText("\n".join(lines))
                return
        except Exception:
            pass
        # fallback to XML loader
        xml_path = Path(__file__).resolve().parent / "resource" / "human_instructions" / "网版准备指令.xml"
        try:
            tree = ET.parse(str(xml_path))
            root = tree.getroot()
            ns = {'ns': 'urn:linecontrol:screen-prep'}
            steps = root.find(".//ns:Steps", ns)
            if steps is None:
                self.prepInfoText.setPlainText("未找到网版准备指令内容。")
                return
            lines = []
            for step in steps.findall("ns:Step", ns):
                sid = step.get("id", "")
                instr = step.findtext("ns:Instruction", "", ns)
                params = step.find("ns:Parameters", ns)
                lines.append(f"【步骤 {sid}】{instr}")
                if params is not None:
                    for p in params:
                        lines.append(f"    {p.tag.split('}', 1)[-1]}: {p.text}")
                lines.append("")
            text = "\n".join(lines)
            self.prepInfoText.setPlainText(text)
        except Exception as e:
            self.prepInfoText.setPlainText(f"网版准备指令加载失败：{e}")

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

    # ---- Four wrapper click methods: switch highlight first, then load content ----
    def on_click_mesh_prep(self):
        self._set_active_prep_button(self.btnMeshPreparation)
        self.show_mesh_preparation()

    def on_click_ink_prep(self):
        self._set_active_prep_button(self.btnInkPreparation)
        self.show_ink_preparation()

    def on_click_fabric_prep(self):
        self._set_active_prep_button(self.btnFabricPreparation)
        self.show_fabric_preparation()

    def on_click_equipment_prep(self):
        self._set_active_prep_button(self.btnEquipmentPreparation)
        self.show_equipment_preparation()

    def _get_prep_from_context(self) -> dict:
        """Return normalized prepInstructions dict from controller.context if available."""
        ctx = getattr(self.controller, "context", {}) or {}
        data = ctx.get("prep_instructions") or ctx.get("route_confirm") or ctx.get("prepInstructions") or ctx.get("prep_instructions")
        if not data:
            return {}
        # if wrapper contains 'prepInstructions' alias
        if isinstance(data, dict) and ("prepInstructions" in data and isinstance(data["prepInstructions"], dict)):
            return data["prepInstructions"]
        # if top-level response dict contains 'prepInstructions'
        if isinstance(data, dict) and "prepInstructions" in data:
            return data["prepInstructions"]
        # accept already normalized dict
        return data