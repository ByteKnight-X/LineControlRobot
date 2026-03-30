from __future__ import annotations

import base64
import io
import re
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, List

from PyQt5 import QtCore, QtGui, QtWidgets, uic
from PyQt5.QtWidgets import QMessageBox

from utilities.backend_client import BackendError

try:
    from PyQt5.QtWebEngineWidgets import QWebEngineView
except ImportError:  # pragma: no cover
    QWebEngineView = None


class PreviewWebEngineView(QWebEngineView):
    """QWebEngineView with ctrl+wheel zoom support for SVG preview."""

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._default_zoom_factor = 1.0
        self._zoom_step = 0.1
        self._min_zoom_factor = 0.3
        self._max_zoom_factor = 3.0
        self.setZoomFactor(self._default_zoom_factor)

    def reset_zoom(self) -> None:
        self.setZoomFactor(self._default_zoom_factor)

    def _apply_zoom_delta(self, direction: int) -> None:
        next_zoom = self.zoomFactor() + (self._zoom_step * direction)
        next_zoom = max(self._min_zoom_factor, min(self._max_zoom_factor, next_zoom))
        self.setZoomFactor(next_zoom)

    def wheelEvent(self, event: QtGui.QWheelEvent) -> None:
        if event.modifiers() & QtCore.Qt.ControlModifier:
            delta_y = event.angleDelta().y()
            if delta_y > 0:
                self._apply_zoom_delta(1)
            elif delta_y < 0:
                self._apply_zoom_delta(-1)
            event.accept()
            return
        super().wheelEvent(event)


def _text(value: Any) -> str:
    return "" if value is None else str(value)


def _message_lines(value: Any) -> List[str]:
    if isinstance(value, list):
        return [_text(item).strip() for item in value if _text(item).strip()]
    message = _text(value).strip()
    return [message] if message else []


def _normalize_sizes(value: Any) -> List[int]:
    if value in (None, ""):
        return []
    if isinstance(value, list):
        items = value
    else:
        items = [part.strip() for part in _text(value).split(",") if part.strip()]
    sizes: List[int] = []
    for item in items:
        try:
            sizes.append(int(item))
        except (TypeError, ValueError):
            continue
    return sizes


def _sizes_to_display(value: Any) -> str:
    sizes = _normalize_sizes(value)
    if not sizes:
        return ""
    unique_sizes = sorted(set(sizes))
    if len(unique_sizes) == 1:
        return str(unique_sizes[0])
    return ",".join(str(item) for item in unique_sizes)


def _looks_like_svg_content(value: str) -> bool:
    text = value.strip()
    if not text:
        return False
    lowered = text.lower()
    return (
        (lowered.startswith("<?xml") and "<svg" in lowered)
        or lowered.startswith("<svg")
        or ("<svg" in lowered and "</svg>" in lowered)
    )


def _normalize_svg_markup(svg_text: str) -> str:
    text = _strip_svg_prolog(svg_text)
    match = re.search(r"(<svg\b.*?</svg>)", text, flags=re.IGNORECASE | re.DOTALL)
    if not match:
        return ""
    return match.group(1).strip()


def _strip_svg_prolog(svg_text: str) -> str:
    text = svg_text.strip()
    if not text:
        return ""
    text = re.sub(r"^\s*<\?xml[^>]*\?>\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^\s*<!--.*?-->\s*", "", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"^\s*<!DOCTYPE[^>]*>\s*", "", text, flags=re.IGNORECASE)
    return text.strip()


def _normalize_svg_references(svg_text: str) -> str:
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


def _prefix_svg_ids(svg_text: str, unique_prefix: str) -> str:
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
    normalized_svg = _normalize_svg_markup(svg_text)
    if not normalized_svg:
        return ""
    normalized_svg = _normalize_svg_references(normalized_svg)
    return _prefix_svg_ids(normalized_svg, unique_prefix)


def _validate_svg_xml(svg_text: str) -> str | None:
    try:
        ET.fromstring(svg_text)
    except ET.ParseError as exc:
        return str(exc)
    return None


