import base64
import json
import re
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, List, Optional

from PyQt5 import QtCore, QtWidgets, uic
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QMessageBox, QTableWidgetItem

try:
    from PyQt5.QtWebEngineWidgets import QWebEngineView
except ImportError:  # pragma: no cover
    QWebEngineView = None

from utilities.backend_client import BackendError
from utilities.prep_utils import (
    TAB_KEY_TO_FIELD,
    TAB_KEY_TO_TITLE,
    build_empty_prep_instruction_context,
    build_validation_feedback,
    identify_instruction_target,
    normalize_prep_instruction_context,
    safe_int as _safe_int,
    safe_text as _safe_text,
    status_to_text,
    summarize_risk_text,
)


MESH_PARAM_FIELDS = [
    "mesh_prep_line_id",
    "process_plan_id",
    "process_plan_version",
    "size",
    "material",
    "mesh_model",
    "diameter",
    "stretching",
    "stretching_degree",
    "mesh_count",
    "tension",
    "frame_specification",
    "quantity",
    "operator",
    "status",
]

MESH_PARAM_LABELS = {
    "mesh_prep_line_id": "网版准备行ID",
    "process_plan_id": "工艺方案ID",
    "process_plan_version": "工艺方案版本",
    "size": "尺码",
    "material": "材质",
    "mesh_model": "网版型号",
    "diameter": "丝径",
    "stretching": "拉网方式",
    "stretching_degree": "拉网角度",
    "mesh_count": "目数",
    "tension": "张力",
    "frame_specification": "网框规格",
    "quantity": "数量",
    "operator": "操作人",
    "status": "状态",
}

MATERIAL_PARAM_FIELDS = [
    "material_prep_instruction_line_id",
    "sku",
    "size",
    "quantity",
    "from_location",
    "operator",
    "status",
]

MATERIAL_PARAM_LABELS = {
    "material_prep_instruction_line_id": "物料准备行ID",
    "sku": "物料SKU",
    "size": "尺码",
    "quantity": "数量",
    "from_location": "来源库位",
    "operator": "操作人",
    "status": "状态",
}

INK_PARAM_FIELDS = [
    "ink_prep_instruction_line_id",
    "material_type",
    "material_name",
    "color_code",
    "recipe",
    "quantity",
    "operator",
    "status",
]

INK_PARAM_LABELS = {
    "ink_prep_instruction_line_id": "油墨胶浆准备行ID",
    "material_type": "材料类型",
    "material_name": "材料名称",
    "color_code": "色号",
    "recipe": "配方",
    "quantity": "数量",
    "operator": "操作人",
    "status": "状态",
}

EQUIPMENT_PARAM_FIELDS = [
    "equipment_prep_instruction_line_id",
    "node_id",
    "mesh_index",
    "material_name",
    "operator",
    "status",
]

EQUIPMENT_PARAM_LABELS = {
    "equipment_prep_instruction_line_id": "设备准备行ID",
    "node_id": "节点ID",
    "mesh_index": "网版序号",
    "material_name": "材料名称",
    "operator": "操作人",
    "status": "状态",
}

MESH_NUMERIC_FIELDS_INT = {
    "process_plan_version",
    "stretching_degree",
    "mesh_count",
    "quantity",
}

MESH_NUMERIC_FIELDS_FLOAT = {
    "diameter",
    "tension",
}

_GENERIC_OBJECT_TITLE = "对象列表"
_GENERIC_OBJECT_SEARCH_PLACEHOLDER = "搜索：丝印机 / 烘干机 / 线长…"
_MESH_OBJECT_TITLE = "网版列表"
_MESH_OBJECT_SEARCH_PLACEHOLDER = "搜索：网版ID / 工艺方案ID / 操作人…"

MATERIAL_NUMERIC_INT_FIELDS = {"quantity"}
INK_NUMERIC_FLOAT_FIELDS = {"quantity"}
EQUIPMENT_NUMERIC_INT_FIELDS = {"mesh_index"}
GENERIC_JSON_FIELDS = {"recipe"}
INK_RECIPE_COMPONENT_KEYS = (
    "配比",
    "components",
    "ingredients",
    "composition",
    "component_list",
    "ingredient_list",
)


def looks_like_svg_content(value: Any) -> bool:
    text = _safe_text(value).strip().lower()
    if not text:
        return False
    return (
        (text.startswith("<?xml") and "<svg" in text)
        or text.startswith("<svg")
        or ("<svg" in text and "</svg>" in text)
    )


def normalize_svg_markup(svg_text: Any) -> str:
    text = _safe_text(svg_text).strip()
    if not text:
        return ""
    text = strip_svg_prolog(text)
    match = re.search(r"(<svg\b.*?</svg>)", text, flags=re.IGNORECASE | re.DOTALL)
    return match.group(1).strip() if match else ""


def strip_svg_prolog(svg_text: str) -> str:
    text = svg_text.strip()
    if not text:
        return ""
    text = re.sub(r"^\s*<\?xml[^>]*\?>\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^\s*<!--.*?-->\s*", "", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"^\s*<!DOCTYPE[^>]*>\s*", "", text, flags=re.IGNORECASE)
    return text.strip()


def normalize_svg_references(svg_text: str) -> str:
    tag_pattern = re.compile(
        r"<(?P<tag>[A-Za-z_][\w:.-]*)(?P<attrs>[^<>]*?(?:xlink:href|(?<!xlink:)href)[^<>]*?)(?P<close>\s*/?)>",
        flags=re.IGNORECASE,
    )

    def _normalize_tag(match: re.Match[str]) -> str:
        tag = match.group("tag")
        attrs = match.group("attrs") or ""
        close = match.group("close") or ""
        xlink_match = re.search(
            r'xlink:href\s*=\s*(?P<quote>["\'])(?P<value>[^"\']+)(?P=quote)',
            attrs,
            flags=re.IGNORECASE,
        )
        href_match = re.search(
            r'(?<![\w:-])href\s*=\s*(?P<quote>["\'])(?P<value>[^"\']+)(?P=quote)',
            attrs,
            flags=re.IGNORECASE,
        )
        if xlink_match and href_match:
            return match.group(0)
        if xlink_match and xlink_match.group("value").startswith("#"):
            quote = xlink_match.group("quote")
            value = xlink_match.group("value")
            attrs = f"{attrs} href={quote}{value}{quote}"
        elif href_match and href_match.group("value").startswith("#"):
            quote = href_match.group("quote")
            value = href_match.group("value")
            attrs = f"{attrs} xlink:href={quote}{value}{quote}"
        return f"<{tag}{attrs}{close}>"

    return tag_pattern.sub(_normalize_tag, svg_text)


