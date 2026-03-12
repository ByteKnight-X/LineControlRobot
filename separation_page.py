from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from PyQt5 import QtCore, QtGui, QtWidgets, uic
from PyQt5.QtWidgets import QMessageBox

from utilities.backend_client import BackendError

try:
    from PyQt5.QtSvg import QGraphicsSvgItem
except ImportError:  # pragma: no cover
    QGraphicsSvgItem = None


def _text(value: Any) -> str:
    return "" if value is None else str(value)


def _message_lines(value: Any) -> List[str]:
    if isinstance(value, list):
        return [_text(item).strip() for item in value if _text(item).strip()]
    message = _text(value).strip()
    return [message] if message else []


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
                _text(plan.get("size")),
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
        ui_path = Path(__file__).resolve().parent / "forms" / "separation_page.ui"
        uic.loadUi(str(ui_path), self)
        self.controller = controller
        self.page_state: Dict[str, Any] = {
            "page_status": "draft",
            "loading": False,
            "dirty": False,
            "current_plan": {
                "process_plan_header": {},
                "process_plan_line": [],
            },
            "active_mesh_index": 0,
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
        self.graphicsPreview.setScene(QtWidgets.QGraphicsScene(self))
        self.graphicsPreview.setRenderHint(QtGui.QPainter.Antialiasing, True)
        self.graphicsPreview.setRenderHint(QtGui.QPainter.SmoothPixmapTransform, True)
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
            header["process_plan_version"] = order_header.get("version")
            header["sku"] = order_header.get("sku")

        valid_lines = [item for item in order_lines if isinstance(item, dict)] if isinstance(order_lines, list) else []
        if valid_lines:
            header["sku"] = header.get("sku") or valid_lines[0].get("sku")
            header["colorway"] = valid_lines[0].get("color")
            sizes = [str(item.get("size")) for item in valid_lines if item.get("size") not in (None, "")]
            if sizes:
                header["code_range"] = sizes[0] if len(set(sizes)) == 1 else f"{min(sizes)}-{max(sizes)}"
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
        self.txtCodeRange.setText(_text(header.get("code_range") or header.get("size")))
        self.txtColorway.setText(_text(header.get("colorway") or header.get("color")))
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
        scene = QtWidgets.QGraphicsScene(self)
        line = self._active_line()
        raw_path = _text(line.get("pattern_design")).strip()
        candidate = self._resolve_preview_path(raw_path)

        if not raw_path:
            text_item = scene.addText("当前网版未提供 pattern_design。")
            text_item.setDefaultTextColor(QtGui.QColor("#595959"))
            text_item.setPos(12, 12)
            self.graphicsPreview.setScene(scene)
            return

        if candidate is None or not candidate.exists():
            text_item = scene.addText(f"图案文件不存在：{Path(raw_path).name}")
            text_item.setDefaultTextColor(QtGui.QColor("#595959"))
            text_item.setPos(12, 12)
            self.graphicsPreview.setScene(scene)
            return

        pixmap = QtGui.QPixmap(str(candidate))
        if not pixmap.isNull():
            scene.addPixmap(pixmap)
            self.graphicsPreview.setScene(scene)
            self._fit_preview(scene)
            return

        if candidate.suffix.lower() == ".svg" and QGraphicsSvgItem is not None:
            scene.addItem(QGraphicsSvgItem(str(candidate)))
            self.graphicsPreview.setScene(scene)
            self._fit_preview(scene)
            return

        text_item = scene.addText(f"无法预览文件：{candidate.name}")
        text_item.setDefaultTextColor(QtGui.QColor("#595959"))
        text_item.setPos(12, 12)
        self.graphicsPreview.setScene(scene)

    def _resolve_preview_path(self, raw_path: str) -> Path | None:
        if not raw_path:
            return None
        normalized = raw_path.strip().strip('"').replace("\\", "/")
        project_root = Path(__file__).resolve().parent
        basename = Path(normalized).name
        candidates = [
            Path(normalized),
            project_root / normalized,
            project_root / "resource" / "layers" / basename,
            project_root / "Resource" / "layers" / basename,
            project_root / "resource" / basename,
            project_root / "Resource" / basename,
        ]
        for candidate in candidates:
            if candidate.exists():
                return candidate.resolve()
        return None

    def _fit_preview(self, scene: QtWidgets.QGraphicsScene) -> None:
        rect = scene.itemsBoundingRect()
        if rect.isNull():
            return
        QtCore.QTimer.singleShot(0, lambda: self.graphicsPreview.fitInView(rect, QtCore.Qt.KeepAspectRatio))

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
        status = _text(self.page_state["current_plan"]["process_plan_header"].get("status")).strip().lower()
        self.page_state["page_status"] = "Frozen" if status == "frozen" else "draft"
        self.page_state["dirty"] = False
        self.page_state["active_mesh_index"] = 0
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
        header["size"] = header.get("size") or header.get("code_range")
        header["color"] = header.get("color") or header.get("colorway")
        lines: List[Dict[str, Any]] = []
        for item in self.page_state["current_plan"]["process_plan_line"]:
            line = dict(item)
            for key in ("mesh_index", "diameter", "stretching_degree", "tpi", "tension"):
                line[key] = _to_number(line.get(key))
            lines.append(line)
        return {
            "process_plan_header": header,
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
        self.page_state["library_dialog"]["selected_process_plan_id"] = False
        self._set_loading(True)
        try:
            process_plans = self.controller.backend.process_plans.list()
        except BackendError as exc:
            self.page_state["library_dialog"]["open"] = False
            self._set_loading(False)
            QMessageBox.critical(self, "版本库", f"版本库加载失败：{exc}")
            return
        self._set_loading(False)

        if not process_plans:
            self.page_state["library_dialog"]["open"] = False
            QMessageBox.information(self, "版本库", "版本库为空，暂无历史方案。")
            return

        dialog = ProcessPlanPickerDialog(process_plans, self.page_state, self)
        if dialog.exec_() != QtWidgets.QDialog.Accepted:
            self.page_state["library_dialog"]["open"] = False
            self.page_state["library_dialog"]["selected_process_plan_id"] = False
            return

        selected = dialog.selected_plan()
        if not selected:
            self.page_state["library_dialog"]["open"] = False
            return

        process_plan_id = _text(selected.get("process_plan_id")).strip()
        try:
            process_plan_version = int(float(selected.get("process_plan_version")))
        except (TypeError, ValueError):
            self.page_state["library_dialog"]["open"] = False
            QMessageBox.warning(self, "版本库", "历史方案版本号无效。")
            return

        self._set_loading(True)
        try:
            detail = self.controller.backend.process_plans.detail(process_plan_id, process_plan_version)
        except BackendError as exc:
            self.page_state["library_dialog"]["open"] = False
            self._set_loading(False)
            QMessageBox.critical(self, "版本库", f"版本详情加载失败：{exc}")
            return
        self._set_loading(False)
        self.page_state["library_dialog"]["open"] = False
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
        self.controller.show_page("route_page")