def _load_ui_with_webengine_support(ui_path: Path, instance: QtWidgets.QWidget) -> None:
    ui_text = ui_path.read_text(encoding="utf-8")
    if 'class="QWebEngineView"' in ui_text and "<customwidgets>" not in ui_text:
        injection = """
  <customwidgets>
    <customwidget>
      <class>PreviewWebEngineView</class>
      <extends>QWebEngineView</extends>
      <header>separation_page</header>
    </customwidget>
  </customwidgets>
"""
        ui_text = ui_text.replace('class="QWebEngineView"', 'class="PreviewWebEngineView"', 1)
        ui_text = ui_text.replace("  <resources/>\n  <connections/>", f"{injection}  <resources/>\n  <connections/>")
        uic.loadUi(io.StringIO(ui_text), instance)
        return
    uic.loadUi(str(ui_path), instance)


def _svg_to_data_url(svg_text: str) -> str:
    encoded_svg = base64.b64encode(svg_text.encode("utf-8")).decode("ascii")
    return f"data:image/svg+xml;base64,{encoded_svg}"


def _build_svg_html(image_src: str) -> str:
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
      overflow: hidden;
      background: #fafafa;
    }}
    body {{
      display: flex;
      align-items: center;
      justify-content: center;
    }}
    .svg-host {{
      width: 100%;
      height: 100%;
      display: flex;
      align-items: center;
      justify-content: center;
      overflow: hidden;
      background: #fafafa;
    }}
    .svg-host img {{
      max-width: 100%;
      max-height: 100%;
      width: auto;
      height: auto;
      display: block;
    }}
  </style>
</head>
<body>
  <div class="svg-host">
    <img class="svg-image" src="{image_src}" alt="SVG preview" />
  </div>
</body>
</html>
"""


def _build_preview_message_html(message: str) -> str:
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
      overflow: hidden;
      background: #fafafa;
      font-family: sans-serif;
    }}
    body {{
      display: flex;
      align-items: center;
      justify-content: center;
    }}
    .message-card {{
      max-width: 80%;
      padding: 16px 20px;
      color: #595959;
      font-size: 13px;
      line-height: 1.6;
      text-align: center;
      background: #ffffff;
      border: 1px solid #f0f0f0;
      border-radius: 8px;
      box-shadow: 0 4px 14px rgba(0, 0, 0, 0.04);
    }}
  </style>
</head>
<body>
  <div class="message-card">{message}</div>
</body>
</html>
"""


def _to_number(value: Any) -> Any:
    if value in (None, ""):
        return value
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return value
    return int(numeric) if numeric.is_integer() else numeric


def _mesh_index_value(value: Any, fallback: int) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return fallback