def prefix_svg_ids(svg_text: str, unique_prefix: str) -> str:
    id_pattern = re.compile(r'\bid=(["\'])([^"\']+)\1', flags=re.IGNORECASE)
    id_map: Dict[str, str] = {}

    def _replace_id(match: re.Match[str]) -> str:
        original_id = match.group(2)
        prefixed_id = id_map.setdefault(original_id, f"{unique_prefix}{original_id}")
        return f'id="{prefixed_id}"'

    text = id_pattern.sub(_replace_id, svg_text)
    if not id_map:
        return text

    for original_id, prefixed_id in sorted(id_map.items(), key=lambda item: len(item[0]), reverse=True):
        escaped_id = re.escape(original_id)
        text = re.sub(rf'url\(\s*#{escaped_id}\s*\)', f"url(#{prefixed_id})", text)
        text = re.sub(
            rf'((?:xlink:href|href)\s*=\s*["\'])#{escaped_id}(["\'])',
            rf"\1#{prefixed_id}\2",
            text,
            flags=re.IGNORECASE,
        )
    return text


def preprocess_svg(svg_text: str, unique_prefix: str) -> str:
    normalized_svg = normalize_svg_markup(svg_text)
    if not normalized_svg:
        return ""
    normalized_svg = normalize_svg_references(normalized_svg)
    return prefix_svg_ids(normalized_svg, unique_prefix)


def validate_svg_xml(svg_text: str) -> str | None:
    try:
        ET.fromstring(svg_text)
    except ET.ParseError as exc:
        return str(exc)
    return None


def svg_to_data_url(svg_text: str) -> str:
    encoded_svg = base64.b64encode(svg_text.encode("utf-8")).decode("ascii")
    return f"data:image/svg+xml;base64,{encoded_svg}"


def build_mesh_preview_html(image_src: str) -> str:
    return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8" />
  <style>
    html, body {{
      margin: 0;
      padding: 0;
      width: 100%;
      height: 100%;
      background: #fafafa;
      overflow: auto;
    }}
    body {{
      display: flex;
      align-items: center;
      justify-content: center;
      overflow: hidden;
    }}
    .image-host {{
      width: 100%;
      height: 100%;
      display: flex;
      align-items: center;
      justify-content: center;
      overflow: auto;
    }}
    .image-host img {{
      max-width: 100%;
      max-height: 100%;
      width: auto;
      height: auto;
      object-fit: contain;
    }}
  </style>
</head>
<body>
  <div class="image-host"><img src="{image_src}" alt="网版图案设计" /></div>
</body>
</html>"""


def build_preview_message_html(message: str) -> str:
    return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8" />
  <style>
    html, body {{
      margin: 0;
      padding: 0;
      width: 100%;
      height: 100%;
      background: #fafafa;
      color: #666666;
      font-family: sans-serif;
    }}
    body {{
      display: flex;
      align-items: center;
      justify-content: center;
      text-align: center;
      padding: 24px;
      box-sizing: border-box;
    }}
  </style>
</head>
<body>{message}</body>
</html>"""


def coerce_mesh_field_value(field_name: str, raw_text: str) -> Any:
    text = raw_text.strip()
    if text == "":
        return ""
    if field_name in MESH_NUMERIC_FIELDS_INT:
        try:
            return int(text)
        except ValueError:
            return text
    if field_name in MESH_NUMERIC_FIELDS_FLOAT:
        try:
            return float(text)
        except ValueError:
            return text
    return text


def build_non_mesh_list_item_text(tab_key: str, line: Dict[str, Any], fallback_index: int) -> str:
    priority_by_tab = {
        "material_prep": ("material_prep_instruction_line_id", "sku"),
        "ink_prep": ("ink_prep_instruction_line_id", "material_name"),
        "equipment_prep": ("node_id", "equipment_prep_instruction_line_id"),
    }
    for key in priority_by_tab.get(tab_key, ()):
        value = _safe_text(line.get(key))
        if value:
            return value
    fallback = identify_instruction_target(line, fallback_index)
    return fallback or f"第{fallback_index + 1}项"


def build_mesh_list_item_text(line: Dict[str, Any], fallback_index: int) -> str:
    for key in ("mesh_prep_line_id", "process_plan_id"):
        value = _safe_text(line.get(key))
        if value:
            return value
    fallback = identify_instruction_target(line, fallback_index)
    return fallback or f"第{fallback_index + 1}项"