class ProcessPlanPickerDialog(QtWidgets.QDialog):
    """Dialog for selecting and importing a historical process plan."""

    def __init__(self, process_plans: List[Dict[str, Any]], page_state: Dict[str, Any], parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)
        self._process_plans = process_plans
        self._page_state = page_state
        self._selected_plan: Dict[str, Any] | None = None
        self.setWindowTitle("版本库")
        self.resize(860, 480)
        self.setStyleSheet(
            """
            QDialog { background-color: #f0f2f5; }
            QFrame#dialogCard {
              background-color: #ffffff;
              border: 1px solid #f0f0f0;
              border-radius: 8px;
            }
            QLabel#titleLabel { font-size: 16px; font-weight: 600; color: #262626; }
            QLabel#tipLabel { font-size: 12px; color: #8c8c8c; }
            QTableWidget {
              background-color: #ffffff;
              border: 1px solid #f0f0f0;
              border-radius: 6px;
              gridline-color: #f0f0f0;
              selection-background-color: #e6f7ff;
              selection-color: #262626;
            }
            QHeaderView::section {
              background-color: #fafafa;
              color: #595959;
              border: none;
              border-bottom: 1px solid #f0f0f0;
              padding: 8px;
              font-weight: 600;
            }
            QPushButton {
              background-color: #1890ff;
              border: none;
              color: #ffffff;
              border-radius: 6px;
              padding: 6px 16px;
              min-height: 30px;
              font-weight: 600;
            }
            QPushButton:hover { background-color: #40a9ff; }
            QPushButton:pressed { background-color: #096dd9; }
            QPushButton:disabled { background-color: #d9d9d9; color: #ffffff; }
            """
        )
        self._setup_ui()

    def _setup_ui(self) -> None:
        root_layout = QtWidgets.QVBoxLayout(self)
        root_layout.setContentsMargins(20, 20, 20, 20)

        card = QtWidgets.QFrame(self)
        card.setObjectName("dialogCard")
        card_layout = QtWidgets.QVBoxLayout(card)
        card_layout.setContentsMargins(16, 16, 16, 16)
        card_layout.setSpacing(12)

        title = QtWidgets.QLabel("历史方案库", card)
        title.setObjectName("titleLabel")
        tip = QtWidgets.QLabel("选择一个历史工艺方案后，点击“导入方案”加载到当前页面。", card)
        tip.setObjectName("tipLabel")
        card_layout.addWidget(title)
        card_layout.addWidget(tip)

        self.table = QtWidgets.QTableWidget(len(self._process_plans), 7, card)
        self.table.setHorizontalHeaderLabels(["方案ID", "版本", "SKU", "码段", "配色", "批准人", "状态"])
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeToContents)
        self.table.itemSelectionChanged.connect(self._update_selection_state)

        for row, plan in enumerate(self._process_plans):
            values = [
                _text(plan.get("process_plan_id")),
                _text(plan.get("process_plan_version")),
                _text(plan.get("sku")),
                _sizes_to_display(plan.get("sizes")),
                _text(plan.get("color")),
                _text(plan.get("validated_by")),
                _text(plan.get("status")),
            ]
            for column, value in enumerate(values):
                self.table.setItem(row, column, QtWidgets.QTableWidgetItem(value))
        card_layout.addWidget(self.table)

        footer = QtWidgets.QHBoxLayout()
        footer.addStretch(1)
        self.import_button = QtWidgets.QPushButton("导入方案", card)
        self.import_button.setEnabled(False)
        self.import_button.clicked.connect(self._accept_selection)
        footer.addWidget(self.import_button)
        card_layout.addLayout(footer)

        root_layout.addWidget(card)

    def _update_selection_state(self) -> None:
        rows = self.table.selectionModel().selectedRows()
        has_selection = bool(rows)
        self.import_button.setEnabled(has_selection)
        self._page_state["library_dialog"]["selected_process_plan_id"] = False
        if not has_selection:
            return
        selected = self._process_plans[rows[0].row()]
        self._page_state["library_dialog"]["selected_process_plan_id"] = selected.get("process_plan_id") or True
        self._page_state["focus"]["selected_process_plan_id"] = selected.get("process_plan_id")
        self._page_state["focus"]["selected_process_plan_version"] = selected.get("process_plan_version")

    def _accept_selection(self) -> None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            QMessageBox.information(self, "版本库", "请选择一个历史方案。")
            return
        self._selected_plan = self._process_plans[rows[0].row()]
        self.accept()

    def selected_plan(self) -> Dict[str, Any] | None:
        return self._selected_plan