class PrepInstructionLibraryDialog(QtWidgets.QDialog):
    """Lightweight library dialog for historical prep instructions."""

    def __init__(self, records: List[Dict[str, Any]], parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("生产准备版本库")
        self.resize(760, 420)
        self.selected_record: Optional[Dict[str, Any]] = None

        layout = QtWidgets.QVBoxLayout(self)
        self.table = QtWidgets.QTableWidget(self)
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["指令ID", "版本", "lot_id", "process_route_id", "状态"])
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table)

        self.empty_label = QtWidgets.QLabel("暂无历史版本", self)
        self.empty_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.empty_label)

        button_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel,
            parent=self,
        )
        button_box.accepted.connect(self._accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        self.table.itemDoubleClicked.connect(lambda _item: self._accept())
        self._populate(records)

    def _populate(self, records: List[Dict[str, Any]]) -> None:
        self.table.setRowCount(len(records))
        self.empty_label.setVisible(not records)
        self.table.setVisible(bool(records))
        for row_index, record in enumerate(records):
            values = [
                _safe_text(record.get("prep_instruction_id")),
                str(_safe_int(record.get("prep_instruction_version"), 0)),
                _safe_text(record.get("lot_id")),
                _safe_text(record.get("process_route_id")),
                _safe_text(record.get("status")),
            ]
            for column_index, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.UserRole, record)
                self.table.setItem(row_index, column_index, item)
        if records:
            self.table.selectRow(0)

    def _accept(self) -> None:
        current_row = self.table.currentRow()
        if current_row < 0:
            QMessageBox.information(self, "版本库", "请先选择一个历史版本。")
            return
        item = self.table.item(current_row, 0)
        if item is None:
            QMessageBox.information(self, "版本库", "当前选择无效，请重新选择。")
            return
        record = item.data(Qt.UserRole)
        if not isinstance(record, dict):
            QMessageBox.information(self, "版本库", "当前选择无效，请重新选择。")
            return
        self.selected_record = record
        self.accept()