class SeparationPage(QtWidgets.QWidget):
    """Frontend page controller for forms/separation_page.ui."""

    def __init__(self, controller: Any):
        super().__init__()
        if QWebEngineView is None:
            raise RuntimeError("当前环境缺少 PyQtWebEngine，工艺设计页无法渲染 SVG 预览。")
        ui_path = Path(__file__).resolve().parent / "forms" / "separation_page.ui"
        _load_ui_with_webengine_support(ui_path, self)
        self.controller = controller
        self.page_state: Dict[str, Any] = {
            "page_status": "draft",
            "loading": False,
            "dirty": False,
            "db_process_plan": [],
            "current_plan": {
                "process_plan_header": {},
                "process_plan_line": [],
            },
            "current_process_plan": {
                "process_plan_header": {},
                "process_plan_line": [],
            },
            "active_mesh_index": 0,
            "focus": {
                "selected_process_plan_id": None,
                "selected_process_plan_version": None,
            },
            "dialogs": {
                "library_open": False,
            },
            "validation_summary": {
                "passed": False,
                "errors": [],
                "risks": [],
            },
            "library_dialog": {
                "open": False,
                "selected_process_plan_id": False,
            },
        }
        self._actions_bound = False
        self._setting_up_widgets = False

        self._setup_widgets()
        self._bind_actions()
        self.refresh_data()

    def _setup_widgets(self) -> None:
        self.graphicsPreview.setContextMenuPolicy(QtCore.Qt.NoContextMenu)
        try:
            self.graphicsPreview.page().setBackgroundColor(QtGui.QColor("#fafafa"))
        except Exception:
            pass
        if isinstance(self.graphicsPreview, PreviewWebEngineView):
            self.graphicsPreview.reset_zoom()
        self.canvasLayout.setStretch(0, 0)
        self.canvasLayout.setStretch(1, 1)
        self.canvasLayout.setStretch(2, 0)
        self.graphicsPreview.setVisible(True)
        self.txtSOPSteps.setReadOnly(False)
        self.txtValidationInfo.setReadOnly(True)

    def _bind_actions(self) -> None:
        if self._actions_bound:
            return
        self.btnImportScheme.clicked.connect(self._on_import_scheme)
        self.btnGenerate.clicked.connect(self._on_generate)
        self.btnValidate.clicked.connect(self._on_validate)
        self.btnApprove.clicked.connect(self._on_approve)
        self.btnNext.clicked.connect(self._on_next)
        self.btnPrevMesh.clicked.connect(self._on_prev_mesh)
        self.btnNextMesh.clicked.connect(self._on_next_mesh)

        editors = [
            self.txtWireMaterial,
            self.txtWireModel,
            self.txtWireDia,
            self.txtFrameSpec,
            self.txtSOPSteps,
        ]
        for editor in editors:
            if isinstance(editor, QtWidgets.QTextEdit):
                editor.textChanged.connect(self._mark_dirty)
            else:
                editor.textChanged.connect(self._mark_dirty)
        self.cmbStretchMethod.currentTextChanged.connect(self._mark_dirty)
        self.spinStretchAngle.valueChanged.connect(self._mark_dirty)
        self.spinTpi.valueChanged.connect(self._mark_dirty)
        self.spinTension.valueChanged.connect(self._mark_dirty)
        self._actions_bound = True

    def refresh_data(self) -> None:
        context = getattr(self.controller, "context", {}) or {}
        plan_context = context.get("process_plan_context")

        if isinstance(plan_context, dict):
            header = plan_context.get("process_plan_header")
            lines = plan_context.get("process_plan_line")
        else:
            header = None
            lines = None

        if not isinstance(header, dict):
            header = self._build_header_from_context(context)
        if not isinstance(lines, list):
            lines = self._build_lines_from_context(context)

        self.page_state["current_plan"] = {
            "process_plan_header": dict(header) if isinstance(header, dict) else {},
            "process_plan_line": [dict(item) for item in lines if isinstance(item, dict)],
        }
        self.page_state["current_process_plan"] = self.page_state["current_plan"]
        status = _text(self.page_state["current_plan"]["process_plan_header"].get("status")).strip().lower()
        self.page_state["page_status"] = "Frozen" if status in {"validated", "frozen"} else "draft"
        self.page_state["dirty"] = False
        self.page_state["validation_summary"] = {
            "passed": False,
            "errors": [],
            "risks": [],
        }
        self.page_state["active_mesh_index"] = 0
        header_data = self.page_state["current_plan"]["process_plan_header"]
        self.page_state["focus"]["selected_process_plan_id"] = header_data.get("process_plan_id")
        self.page_state["focus"]["selected_process_plan_version"] = header_data.get("process_plan_version")
        self._render_page()
        self.page_state["active_mesh_index"] = 0
        self._render_page()

    def _build_header_from_context(self, context: Dict[str, Any]) -> Dict[str, Any]:
        header: Dict[str, Any] = {}
        order_context = context.get("order_context")
        lot_context = context.get("lot_context")
        current_order = context.get("current_order")
        current_lot = context.get("current_lot")

        if isinstance(order_context, dict):
            order_header = order_context.get("order_header") or order_context.get("header") or {}
            order_lines = order_context.get("order_line") or order_context.get("lines") or []
        else:
            order_header = current_order.get("header") if isinstance(current_order, dict) else {}
            order_lines = current_order.get("lines") if isinstance(current_order, dict) else []

        if isinstance(lot_context, dict):
            lot_header = lot_context.get("lot_header") or lot_context.get("header") or {}
        else:
            lot_header = current_lot.get("header") if isinstance(current_lot, dict) else {}

        if isinstance(lot_header, dict):
            header["process_plan_id"] = lot_header.get("lot_id") or lot_header.get("id")
            header["status"] = lot_header.get("status")
        if isinstance(order_header, dict):
            header["sku"] = order_header.get("sku")

        valid_lines = [item for item in order_lines if isinstance(item, dict)] if isinstance(order_lines, list) else []
        if valid_lines:
            header["sku"] = header.get("sku") or valid_lines[0].get("sku")
            header["color"] = valid_lines[0].get("color")
            sizes = [item.get("size") for item in valid_lines if item.get("size") not in (None, "")]
            if sizes:
                header["sizes"] = _normalize_sizes(sizes)
        return {key: value for key, value in header.items() if value not in (None, "")}

    def _build_lines_from_context(self, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        plan_context = context.get("process_plan_context")
        if isinstance(plan_context, dict):
            plan_lines = plan_context.get("process_plan_line")
            if isinstance(plan_lines, list):
                return [dict(item) for item in plan_lines if isinstance(item, dict)]

        legacy = context.get("separation_plan") or context.get("separationPlan")
        if not isinstance(legacy, list):
            return []
        items: List[Dict[str, Any]] = []
        for index, item in enumerate(legacy):
            if not isinstance(item, dict):
                continue
            mesh_index = item.get("index")
            try:
                mesh_index = int(mesh_index) + 1
            except (TypeError, ValueError):
                mesh_index = index + 1
            items.append(
                {
                    "mesh_index": mesh_index,
                    "material": item.get("material"),
                    "mesh_model": item.get("model"),
                    "diameter": item.get("lineDiameter"),
                    "stretching": item.get("drawingMethod"),
                    "stretching_degree": item.get("drawAngle"),
                    "tpi": item.get("count"),
                    "tension": item.get("tension"),
                    "frame_specification": item.get("netFrameSpecification"),
                    "pattern_design": item.get("imagePath"),
                    "operation": item.get("operation"),
                }
            )
        return items

    def _render_page(self) -> None:
        self._setting_up_widgets = True
        header = self.page_state["current_plan"]["process_plan_header"]
        line = self._active_line()

        self.txtPlanId.setText(_text(header.get("process_plan_id")))
        self.txtPlanVer.setText(_text(header.get("process_plan_version")))
        self.txtSku.setText(_text(header.get("sku")))
        self.txtCodeRange.setText(_sizes_to_display(header.get("sizes")))
        self.txtColorway.setText(_text(header.get("color")))
        self.txtApprover.setText(_text(header.get("validated_by")))
        self.txtStatus.setText(_text(header.get("status") or self.page_state["page_status"]))

        self.txtWireMaterial.setText(_text(line.get("material")))
        self.txtWireModel.setText(_text(line.get("mesh_model")))
        self.txtWireDia.setText(_text(line.get("diameter")))
        self.txtFrameSpec.setText(_text(line.get("frame_specification")))
        self._set_combo_text(self.cmbStretchMethod, line.get("stretching"))
        self.spinStretchAngle.setValue(float(line.get("stretching_degree") or 0))
        self.spinTpi.setValue(int(float(line.get("tpi") or 0)))
        self.spinTension.setValue(float(line.get("tension") or 0))
        self.txtSOPSteps.setPlainText(_text(line.get("operation")))

        self._render_validation()
        self._render_preview()
        self._render_mesh_navigation()
        self._sync_button_states()
        self._setting_up_widgets = False

    def _render_validation(self) -> None:
        summary = self.page_state["validation_summary"]
        lines = [f"页面状态：{self.page_state['page_status']}"]
        lines.append(f"是否有未保存修改：{'是' if self.page_state['dirty'] else '否'}")
        lines.append(f"校验状态：{'通过' if summary.get('passed') else '未通过'}")
        errors = _message_lines(summary.get("errors"))
        risks = _message_lines(summary.get("risks"))
        lines.append("错误：")
        lines.extend(f"- {item}" for item in errors) if errors else lines.append("- 无")
        lines.append("风险：")
        lines.extend(f"- {item}" for item in risks) if risks else lines.append("- 无")
        self.txtValidationInfo.setPlainText("\n".join(lines))

    def _render_preview(self) -> None:
        line = self._active_line()
        svg_text = _text(line.get("pattern_design")).strip()
        base_url = QtCore.QUrl.fromLocalFile(str(Path(__file__).resolve().parent) + "/")
        if isinstance(self.graphicsPreview, PreviewWebEngineView):
            self.graphicsPreview.reset_zoom()

        if not svg_text:
            self.graphicsPreview.setHtml(_build_preview_message_html("当前网版未提供 SVG 内容。"), base_url)
            return

        svg_prefix = f"svg_preview_{int(time.time() * 1000)}_{self.page_state['active_mesh_index']}_"
        processed_svg = preprocess_svg(svg_text, svg_prefix)
        if not processed_svg:
            self.graphicsPreview.setHtml(
                _build_preview_message_html("SVG 结构无效，缺少可渲染的 &lt;svg&gt; 根节点。"),
                base_url,
            )
            return
        xml_error = _validate_svg_xml(processed_svg)
        if xml_error:
            self.graphicsPreview.setHtml(
                _build_preview_message_html(f"SVG 结构无效，预处理后 XML 不合法。<br/>{xml_error}"),
                base_url,
            )
            return

        image_src = _svg_to_data_url(processed_svg)
        self.graphicsPreview.setHtml(
            _build_svg_html(image_src),
            base_url,
        )

    def _set_combo_text(self, combo: QtWidgets.QComboBox, value: Any) -> None:
        text = _text(value).strip()
        if not text:
            combo.setCurrentIndex(-1)
            return
        index = combo.findText(text)
        if index < 0:
            combo.addItem(text)
            index = combo.findText(text)
        combo.setCurrentIndex(index)

    def _active_line(self) -> Dict[str, Any]:
        lines = self.page_state["current_plan"]["process_plan_line"]
        if not lines:
            return {}
        index = self.page_state["active_mesh_index"]
        if index < 0 or index >= len(lines):
            self.page_state["active_mesh_index"] = 0
            return lines[0]
        return lines[index]

    def _mark_dirty(self, *_args: Any) -> None:
        if self._setting_up_widgets or self.page_state["loading"]:
            return
        self.page_state["dirty"] = True
        if self.page_state["page_status"] in {"validated", "Frozen"}:
            self.page_state["page_status"] = "draft"
        self._render_validation()
        self._sync_button_states()

    def _set_loading(self, is_loading: bool) -> None:
        self.page_state["loading"] = is_loading
        self._sync_button_states()

    def _sync_button_states(self) -> None:
        loading = self.page_state["loading"]
        page_status = self.page_state["page_status"]
        self.btnImportScheme.setEnabled(not loading)
        self.btnGenerate.setEnabled(not loading)
        self.btnValidate.setEnabled(not loading)
        self.btnApprove.setEnabled((not loading) and page_status == "validated")
        self.btnNext.setEnabled((not loading) and page_status == "Frozen")
        self._render_mesh_navigation()

    def _render_mesh_navigation(self) -> None:
        lines = self.page_state["current_plan"]["process_plan_line"]
        loading = self.page_state["loading"]
        if not lines:
            self.lblMeshPager.setText("0 / 0")
            self.btnPrevMesh.setEnabled(False)
            self.btnNextMesh.setEnabled(False)
            return

        max_index = len(lines) - 1
        active_index = min(max(self.page_state["active_mesh_index"], 0), max_index)
        self.page_state["active_mesh_index"] = active_index
        current_mesh_index = _mesh_index_value(lines[active_index].get("mesh_index"), active_index + 1)
        max_mesh_index = _mesh_index_value(lines[max_index].get("mesh_index"), len(lines))

        self.lblMeshPager.setText(f"{current_mesh_index} / {max_mesh_index}")
        self.btnPrevMesh.setEnabled((not loading) and active_index > 0)
        self.btnNextMesh.setEnabled((not loading) and active_index < max_index)

    def _collect_current_mesh_from_widgets(self) -> None:
        lines = self.page_state["current_plan"]["process_plan_line"]
        if not lines:
            lines.append({"mesh_index": 1})
            self.page_state["active_mesh_index"] = 0
        line = lines[self.page_state["active_mesh_index"]]
        line["mesh_index"] = line.get("mesh_index") or self.page_state["active_mesh_index"] + 1
        line["material"] = self.txtWireMaterial.text().strip()
        line["mesh_model"] = self.txtWireModel.text().strip()
        line["diameter"] = self.txtWireDia.text().strip()
        line["stretching"] = self.cmbStretchMethod.currentText().strip()
        line["stretching_degree"] = self.spinStretchAngle.value()
        line["tpi"] = self.spinTpi.value()
        line["tension"] = self.spinTension.value()
        line["frame_specification"] = self.txtFrameSpec.text().strip()
        line["operation"] = self.txtSOPSteps.toPlainText().strip()

    def _on_prev_mesh(self) -> None:
        if self.page_state["loading"]:
            return
        self._collect_current_mesh_from_widgets()
        if self.page_state["active_mesh_index"] <= 0:
            return
        self.page_state["active_mesh_index"] -= 1
        self._render_page()

    def _on_next_mesh(self) -> None:
        if self.page_state["loading"]:
            return
        lines = self.page_state["current_plan"]["process_plan_line"]
        self._collect_current_mesh_from_widgets()
        if self.page_state["active_mesh_index"] >= len(lines) - 1:
            return
        self.page_state["active_mesh_index"] += 1
        self._render_page()

    def _update_validation_summary(self, summary: Dict[str, Any]) -> None:
        self.page_state["validation_summary"] = {
            "passed": bool(summary.get("passed")),
            "errors": _message_lines(summary.get("errors")),
            "risks": _message_lines(summary.get("risks")),
        }
        self._render_validation()

    def _load_process_plan(self, plan_detail: Dict[str, Any]) -> None:
        header = plan_detail.get("process_plan_header")
        lines = plan_detail.get("process_plan_line")
        self.page_state["current_plan"] = {
            "process_plan_header": dict(header) if isinstance(header, dict) else {},
            "process_plan_line": [dict(item) for item in lines if isinstance(item, dict)] if isinstance(lines, list) else [],
        }
        self.page_state["current_process_plan"] = self.page_state["current_plan"]
        status = _text(self.page_state["current_plan"]["process_plan_header"].get("status")).strip().lower()
        self.page_state["page_status"] = "Frozen" if status in {"frozen", "validated"} else "draft"
        self.page_state["dirty"] = False
        self.page_state["active_mesh_index"] = 0
        self.page_state["focus"]["selected_process_plan_id"] = self.page_state["current_plan"]["process_plan_header"].get(
            "process_plan_id"
        )
        self.page_state["focus"]["selected_process_plan_version"] = self.page_state["current_plan"][
            "process_plan_header"
        ].get("process_plan_version")
        self.page_state["validation_summary"] = {
            "passed": False,
            "errors": [],
            "risks": [],
        }
        self._render_page()

    def _sync_process_plan_context(self) -> None:
        context = getattr(self.controller, "context", {})
        context["process_plan_context"] = {
            "process_plan_header": dict(self.page_state["current_plan"]["process_plan_header"]),
            "process_plan_line": [dict(item) for item in self.page_state["current_plan"]["process_plan_line"]],
        }
        context["separation_plan"] = self._build_legacy_separation_plan()
        context["separationPlan"] = context["separation_plan"]

    def _build_payload(self) -> Dict[str, Any]:
        self._collect_current_mesh_from_widgets()
        header = dict(self.page_state["current_plan"]["process_plan_header"])
        header_payload = {
            "sku": header.get("sku"),
            "sizes": _normalize_sizes(header.get("sizes")),
            "color": header.get("color"),
            "validated_by": header.get("validated_by"),
        }
        lines: List[Dict[str, Any]] = []
        for item in self.page_state["current_plan"]["process_plan_line"]:
            line = {
                "mesh_index": item.get("mesh_index"),
                "sizes": item.get("sizes") or _sizes_to_display(header_payload["sizes"]),
                "pattern_design": item.get("pattern_design"),
                "material": item.get("material"),
                "mesh_model": item.get("mesh_model"),
                "diameter": item.get("diameter"),
                "stretching": item.get("stretching"),
                "stretching_degree": item.get("stretching_degree"),
                "tpi": item.get("tpi"),
                "tension": item.get("tension"),
                "frame_specification": item.get("frame_specification"),
                "operation": item.get("operation"),
            }
            for key in ("mesh_index", "diameter", "stretching_degree", "tpi", "tension"):
                line[key] = _to_number(line.get(key))
            lines.append(line)
        return {
            "process_plan_header": header_payload,
            "process_plan_line": lines,
        }

    def _build_legacy_separation_plan(self) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        for index, line in enumerate(self.page_state["current_plan"]["process_plan_line"]):
            mesh_index = line.get("mesh_index", index + 1)
            try:
                mesh_index = int(mesh_index) - 1
            except (TypeError, ValueError):
                mesh_index = index
            items.append(
                {
                    "index": mesh_index,
                    "imagePath": line.get("pattern_design"),
                    "material": line.get("material"),
                    "model": line.get("mesh_model"),
                    "lineDiameter": line.get("diameter"),
                    "drawingMethod": line.get("stretching"),
                    "drawAngle": line.get("stretching_degree"),
                    "count": line.get("tpi"),
                    "tension": line.get("tension"),
                    "netFrameSpecification": line.get("frame_specification"),
                    "operation": line.get("operation"),
                }
            )
        return items

    def _on_import_scheme(self) -> None:
        self.page_state["library_dialog"]["open"] = True
        self.page_state["dialogs"]["library_open"] = True
        self.page_state["library_dialog"]["selected_process_plan_id"] = False
        self._set_loading(True)
        try:
            process_plans = self.controller.backend.process_plans.list()
        except BackendError as exc:
            self.page_state["library_dialog"]["open"] = False
            self.page_state["dialogs"]["library_open"] = False
            self._set_loading(False)
            QMessageBox.critical(self, "版本库", f"版本库加载失败：{exc}")
            return
        self._set_loading(False)
        self.page_state["db_process_plan"] = [dict(item) for item in process_plans]

        if not process_plans:
            self.page_state["library_dialog"]["open"] = False
            self.page_state["dialogs"]["library_open"] = False
            QMessageBox.information(self, "版本库", "版本库为空，暂无历史方案。")
            return

        dialog = ProcessPlanPickerDialog(process_plans, self.page_state, self)
        if dialog.exec_() != QtWidgets.QDialog.Accepted:
            self.page_state["library_dialog"]["open"] = False
            self.page_state["dialogs"]["library_open"] = False
            self.page_state["library_dialog"]["selected_process_plan_id"] = False
            return

        selected = dialog.selected_plan()
        if not selected:
            self.page_state["library_dialog"]["open"] = False
            self.page_state["dialogs"]["library_open"] = False
            return

        process_plan_id = _text(selected.get("process_plan_id")).strip()
        try:
            process_plan_version = int(float(selected.get("process_plan_version")))
        except (TypeError, ValueError):
            self.page_state["library_dialog"]["open"] = False
            self.page_state["dialogs"]["library_open"] = False
            QMessageBox.warning(self, "版本库", "历史方案版本号无效。")
            return

        self._set_loading(True)
        try:
            detail = self.controller.backend.process_plans.detail(process_plan_id, process_plan_version)
        except BackendError as exc:
            self.page_state["library_dialog"]["open"] = False
            self.page_state["dialogs"]["library_open"] = False
            self._set_loading(False)
            QMessageBox.critical(self, "版本库", f"版本详情加载失败：{exc}")
            return
        self._set_loading(False)
        self.page_state["library_dialog"]["open"] = False
        self.page_state["dialogs"]["library_open"] = False
        self._load_process_plan(detail)
        self._sync_process_plan_context()

    def _on_generate(self) -> None:
        QMessageBox.information(self, "AI优化", "AI优化入口已保留，当前前端未接入生成逻辑。")

    def _on_validate(self) -> None:
        payload = self._build_payload()
        self._set_loading(True)
        try:
            result = self.controller.backend.process_plans.validate(payload)
        except BackendError as exc:
            self._set_loading(False)
            QMessageBox.critical(self, "AI校验", f"方案校验失败：{exc}")
            return
        self._set_loading(False)
        self._update_validation_summary(result)
        if self.page_state["validation_summary"]["passed"]:
            self.page_state["page_status"] = "validated"
            self.page_state["dirty"] = False
        else:
            self.page_state["page_status"] = "draft"
        self._render_page()
        QMessageBox.information(self, "AI校验", "已完成方案校验。")

    def _on_approve(self) -> None:
        if self.page_state["page_status"] != "validated":
            QMessageBox.warning(self, "批准方案", "当前页面未处于 validated 状态，无法批准。")
            return
        payload = self._build_payload()
        self._set_loading(True)
        try:
            result = self.controller.backend.process_plans.approve(payload)
        except BackendError as exc:
            self._set_loading(False)
            QMessageBox.critical(self, "批准方案", f"方案批准失败：{exc}")
            return
        self._set_loading(False)
        self._update_validation_summary(result)
        if result.get("approved") is not True:
            self.page_state["page_status"] = "draft"
            self._render_page()
            QMessageBox.warning(self, "批准方案", "方案批准失败，请检查校验反馈。")
            return

        header = self.page_state["current_plan"]["process_plan_header"]
        header["process_plan_id"] = result.get("process_plan_id")
        header["process_plan_version"] = result.get("process_plan_version")
        header["status"] = result.get("status")
        self.page_state["page_status"] = "Frozen"
        self.page_state["dirty"] = False
        self._sync_process_plan_context()
        self._render_page()
        QMessageBox.information(
            self,
            "批准方案",
            f"方案已批准：{result.get('process_plan_id')} V{result.get('process_plan_version')}，状态 {result.get('status')}。",
        )

    def _on_next(self) -> None:
        if self.page_state["page_status"] != "Frozen":
            QMessageBox.warning(self, "下一步", "当前方案未冻结，无法进入工艺路线页面。")
            return
        self._collect_current_mesh_from_widgets()
        self._sync_process_plan_context()
        if not hasattr(self.controller, "show_page"):
            QMessageBox.critical(self, "下一步", "主窗口未提供页面切换能力。")
            return
        self.controller.show_page("process_route_page")