class PreparePage(QtWidgets.QWidget):
    """Production preparation page for the minimum closed loop."""

    _TAB_ACTIVE_STYLE = """
        QPushButton {
            background-color: #1677ff;
            border: 1px solid #1677ff;
            border-radius: 8px;
            min-height: 24px;
            max-height: 24px;
            padding: 0 14px;
            font-size: 12px;
            color: #ffffff;
            font-weight: 600;
        }
    """
    _TAB_INACTIVE_STYLE = """
        QPushButton {
            background-color: #f5f6f8;
            border: 1px solid #f0f0f0;
            border-radius: 8px;
            min-height: 24px;
            max-height: 24px;
            padding: 0 14px;
            font-size: 12px;
            color: #666666;
            font-weight: 400;
        }
        QPushButton:hover {
            background-color: #ffffff;
            border-color: #d9d9d9;
            color: #1677ff;
        }
    """

    def __init__(self, controller: Any) -> None:
        super().__init__()
        uic.loadUi(str(Path(__file__).resolve().parent / "forms" / "prep_page.ui"), self)
        self.controller = controller
        self._updating_widgets = False
        self._updating_mesh_param_table = False
        self._updating_generic_param_table = False
        self._last_selected_row: Optional[int] = None
        self._mesh_preview_widget: QtWidgets.QWidget | None = None
        self.page_state = self._build_initial_page_state()
        self._init_mesh_widgets()
        self._bind_events()
        self._restore_or_create_context()
        self._render_page()

    def refresh_data(self) -> None:
        self._load_target_instruction_if_needed()
        self._restore_or_create_context()
        self._render_page()

    def _build_initial_page_state(self) -> Dict[str, Any]:
        return {
            "page_status": "created",
            "loading": False,
            "dirty": False,
            "active_tab": "mesh_prep",
            "active_target_id": "",
            "selected_object_row": None,
            "library_dialog": {"open": False},
            "selected_instruction_id": "",
            "selected_instruction_version": 0,
            "current_instruction_set": {},
            "validation_summary": {"passed": False, "errors": [], "risks": []},
        }

    def _bind_events(self) -> None:
        self.btnVersionLib.clicked.connect(self._open_version_library)
        self.btnLocalImport.clicked.connect(self._show_local_import_placeholder)
        self.btnAIOptimize.clicked.connect(self._show_ai_optimize_placeholder)
        self.btnValidate.clicked.connect(self._validate_instruction_set)
        self.btnDispatch.clicked.connect(self._distribute_instruction_set)

        self.tabStencil.clicked.connect(lambda: self._switch_tab("mesh_prep"))
        self.tabMaterial.clicked.connect(lambda: self._switch_tab("material_prep"))
        self.tabInk.clicked.connect(lambda: self._switch_tab("ink_prep"))
        self.tabEquipment.clicked.connect(lambda: self._switch_tab("equipment_prep"))

        self.listObjects.currentRowChanged.connect(self._on_object_changed)
        self.listObjects.itemClicked.connect(lambda _item: self._force_render_current_object())
        self.txtSearchObject.textChanged.connect(self._filter_object_list)
        self.tableMeshParams.itemChanged.connect(self._on_mesh_param_item_changed)
        self.tableGenericParams.itemChanged.connect(self._on_generic_param_item_changed)
        self.lblViewRisk.setCursor(Qt.PointingHandCursor)
        self.lblViewRisk.mousePressEvent = self._show_risks  # type: ignore[assignment]

    def _init_mesh_widgets(self) -> None:
        preview_layout = self.meshPreviewHost.layout()
        if QWebEngineView is not None:
            self._mesh_preview_widget = QWebEngineView(self.meshPreviewHost)
        else:
            browser = QtWidgets.QTextBrowser(self.meshPreviewHost)
            browser.setOpenExternalLinks(False)
            browser.setReadOnly(True)
            self._mesh_preview_widget = browser
        preview_layout.addWidget(self._mesh_preview_widget)

        self.tableMeshParams.setColumnCount(2)
        self.tableMeshParams.setHorizontalHeaderLabels(["参数名称", "参数值"])
        self.tableMeshParams.verticalHeader().setVisible(False)
        self.tableMeshParams.horizontalHeader().setStretchLastSection(True)
        self.tableMeshParams.horizontalHeader().setSectionResizeMode(
            0, QtWidgets.QHeaderView.ResizeToContents
        )
        self.tableMeshParams.horizontalHeader().setSectionResizeMode(
            1, QtWidgets.QHeaderView.Stretch
        )
        self.tableMeshParams.setAlternatingRowColors(True)
        self.tableMeshParams.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectItems)
        self.tableGenericParams.setColumnCount(2)
        self.tableGenericParams.setHorizontalHeaderLabels(["参数名称", "参数值"])
        self.tableGenericParams.verticalHeader().setVisible(False)
        self.tableGenericParams.horizontalHeader().setStretchLastSection(True)
        self.tableGenericParams.horizontalHeader().setSectionResizeMode(
            0, QtWidgets.QHeaderView.ResizeToContents
        )
        self.tableGenericParams.horizontalHeader().setSectionResizeMode(
            1, QtWidgets.QHeaderView.Stretch
        )
        self.tableGenericParams.setAlternatingRowColors(True)
        self.tableGenericParams.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectItems)

    def _restore_or_create_context(self) -> None:
        context = self.controller.context.get("prep_instruction_context")
        if not isinstance(context, dict):
            context = build_empty_prep_instruction_context(self.controller.context)
            self.controller.context["prep_instruction_context"] = context
        normalized = normalize_prep_instruction_context(context)
        header = normalized["prep_instruction_header"]
        self.page_state["current_instruction_set"] = normalized
        self.page_state["page_status"] = _safe_text(header.get("status")).lower() or "created"
        self.page_state["selected_instruction_id"] = _safe_text(header.get("prep_instruction_id"))
        self.page_state["selected_instruction_version"] = _safe_int(header.get("prep_instruction_version"), 0)
        self.page_state["active_target_id"] = ""
        self.page_state["selected_object_row"] = None
        self.page_state["validation_summary"] = self.page_state.get("validation_summary") or {
            "passed": False,
            "errors": [],
            "risks": [],
        }

    def _load_target_instruction_if_needed(self) -> None:
        context = getattr(self.controller, "context", None)
        if not isinstance(context, dict):
            return
        target = context.get("prepare_page_target_instruction")
        if not isinstance(target, dict):
            return

        prep_instruction_id = _safe_text(target.get("prep_instruction_id"))
        prep_instruction_version = _safe_int(target.get("prep_instruction_version"), 0)
        context.pop("prepare_page_target_instruction", None)
        production_context = getattr(self.controller, "production_context", None)
        if isinstance(production_context, dict):
            production_context.pop("prepare_page_target_instruction", None)
        if not prep_instruction_id or prep_instruction_version <= 0:
            return

        try:
            detail = self.controller.backend.prep_instructions.detail(
                prep_instruction_id,
                prep_instruction_version,
            )
        except BackendError as exc:
            QMessageBox.warning(
                self,
                "加载生产准备指令",
                f"加载生产准备指令 {prep_instruction_id} v{prep_instruction_version} 失败：{exc}",
            )
            return

        self._apply_loaded_instruction_detail(detail)

    def _apply_loaded_instruction_detail(self, detail: Dict[str, Any]) -> None:
        normalized = normalize_prep_instruction_context(detail)
        header = normalized["prep_instruction_header"]
        self.page_state["current_instruction_set"] = normalized
        self.page_state["selected_instruction_id"] = _safe_text(header.get("prep_instruction_id"))
        self.page_state["selected_instruction_version"] = _safe_int(header.get("prep_instruction_version"), 0)
        self.page_state["page_status"] = _safe_text(header.get("status")).lower() or "created"
        self.page_state["dirty"] = False
        self.page_state["active_target_id"] = ""
        self.page_state["selected_object_row"] = None
        self.page_state["validation_summary"] = {"passed": False, "errors": [], "risks": []}
        self.controller.context["prep_instruction_context"] = normalized

    def _current_field_name(self) -> str:
        return TAB_KEY_TO_FIELD[self.page_state["active_tab"]]

    def _current_lines(self) -> List[Dict[str, Any]]:
        current = self.page_state["current_instruction_set"]
        lines = current.get(self._current_field_name())
        return lines if isinstance(lines, list) else []

    def _sync_context(self) -> None:
        current = normalize_prep_instruction_context(self.page_state["current_instruction_set"])
        current["prep_instruction_header"]["status"] = self.page_state["page_status"]
        self.page_state["current_instruction_set"] = current
        self.controller.context["prep_instruction_context"] = current

    def _selected_line_index(self) -> int:
        lines = self._current_lines()
        row = self._selected_object_row()
        if 0 <= row < len(lines):
            return row
        if self._is_mesh_tab() and lines:
            return 0
        return -1

    def _save_current_editor(self) -> bool:
        if self._is_mesh_tab() or self._is_table_tab() or not hasattr(self, "txtInstructionContent"):
            return True
        index = self._selected_line_index()
        if index < 0:
            return True
        lines = self._current_lines()
        if index >= len(lines):
            return True
        return True

    def _switch_tab(self, tab_key: str) -> None:
        if self.page_state["active_tab"] == tab_key:
            return
        if not self._save_current_editor():
            return
        self.page_state["active_tab"] = tab_key
        self.page_state["active_target_id"] = ""
        self._render_page()

    def _filter_object_list(self) -> None:
        self._render_object_panel_meta()
        keyword = self.txtSearchObject.text().strip().lower()
        for row_index in range(self.listObjects.count()):
            item = self.listObjects.item(row_index)
            hidden = bool(keyword) and keyword not in item.text().lower()
            item.setHidden(hidden)
        self._ensure_valid_selection()

    def _ensure_valid_selection(self) -> None:
        visible_row = -1
        for row_index in range(self.listObjects.count()):
            item = self.listObjects.item(row_index)
            if item is not None and not item.isHidden():
                visible_row = row_index
                break
        if visible_row >= 0 and self.listObjects.currentRow() < 0:
            self._set_selected_object_row(visible_row)
            self.listObjects.setCurrentRow(visible_row)

    def _on_object_changed(self, row: int) -> None:
        if self._updating_widgets:
            return
        if self._last_selected_row is not None and not self._save_current_editor():
            self._updating_widgets = True
            self.listObjects.setCurrentRow(self._last_selected_row)
            self._updating_widgets = False
            return
        self._set_selected_object_row(row)
        self._last_selected_row = row if row >= 0 else None
        self._render_instruction_editor()

    def _show_local_import_placeholder(self) -> None:
        QMessageBox.information(
            self,
            "本地导入",
            "本地导入尚未接入当前生产准备最小闭环，请优先使用版本库导入历史版本。",
        )

    def _show_ai_optimize_placeholder(self) -> None:
        QMessageBox.information(self, "AI优化", "AI优化尚未接入当前生产准备最小闭环。")

    def _open_version_library(self) -> None:
        if not self._save_current_editor():
            return
        try:
            records = self.controller.backend.prep_instructions.list()
        except BackendError as exc:
            QMessageBox.warning(self, "版本库", f"获取历史版本失败：{exc}")
            return
        dialog = PrepInstructionLibraryDialog(records, parent=self)
        self.page_state["library_dialog"]["open"] = True
        try:
            if dialog.exec_() != QtWidgets.QDialog.Accepted or not dialog.selected_record:
                return
            record = dialog.selected_record
            prep_instruction_id = _safe_text(record.get("prep_instruction_id"))
            prep_instruction_version = _safe_int(record.get("prep_instruction_version"), 0)
            try:
                detail = self.controller.backend.prep_instructions.detail(
                    prep_instruction_id,
                    prep_instruction_version,
                )
            except BackendError as exc:
                QMessageBox.warning(self, "版本库", f"加载历史版本失败：{exc}")
                return
            self.page_state["current_instruction_set"] = normalize_prep_instruction_context(detail)
            self.page_state["selected_instruction_id"] = prep_instruction_id
            self.page_state["selected_instruction_version"] = prep_instruction_version
            self.page_state["page_status"] = (
                _safe_text(detail.get("prep_instruction_header", {}).get("status")).lower() or "created"
            )
            self.page_state["dirty"] = False
            self.page_state["validation_summary"] = {"passed": False, "errors": [], "risks": []}
            self._sync_context()
            self._render_page()
        finally:
            self.page_state["library_dialog"]["open"] = False

    def _collect_payload(self) -> Dict[str, Any]:
        current = normalize_prep_instruction_context(self.page_state["current_instruction_set"])
        current["prep_instruction_header"]["status"] = self.page_state["page_status"]
        return current

    def _update_validation_summary(self, result: Dict[str, Any]) -> None:
        self.page_state["validation_summary"] = {
            "passed": bool(result.get("passed")),
            "errors": result.get("errors") if isinstance(result.get("errors"), list) else [],
            "risks": result.get("risks") if isinstance(result.get("risks"), list) else [],
        }

    def _validate_instruction_set(self) -> None:
        if not self._save_current_editor():
            return
        try:
            result = self.controller.backend.prep_instructions.validate(self._collect_payload())
        except BackendError as exc:
            message = f"生产准备校验失败：{exc}"
            self.lblValidationFeedback.setText(message)
            QMessageBox.warning(self, "AI校验", message)
            return
        self._update_validation_summary(result)
        self.page_state["page_status"] = "validated" if result.get("passed") else "created"
        self.page_state["dirty"] = False
        self.page_state["current_instruction_set"]["prep_instruction_header"]["status"] = self.page_state["page_status"]
        self._sync_context()
        self._render_page()
        message = "生产准备校验通过。该操作仅执行校验，不会写入数据库。" if result.get("passed") else "生产准备校验未通过，请查看反馈。"
        QMessageBox.information(self, "AI校验", message)

    def _distribute_instruction_set(self) -> None:
        if not self._save_current_editor():
            return
        if self.page_state["page_status"] != "validated":
            QMessageBox.warning(self, "下发指令", "请先完成校验并确保通过。")
            return
        if not hasattr(self.controller, "show_page"):
            QMessageBox.critical(self, "下发指令", "主窗口未提供页面切换能力。")
            return
        self.controller.show_page("monitor_page")
        try:
            result = self.controller.backend.prep_instructions.distribute(self._collect_payload())
        except BackendError as exc:
            message = f"生产准备下发失败：{exc}"
            self.lblValidationFeedback.setText(message)
            QMessageBox.warning(self, "下发指令", message)
            return
        self._update_validation_summary(result)
        if not result.get("passed"):
            self.page_state["page_status"] = "created"
            self._render_page()
            QMessageBox.warning(self, "下发指令", "生产准备下发失败，请检查校验反馈。")
            return

        prep_instruction_id = _safe_text(result.get("prep_instruction_id"))
        prep_instruction_version = _safe_int(result.get("prep_instruction_version"), 0)
        if not prep_instruction_id or prep_instruction_version <= 0:
            QMessageBox.warning(
                self,
                "下发指令",
                "下发接口返回成功，但缺少有效的准备指令ID或版本号，无法确认是否已落库。",
            )
            return

        try:
            persisted = self.controller.backend.prep_instructions.detail(
                prep_instruction_id,
                prep_instruction_version,
            )
        except BackendError as exc:
            QMessageBox.warning(
                self,
                "下发指令",
                f"下发接口已返回成功，但回查生产准备详情失败，无法确认是否已落库：{exc}",
            )
            return

        self.page_state["current_instruction_set"] = normalize_prep_instruction_context(persisted)
        self.page_state["current_instruction_set"]["prep_instruction_header"]["prep_instruction_id"] = prep_instruction_id
        self.page_state["current_instruction_set"]["prep_instruction_header"]["prep_instruction_version"] = prep_instruction_version
        self.page_state["page_status"] = _safe_text(result.get("status")).lower() or "released"
        self.page_state["current_instruction_set"]["prep_instruction_header"]["status"] = self.page_state["page_status"]
        self.page_state["selected_instruction_id"] = prep_instruction_id
        self.page_state["selected_instruction_version"] = prep_instruction_version
        self.page_state["dirty"] = False
        self._sync_context()
        self._render_page()
        QMessageBox.information(
            self,
            "下发指令",
            f"生产准备指令已下发并完成落库校验：{prep_instruction_id} V{prep_instruction_version}。",
        )

    def _show_risks(self, _event: Optional[QtCore.QEvent]) -> None:
        risks = self.page_state.get("validation_summary", {}).get("risks")
        if not isinstance(risks, list) or not risks:
            QMessageBox.information(self, "风险详情", "当前无风险信息。")
            return
        QMessageBox.information(self, "风险详情", "\n".join(f"- {item}" for item in risks))

    def _render_page(self) -> None:
        self._updating_widgets = True
        try:
            self._render_tab_states()
            self._render_header()
            self._render_object_list()
            self._render_instruction_editor()
            self._render_validation_panel()
            self.btnDispatch.setEnabled(self.page_state["page_status"] == "validated")
        finally:
            self._updating_widgets = False

    def _render_tab_states(self) -> None:
        active_tab = self.page_state["active_tab"]
        buttons = {
            "mesh_prep": self.tabStencil,
            "material_prep": self.tabMaterial,
            "ink_prep": self.tabInk,
            "equipment_prep": self.tabEquipment,
        }
        for tab_key, button in buttons.items():
            is_active = tab_key == active_tab
            button.setCheckable(True)
            button.setChecked(is_active)
            self._apply_tab_style(button, is_active)

    def _apply_tab_style(self, button: QtWidgets.QPushButton, is_active: bool) -> None:
        button.setProperty("active", is_active)
        button.setStyleSheet(self._TAB_ACTIVE_STYLE if is_active else self._TAB_INACTIVE_STYLE)

    def _render_header(self) -> None:
        header = self.page_state["current_instruction_set"]["prep_instruction_header"]
        prep_instruction_id = _safe_text(header.get("prep_instruction_id")) or "未落库"
        version = _safe_int(header.get("prep_instruction_version"), 0)
        status = self.page_state["page_status"]
        self.lblVersion.setText(f"当前版本：{prep_instruction_id} v{version}（{status_to_text(status)}）")
        self.lblRisk.setText(summarize_risk_text(self.page_state["validation_summary"]))
        self.lblMetaStrip.setText(self._build_meta_strip())

    def _render_object_panel_meta(self) -> None:
        if self._is_mesh_tab():
            self.lblObjectTitle.setText(_MESH_OBJECT_TITLE)
            self.txtSearchObject.setPlaceholderText(_MESH_OBJECT_SEARCH_PLACEHOLDER)
            self.lblInstructionTitle.setText("网版准备指令内容")
            return
        self.lblObjectTitle.setText(_GENERIC_OBJECT_TITLE)
        self.txtSearchObject.setPlaceholderText(_GENERIC_OBJECT_SEARCH_PLACEHOLDER)
        self.lblInstructionTitle.setText("指令内容栏")

    def _build_meta_strip(self) -> str:
        header = self.page_state["current_instruction_set"]["prep_instruction_header"]
        return (
            f"lot_id: {_safe_text(header.get('lot_id')) or '-'}    "
            f"process_route_id: {_safe_text(header.get('process_route_id')) or '-'}    "
            f"process_route_version: {_safe_int(header.get('process_route_version'), 0)}    "
            f"当前页签: {TAB_KEY_TO_TITLE[self.page_state['active_tab']]}"
        )

    def _render_object_list(self) -> None:
        lines = self._current_lines()
        current_target_id = self.page_state["active_target_id"]
        self._render_object_panel_meta()
        self.listObjects.clear()
        for index, line in enumerate(lines):
            target_id = self._build_active_target_id(line, index)
            item = QtWidgets.QListWidgetItem(target_id)
            item.setData(Qt.UserRole, index)
            self.listObjects.addItem(item)

        selected_row = -1
        if lines:
            for row_index in range(self.listObjects.count()):
                item = self.listObjects.item(row_index)
                if item.text() == current_target_id:
                    selected_row = row_index
                    break
            if selected_row < 0:
                selected_row = 0
                self.page_state["active_target_id"] = self._build_active_target_id(lines[0], 0)
        else:
            self.page_state["active_target_id"] = ""
        self._set_selected_object_row(selected_row)
        if selected_row >= 0:
            self.listObjects.setCurrentRow(selected_row)
        else:
            self._last_selected_row = None
        self._filter_object_list()

    def _render_instruction_editor(self) -> None:
        if self._is_mesh_tab():
            self.instructionStack.setCurrentWidget(self.pageMeshInstruction)
            self._render_mesh_editor()
            return
        self.instructionStack.setCurrentWidget(self.pageGenericInstruction)
        self._render_generic_table_editor()

    def _render_validation_panel(self) -> None:
        self.lblValidationFeedback.setText(build_validation_feedback(self.page_state["validation_summary"]))

    def _is_mesh_tab(self) -> bool:
        return self.page_state["active_tab"] == "mesh_prep"

    def _is_table_tab(self) -> bool:
        return self.page_state["active_tab"] in {"material_prep", "ink_prep", "equipment_prep"}

    def _build_active_target_id(self, line: Dict[str, Any], index: int) -> str:
        if self._is_mesh_tab():
            return build_mesh_list_item_text(line, index)
        if self._is_table_tab():
            return build_non_mesh_list_item_text(self.page_state["active_tab"], line, index)
        return identify_instruction_target(line, index)

    def _render_mesh_editor(self) -> None:
        lines = self._current_lines()
        index = self._selected_line_index()
        if lines and (index < 0 or index >= len(lines)):
            index = 0
            self._set_selected_object_row(0)
            self._last_selected_row = 0
            if self.listObjects.count() > 0 and self.listObjects.currentRow() != 0:
                self._updating_widgets = True
                try:
                    self.listObjects.setCurrentRow(0)
                finally:
                    self._updating_widgets = False

        if index < 0 or index >= len(lines):
            title = "网版：暂无对象，可先从版本库导入或直接提交空草稿。"
            if not lines:
                self._clear_mesh_preview("当前没有网版准备指令数据。")
            else:
                self._clear_mesh_preview("当前没有可展示的网版图案。")
            self.lblInstructionTarget.setText(title)
            self._render_mesh_param_table({})
            return

        current_line = lines[index]
        target_id = self._build_active_target_id(current_line, index)
        self.page_state["active_target_id"] = target_id
        self.lblInstructionTarget.setText(f"网版：{target_id}")
        self._render_mesh_preview(current_line)
        self._render_mesh_param_table(current_line)

    def _render_mesh_preview(self, line: Dict[str, Any]) -> None:
        svg_text = _safe_text(line.get("pattern_design")).strip()
        base_url = QtCore.QUrl.fromLocalFile(str(Path(__file__).resolve().parent) + "/")
        if not svg_text:
            self._clear_mesh_preview("当前网版未提供 SVG 图案内容。")
            return
        if QWebEngineView is None:
            self._clear_mesh_preview("当前环境未安装 PyQtWebEngine，无法渲染 SVG 预览。")
            return
        if not looks_like_svg_content(svg_text):
            self._clear_mesh_preview("pattern_design 不是合法 SVG 文本，无法预览。")
            return

        svg_prefix = f"prep_svg_{int(time.time() * 1000)}_{self._selected_line_index()}_"
        processed_svg = preprocess_svg(svg_text, svg_prefix)
        if not processed_svg:
            self._clear_mesh_preview("SVG 结构无效，缺少可渲染的 <svg> 根节点。")
            return
        xml_error = validate_svg_xml(processed_svg)
        if xml_error:
            self._clear_mesh_preview(f"SVG 结构无效，预处理后 XML 不合法。<br/>{xml_error}")
            return
        assert self._mesh_preview_widget is not None
        casted = self._mesh_preview_widget
        if isinstance(casted, QWebEngineView):
            image_src = svg_to_data_url(processed_svg)
            casted.setHtml(build_mesh_preview_html(image_src), base_url)
            return
        self._clear_mesh_preview("当前环境未安装 PyQtWebEngine，无法渲染 SVG 预览。")

    def _clear_mesh_preview(self, message: str) -> None:
        if self._mesh_preview_widget is None:
            return
        if QWebEngineView is not None and isinstance(self._mesh_preview_widget, QWebEngineView):
            self._mesh_preview_widget.setHtml(build_preview_message_html(message))
            return
        if isinstance(self._mesh_preview_widget, QtWidgets.QTextBrowser):
            self._mesh_preview_widget.setHtml(build_preview_message_html(message))

    def _render_mesh_param_table(self, line: Dict[str, Any]) -> None:
        self._updating_mesh_param_table = True
        try:
            self.tableMeshParams.setRowCount(len(MESH_PARAM_FIELDS))
            for row_index, field_name in enumerate(MESH_PARAM_FIELDS):
                label_item = QTableWidgetItem(MESH_PARAM_LABELS[field_name])
                label_item.setFlags(label_item.flags() & ~Qt.ItemIsEditable)
                label_item.setData(Qt.UserRole, field_name)
                value = "" if not isinstance(line, dict) else line.get(field_name, "")
                value_item = QTableWidgetItem("" if value is None else str(value))
                value_item.setData(Qt.UserRole, field_name)
                self.tableMeshParams.setItem(row_index, 0, label_item)
                self.tableMeshParams.setItem(row_index, 1, value_item)
        finally:
            self._updating_mesh_param_table = False

    def _generic_fields_for_active_tab(self) -> List[str]:
        mapping = {
            "material_prep": MATERIAL_PARAM_FIELDS,
            "ink_prep": INK_PARAM_FIELDS,
            "equipment_prep": EQUIPMENT_PARAM_FIELDS,
        }
        return list(mapping.get(self.page_state["active_tab"], []))

    def _generic_labels_for_active_tab(self) -> Dict[str, str]:
        mapping = {
            "material_prep": MATERIAL_PARAM_LABELS,
            "ink_prep": INK_PARAM_LABELS,
            "equipment_prep": EQUIPMENT_PARAM_LABELS,
        }
        return dict(mapping.get(self.page_state["active_tab"], {}))

    def _render_generic_table_editor(self) -> None:
        lines = self._current_lines()
        index = self._selected_line_index()
        if index < 0 or index >= len(lines):
            title = f"对象：暂无{TAB_KEY_TO_TITLE[self.page_state['active_tab']]}"
            if not lines:
                title = "对象：暂无对象，可先从版本库导入或直接提交空草稿。"
            self.lblInstructionTarget.setText(title)
            self._render_generic_param_table({})
            return
        current_line = lines[index]
        target_id = self._build_active_target_id(current_line, index)
        self.page_state["active_target_id"] = target_id
        self.lblInstructionTarget.setText(f"对象：{target_id}")
        self._render_generic_param_table(current_line)

    def _render_generic_param_table(self, line: Dict[str, Any]) -> None:
        fields = self._generic_fields_for_active_tab()
        labels = self._generic_labels_for_active_tab()
        self._updating_generic_param_table = True
        try:
            self.tableGenericParams.setRowCount(len(fields))
            for row_index, field_name in enumerate(fields):
                label_item = QTableWidgetItem(labels[field_name])
                label_item.setFlags(label_item.flags() & ~Qt.ItemIsEditable)
                label_item.setData(Qt.UserRole, field_name)
                value = "" if not isinstance(line, dict) else line.get(field_name, "")
                if field_name == "recipe" and self.page_state["active_tab"] == "ink_prep":
                    value_text = self._format_ink_recipe_for_display(value)
                elif field_name in GENERIC_JSON_FIELDS and value not in ("", None):
                    value_text = json.dumps(value, ensure_ascii=False, sort_keys=True)
                else:
                    value_text = "" if value is None else str(value)
                value_item = QTableWidgetItem(value_text)
                value_item.setData(Qt.UserRole, field_name)
                self.tableGenericParams.setItem(row_index, 0, label_item)
                self.tableGenericParams.setItem(row_index, 1, value_item)
        finally:
            self._updating_generic_param_table = False

    def _coerce_generic_field_value(self, field_name: str, raw_text: str) -> Any:
        text = raw_text.strip()
        if text == "":
            return ""
        if field_name == "recipe" and self.page_state["active_tab"] == "ink_prep":
            lines = self._current_lines()
            index = self._selected_line_index()
            previous_value: Any = ""
            if 0 <= index < len(lines):
                previous_value = lines[index].get(field_name, "")
            return self._merge_ink_recipe_ratio_edit(previous_value, text)
        if field_name in GENERIC_JSON_FIELDS:
            return json.loads(text)
        if self.page_state["active_tab"] == "material_prep" and field_name in MATERIAL_NUMERIC_INT_FIELDS:
            return int(text)
        if self.page_state["active_tab"] == "ink_prep" and field_name in INK_NUMERIC_FLOAT_FIELDS:
            return float(text)
        if self.page_state["active_tab"] == "equipment_prep" and field_name in EQUIPMENT_NUMERIC_INT_FIELDS:
            return int(text)
        return text

    def _on_generic_param_item_changed(self, item: QTableWidgetItem) -> None:
        if self._updating_generic_param_table or self._updating_widgets or not self._is_table_tab():
            return
        if item.column() != 1:
            return
        field_name = item.data(Qt.UserRole)
        labels = self._generic_labels_for_active_tab()
        if not isinstance(field_name, str) or field_name not in labels:
            return
        lines = self._current_lines()
        index = self._selected_line_index()
        if index < 0 or index >= len(lines):
            return
        current_line = lines[index]
        previous_value = current_line.get(field_name, "")
        try:
            next_value = self._coerce_generic_field_value(field_name, item.text())
        except (ValueError, TypeError, json.JSONDecodeError):
            self._updating_generic_param_table = True
            try:
                if field_name == "recipe" and self.page_state["active_tab"] == "ink_prep":
                    item.setText(self._format_ink_recipe_for_display(previous_value))
                elif field_name in GENERIC_JSON_FIELDS and previous_value not in ("", None):
                    item.setText(json.dumps(previous_value, ensure_ascii=False, sort_keys=True))
                else:
                    item.setText("" if previous_value is None else str(previous_value))
            finally:
                self._updating_generic_param_table = False
            QMessageBox.warning(self, "参数栏", f"{labels[field_name]} 不是合法内容，请修正后再继续。")
            return
        if previous_value == next_value:
            return
        current_line[field_name] = next_value
        self.page_state["active_target_id"] = self._build_active_target_id(current_line, index)
        self._reset_validation_state_after_edit()
        self._sync_context()
        if field_name in {
            "material_prep_instruction_line_id",
            "sku",
            "ink_prep_instruction_line_id",
            "material_name",
            "equipment_prep_instruction_line_id",
            "node_id",
        }:
            self._render_object_list()
            self._render_generic_table_editor()

    def _on_mesh_param_item_changed(self, item: QTableWidgetItem) -> None:
        if self._updating_mesh_param_table or self._updating_widgets:
            return
        if item.column() != 1 or not self._is_mesh_tab():
            return
        field_name = item.data(Qt.UserRole)
        if not isinstance(field_name, str) or field_name not in MESH_PARAM_LABELS:
            return
        lines = self._current_lines()
        index = self._selected_line_index()
        if index < 0 or index >= len(lines):
            return
        current_line = lines[index]
        next_value = coerce_mesh_field_value(field_name, item.text())
        if current_line.get(field_name) == next_value:
            return
        current_line[field_name] = next_value
        self.page_state["active_target_id"] = self._build_active_target_id(current_line, index)
        self._reset_validation_state_after_edit()
        self._sync_context()

    def _format_ink_recipe_for_display(self, value: Any) -> str:
        ratio_view = self._extract_ink_recipe_ratio_view(value)
        if ratio_view in ("", None):
            return ""
        if isinstance(ratio_view, str):
            return ratio_view
        if isinstance(ratio_view, (dict, list)):
            return json.dumps(ratio_view, ensure_ascii=False, indent=2)
        return json.dumps(ratio_view, ensure_ascii=False)

    def _extract_ink_recipe_ratio_view(self, value: Any) -> Any:
        if value in ("", None):
            return ""
        if not isinstance(value, dict):
            return value
        for key in INK_RECIPE_COMPONENT_KEYS:
            if key in value:
                return value[key]
        return value

    def _merge_ink_recipe_ratio_edit(self, previous_value: Any, raw_text: str) -> Any:
        parsed_value = json.loads(raw_text)
        if not isinstance(previous_value, dict):
            return parsed_value
        merged = dict(previous_value)
        for key in INK_RECIPE_COMPONENT_KEYS:
            if key in merged:
                merged[key] = parsed_value
                return merged
        return parsed_value

    def _reset_validation_state_after_edit(self) -> None:
        self.page_state["dirty"] = True
        self.page_state["validation_summary"] = {"passed": False, "errors": [], "risks": []}
        if self.page_state["page_status"] in {"validated", "released"}:
            self.page_state["page_status"] = "created"
            self.page_state["current_instruction_set"]["prep_instruction_header"]["status"] = "created"

    def _selected_object_row(self) -> int:
        row = self.page_state.get("selected_object_row")
        if isinstance(row, int):
            return row
        current_row = self.listObjects.currentRow()
        return current_row if isinstance(current_row, int) else -1

    def _set_selected_object_row(self, row: int) -> None:
        self.page_state["selected_object_row"] = row if row >= 0 else None

    def _force_render_current_object(self) -> None:
        if self._updating_widgets:
            return
        row = self.listObjects.currentRow()
        self._set_selected_object_row(row)
        self._last_selected_row = row if row >= 0 else None
        self._render_instruction_editor()
