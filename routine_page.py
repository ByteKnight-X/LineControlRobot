from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

from PyQt5 import QtCore, QtGui, QtWidgets, uic
from PyQt5.QtCore import QPointF, QRectF, Qt
from PyQt5.QtGui import QColor, QPainter, QPainterPath, QPen, QPolygonF
from PyQt5.QtWidgets import QMessageBox

from utilities.backend_client import BackendError
from utilities.prep_utils import build_constraint_context


def _text(value: Any) -> str:
    return "" if value is None else str(value)


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _normalize_params(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    if value in (None, ""):
        return {}
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return {}
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {"raw": value}
    return value


def _parse_params_text(text: str) -> Any:
    payload_text = text.strip() or "{}"
    try:
        return json.loads(payload_text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Params 不是合法 JSON：{exc}") from exc


def _render_json(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, indent=2)


def _short_json(value: Any, limit: int = 64) -> str:
    try:
        text = json.dumps(value, ensure_ascii=False)
    except TypeError:
        text = _text(value)
    if len(text) <= limit:
        return text
    return f"{text[: limit - 3]}..."


class RouteNodeItem(QtWidgets.QGraphicsRectItem):
    """React Flow-like node card."""

    def __init__(
        self,
        rect: QRectF,
        node: Dict[str, Any],
        open_editor,
        locked: bool,
    ) -> None:
        super().__init__(rect)
        self.node = node
        self._open_editor = open_editor
        self._locked = locked
        self.setPen(QPen(QColor("#D7DCE5"), 1))
        self.setBrush(QtGui.QBrush(QColor("#FFFFFF")))
        self.setFlag(QtWidgets.QGraphicsItem.ItemIsSelectable, True)
        self.setAcceptHoverEvents(True)
        self.setZValue(20)

        hint = "双击查看并编辑节点"
        self.setToolTip(
            f"{_text(node.get('node_id'))}\n"
            f"instruction: {_text(node.get('instruction'))}\n"
            f"params: {_short_json(node.get('params', {}), 120)}\n"
            f"{hint}"
        )

        strip_rect = QRectF(rect.x(), rect.y(), rect.width(), 28)
        strip = QtWidgets.QGraphicsRectItem(strip_rect, self)
        strip.setPen(QPen(Qt.NoPen))
        strip.setBrush(QtGui.QBrush(QColor("#EEF3FF")))
        strip.setZValue(21)

        node_id = QtWidgets.QGraphicsSimpleTextItem(
            _text(node.get("node_id") or "未命名节点"),
            self,
        )
        node_id_font = node_id.font()
        node_id_font.setPointSize(12)
        node_id_font.setBold(True)
        node_id.setFont(node_id_font)
        node_id.setBrush(QtGui.QBrush(QColor("#1F2937")))

        text_rect = node_id.boundingRect()
        node_id.setPos(
            rect.x() + (rect.width() - text_rect.width()) / 2,
            rect.y() + (rect.height() - text_rect.height()) / 2,
        )
        node_id.setZValue(22)

        port_in = QtWidgets.QGraphicsEllipseItem(
            rect.x() - 6,
            rect.center().y() - 6,
            12,
            12,
            self,
        )
        port_in.setPen(QPen(QColor("#9CA3AF"), 1))
        port_in.setBrush(QtGui.QBrush(QColor("#FFFFFF")))
        port_in.setZValue(25)

        port_out = QtWidgets.QGraphicsEllipseItem(
            rect.right() - 6,
            rect.center().y() - 6,
            12,
            12,
            self,
        )
        port_out.setPen(QPen(QColor("#9CA3AF"), 1))
        port_out.setBrush(QtGui.QBrush(QColor("#FFFFFF")))
        port_out.setZValue(25)

    def paint(self, painter, option, widget=None) -> None:
        painter.setRenderHint(QPainter.Antialiasing)

        shadow_rect = self.rect().translated(0, 3)
        painter.setPen(QPen(Qt.NoPen))
        painter.setBrush(QColor(15, 23, 42, 20))
        painter.drawRoundedRect(shadow_rect, 12, 12)

        border = QColor("#335DFF") if self.isSelected() else QColor("#D7DCE5")
        painter.setPen(QPen(border, 1.4))
        painter.setBrush(self.brush())
        painter.drawRoundedRect(self.rect(), 12, 12)

    def mouseDoubleClickEvent(self, event) -> None:
        self._open_editor(self.node)
        super().mouseDoubleClickEvent(event)


class LoopEdgeItem(QtWidgets.QGraphicsPathItem):
    """Editable loop edge (orthogonal polyline)."""

    def __init__(
        self,
        path: QPainterPath,
        loop_data: Dict[str, Any],
        open_editor,
        locked: bool,
    ) -> None:
        super().__init__(path)
        self.loop_data = loop_data
        self._open_editor = open_editor
        self._locked = locked
        self.setPen(QPen(QColor("#F59E0B"), 2, Qt.DashLine, Qt.RoundCap, Qt.RoundJoin))
        self.setBrush(QtGui.QBrush(Qt.NoBrush))
        self.setAcceptHoverEvents(True)
        self.setZValue(8)

        hint = "已冻结" if locked else "双击编辑循环边"
        self.setToolTip(
            f"loop: {_text(loop_data.get('loop_id'))}\n"
            f"entry: {_text(loop_data.get('entry_node_id'))}\n"
            f"exit: {_text(loop_data.get('exit_node_id'))}\n"
            f"count: {_text(loop_data.get('loop_count'))}\n"
            f"{hint}"
        )

    def hoverEnterEvent(self, event) -> None:
        self.setPen(QPen(QColor("#D97706"), 2.4, Qt.DashLine, Qt.RoundCap, Qt.RoundJoin))
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event) -> None:
        self.setPen(QPen(QColor("#F59E0B"), 2, Qt.DashLine, Qt.RoundCap, Qt.RoundJoin))
        super().hoverLeaveEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        if not self._locked:
            self._open_editor(self.loop_data)
        super().mouseDoubleClickEvent(event)


class ProcessRoutePickerDialog(QtWidgets.QDialog):
    def __init__(self, routes: List[Dict[str, Any]], parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._routes = routes
        self._selected_route: Dict[str, Any] | None = None
        self.setWindowTitle("版本库")
        self.resize(900, 480)
        layout = QtWidgets.QVBoxLayout(self)

        tip = QtWidgets.QLabel("选择一个历史工艺路线版本并导入。", self)
        layout.addWidget(tip)

        self.table = QtWidgets.QTableWidget(len(routes), 6, self)
        self.table.setHorizontalHeaderLabels(
            ["批次号", "路线ID", "版本号", "产线规格", "审批人", "状态"]
        )
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeToContents)
        for row, route in enumerate(routes):
            values = [
                _text(route.get("lot_id")),
                _text(route.get("process_route_id")),
                _text(route.get("process_route_version")),
                _text(route.get("line_spec_id")),
                _text(route.get("approved_by")),
                _text(route.get("status")),
            ]
            for column, value in enumerate(values):
                self.table.setItem(row, column, QtWidgets.QTableWidgetItem(value))
        layout.addWidget(self.table)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Cancel | QtWidgets.QDialogButtonBox.Ok,
            parent=self,
        )
        buttons.accepted.connect(self._accept_selection)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _accept_selection(self) -> None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            QMessageBox.information(self, "版本库", "请选择一个历史工艺路线版本。")
            return
        self._selected_route = self._routes[rows[0].row()]
        self.accept()

    def selected_route(self) -> Dict[str, Any] | None:
        return self._selected_route


class ProcessRoutePage(QtWidgets.QWidget):
    """Frontend page controller for process routine page."""

    MIN_ZOOM = 0.35
    MAX_ZOOM = 2.8
    ZOOM_FACTOR = 1.15

    NODE_W = 192
    NODE_H = 120
    NODE_GAP_X = 56
    START_X = 64
    BASE_Y = 184
    LOOP_LANE_HEIGHT = 84

    def __init__(self, controller: Any):
        super().__init__()
        ui_path = Path(__file__).resolve().parent / "forms" / "process_routine_page.ui"
        uic.loadUi(str(ui_path), self)
        self.controller = controller
        self.page_state: Dict[str, Any] = {
            "page_status": "created",
            "loading": False,
            "dirty": False,
            "current_route": {
                "process_route_header": {},
                "process_route_loop_line": [],
                "process_route_loop_step_line": [],
            },
            "active_loop_id": "",
            "active_node_id": "",
            "validation_summary": {"passed": False, "errors": [], "risks": []},
            "simulation": {
                "objective_weight": {"efficiency": 0.5, "cost": 0.5},
                "simulation_results": [],
                "assumption": {},
            },
            "simulation_status": "idle",
            "objective_weight": {"efficiency": 0.5, "cost": 0.5},
            "assumption": {},
            "library_dialog": {"open": False},
        }
        self._updating_widgets = False
        self._node_items: Dict[str, RouteNodeItem] = {}
        self._graph_scene_rect = QRectF()
        self._setup_widgets()
        self._bind_actions()
        self.refresh_data()

    def _setup_widgets(self) -> None:
        self.graphicsDigitalTwin.setScene(QtWidgets.QGraphicsScene(self))
        self.graphicsDigitalTwin.setRenderHint(QPainter.Antialiasing, True)
        self.graphicsDigitalTwin.setRenderHint(QPainter.TextAntialiasing, True)
        self.graphicsDigitalTwin.setDragMode(QtWidgets.QGraphicsView.ScrollHandDrag)
        self.graphicsDigitalTwin.setTransformationAnchor(QtWidgets.QGraphicsView.AnchorUnderMouse)
        self.graphicsDigitalTwin.setResizeAnchor(QtWidgets.QGraphicsView.AnchorViewCenter)
        self.graphicsDigitalTwin.setViewportUpdateMode(QtWidgets.QGraphicsView.FullViewportUpdate)
        self.graphicsDigitalTwin.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.graphicsDigitalTwin.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.graphicsDigitalTwin.viewport().installEventFilter(self)
        self.graphicsDigitalTwin.setMouseTracking(True)
        self.txtValidationInfo.setReadOnly(True)
        self.tblSimulationResult.setRowCount(0)

    def _bind_actions(self) -> None:
        self.btnVersionLib.clicked.connect(self._on_import_route)
        self.btnStartSim.clicked.connect(
            lambda: QMessageBox.information(self, "启动仿真", "仿真功能待接入。")
        )
        self.btnOptimize.clicked.connect(
            lambda: QMessageBox.information(self, "AI优化", "AI优化功能待接入。")
        )
        self.btnValidate.clicked.connect(self._on_validate)
        self.btnApprove.clicked.connect(self._on_approve)
        self.btnNext.clicked.connect(self._on_next)
        self.txtConstraints.textChanged.connect(self._on_constraints_changed)
        self.sliderEfficiencyCostBalance.valueChanged.connect(self._on_weight_changed)

    def eventFilter(self, watched: QtCore.QObject, event: QtCore.QEvent) -> bool:
        if watched is self.graphicsDigitalTwin.viewport():
            if event.type() == QtCore.QEvent.Wheel:
                wheel_event = event
                angle = wheel_event.angleDelta().y()
                if angle == 0:
                    return True
                factor = self.ZOOM_FACTOR if angle > 0 else 1.0 / self.ZOOM_FACTOR
                self._zoom_graph_view(factor, wheel_event.pos())
                return True

            if event.type() == QtCore.QEvent.MouseButtonDblClick:
                mouse_event = event
                if mouse_event.button() == Qt.LeftButton:
                    item = self.graphicsDigitalTwin.itemAt(mouse_event.pos())
                    if item is not None:
                        return False
                    self._fit_graph_view()
                    return True
        return super().eventFilter(watched, event)

    def _zoom_graph_view(self, factor: float, anchor_pos: QtCore.QPoint | None = None) -> None:
        view = self.graphicsDigitalTwin
        current_scale = view.transform().m11()
        target_scale = current_scale * factor
        if target_scale < self.MIN_ZOOM:
            factor = self.MIN_ZOOM / max(current_scale, 0.0001)
        elif target_scale > self.MAX_ZOOM:
            factor = self.MAX_ZOOM / max(current_scale, 0.0001)

        if anchor_pos is None:
            view.scale(factor, factor)
            return

        before = view.mapToScene(anchor_pos)
        view.scale(factor, factor)
        after = view.mapToScene(anchor_pos)
        delta = after - before
        view.translate(delta.x(), delta.y())

    def _fit_graph_view(self) -> None:
        if self._graph_scene_rect.isNull():
            return
        self.graphicsDigitalTwin.resetTransform()
        self.graphicsDigitalTwin.fitInView(
            self._graph_scene_rect.adjusted(-32, -32, 32, 32),
            Qt.KeepAspectRatio,
        )

    def refresh_data(self) -> None:
        context = getattr(self.controller, "context", {}) or {}
        route_context = context.get("process_route_context")
        if not isinstance(route_context, dict):
            route_context = {}

        current_route = self._normalize_route_context(route_context)
        if not any(current_route.values()):
            self._set_empty_state()
            return

        self.page_state["current_route"] = current_route
        status = _text(current_route["process_route_header"].get("status")).strip().lower()
        self.page_state["page_status"] = status or "created"
        self.page_state["dirty"] = False
        self._render_page()

    def _set_empty_state(self) -> None:
        self.page_state["current_route"] = {
            "process_route_header": {},
            "process_route_loop_line": [],
            "process_route_loop_step_line": [],
        }
        self.page_state["page_status"] = "created"
        self.page_state["dirty"] = False
        self.page_state["validation_summary"] = {"passed": False, "errors": [], "risks": []}
        self._render_page(empty_message="暂无工艺路线数据", validation_message="未加载工艺路线方案。")

    def _normalize_route_context(self, route_context: Dict[str, Any]) -> Dict[str, Any]:
        header = route_context.get("process_route_header")
        if not isinstance(header, dict):
            header = route_context.get("process_router_header")
        loops = route_context.get("process_route_loop_line")
        steps = route_context.get("process_route_loop_step_line")
        if not isinstance(steps, list):
            steps = route_context.get("process_route_loop_step")
        if not isinstance(header, dict):
            header = {}
        if not isinstance(loops, list):
            loops = []
        if not isinstance(steps, list):
            steps = []

        loops_out: List[Dict[str, Any]] = []
        for loop in loops:
            if not isinstance(loop, dict):
                continue
            item = dict(loop)
            item["loop_index"] = _to_int(item.get("loop_index"), 0)
            item["loop_count"] = _to_int(item.get("loop_count"), 1)
            loops_out.append(item)
        loops_out.sort(key=lambda item: (item.get("loop_index", 0), _text(item.get("loop_id"))))

        loop_index_map = {item.get("loop_id"): item.get("loop_index", 0) for item in loops_out}
        steps_out: List[Dict[str, Any]] = []
        for step in steps:
            if not isinstance(step, dict):
                continue
            item = dict(step)
            item["loop_index"] = _to_int(
                item.get("loop_index", loop_index_map.get(item.get("loop_id"), 0)),
                0,
            )
            item["node_index"] = _to_int(item.get("node_index"), 0)
            item["params"] = _normalize_params(item.get("params"))
            steps_out.append(item)
        steps_out.sort(
            key=lambda item: (
                item.get("loop_index", 0),
                item.get("node_index", 0),
                _text(item.get("node_id")),
            )
        )

        return {
            "process_route_header": dict(header),
            "process_route_loop_line": loops_out,
            "process_route_loop_step_line": steps_out,
        }

    def _is_locked(self) -> bool:
        return self.page_state["page_status"] in {"approved", "frozen", "locked"}

    def _mark_route_dirty(self) -> None:
        if self._is_locked():
            return
        if self.page_state["page_status"] == "validated":
            self.page_state["page_status"] = "created"
            self.page_state["current_route"]["process_route_header"]["status"] = "created"
        self.page_state["dirty"] = True

    def _current_node_ids(self) -> List[str]:
        steps = self.page_state["current_route"]["process_route_loop_step_line"]
        return [_text(step.get("node_id")).strip() for step in steps if _text(step.get("node_id")).strip()]

    def _build_graph(self) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[str]]:
        route = self.page_state["current_route"]
        header = route["process_route_header"]
        loops = route["process_route_loop_line"]
        steps = route["process_route_loop_step_line"]

        warnings: List[str] = []

        nodes: List[Dict[str, Any]] = []
        for step in steps:
            node_id = _text(step.get("node_id"))
            if not node_id:
                warnings.append("存在缺少 node_id 的节点，已跳过。")
                continue
            nodes.append(
                {
                    "node_id": node_id,
                    "loop_id": _text(step.get("loop_id")),
                    "loop_index": _to_int(step.get("loop_index"), 0),
                    "node_index": _to_int(step.get("node_index"), 0),
                    "node_type": _text(step.get("node_type")) or "NODE",
                    "instruction": _text(step.get("instruction")),
                    "params": step.get("params", {}),
                }
            )
        nodes.sort(key=lambda item: (item["loop_index"], item["node_index"], item["node_id"]))

        nodes_by_loop: Dict[str, List[Dict[str, Any]]] = {}
        for node in nodes:
            nodes_by_loop.setdefault(node["loop_id"], []).append(node)

        loop_order = [_text(loop.get("loop_id")) for loop in loops if _text(loop.get("loop_id"))]
        if not loop_order and nodes:
            loop_order = sorted({node["loop_id"] for node in nodes}, key=str)

        edges: List[Dict[str, Any]] = []

        for loop_id in loop_order:
            loop_nodes = nodes_by_loop.get(loop_id, [])
            loop_nodes.sort(key=lambda item: (item["node_index"], item["node_id"]))
            for first, second in zip(loop_nodes, loop_nodes[1:]):
                edges.append(
                    {
                        "source": first["node_id"],
                        "target": second["node_id"],
                        "edge_type": "forward",
                        "loop_id": loop_id,
                        "loop_count": None,
                    }
                )

        for current_loop, next_loop in zip(loop_order, loop_order[1:]):
            current_nodes = nodes_by_loop.get(current_loop, [])
            next_nodes = nodes_by_loop.get(next_loop, [])
            if current_nodes and next_nodes:
                edges.append(
                    {
                        "source": current_nodes[-1]["node_id"],
                        "target": next_nodes[0]["node_id"],
                        "edge_type": "forward",
                        "loop_id": current_loop,
                        "loop_count": None,
                    }
                )

        valid_node_ids = {node["node_id"] for node in nodes}
        loop_map = {_text(loop.get("loop_id")): loop for loop in loops if _text(loop.get("loop_id"))}

        for loop_id in loop_order:
            loop = loop_map.get(loop_id)
            if not loop:
                continue

            loop_nodes = nodes_by_loop.get(loop_id, [])
            if len(loop_nodes) <= 1:
                continue

            loop_count = _to_int(loop.get("loop_count"), 1)
            entry_node_id = _text(loop.get("entry_node_id"))
            exit_node_id = _text(loop.get("exit_node_id"))
            if entry_node_id in valid_node_ids and exit_node_id in valid_node_ids:
                edges.append(
                    {
                        "source": exit_node_id,
                        "target": entry_node_id,
                        "edge_type": "loop",
                        "loop_id": loop_id,
                        "loop_count": loop_count,
                        "loop_data": loop,
                    }
                )
            else:
                warnings.append(
                    f"循环 {loop_id} 的 entry_node_id 或 exit_node_id 无法匹配现有节点。"
                )

        if not header:
            warnings.append("未加载工艺路线头信息。")
        if not loops:
            warnings.append("未加载工艺路线 loop 信息。")
        if not steps:
            warnings.append("未加载工艺路线步骤信息。")
        return nodes, edges, warnings

    def _render_page(self, empty_message: str = "", validation_message: str = "") -> None:
        self._updating_widgets = True
        try:
            header = self.page_state["current_route"]["process_route_header"]
            self.txtBatchNo.setText(_text(header.get("lot_id")) or "—")
            self.txtRouteId.setText(_text(header.get("process_route_id")) or "—")
            self.txtRouteVer.setText(_text(header.get("process_route_version")) or "—")
            self.txtApprover.setText(_text(header.get("approved_by")) or "—")
            self.txtStatus.setText(_text(header.get("status")) or self.page_state["page_status"] or "—")
            self.txtConstraints.setPlainText(self._constraints_text())
            self._render_simulation_results()

            nodes, edges, warnings = self._build_graph()
            self._render_graph(nodes, edges, empty_message or ("暂无工艺路线数据" if not nodes else ""))
            message = validation_message or self._build_validation_text(warnings)
            self.txtValidationInfo.setPlainText(message)
            self.btnApprove.setEnabled(
                (not self.page_state["loading"]) and self.page_state["page_status"] == "validated"
            )
        finally:
            self._updating_widgets = False

    def _render_simulation_results(self) -> None:
        results = self.page_state["simulation"].get("simulation_results") or []
        self.tblSimulationResult.setRowCount(len(results))
        for row, item in enumerate(results):
            if not isinstance(item, dict):
                item = {"operation": _text(item)}
            values = [
                _text(item.get("operation") or item.get("step")),
                _text(item.get("start_time")),
                _text(item.get("end_time")),
                _text(item.get("duration")),
                _text(item.get("remark")),
            ]
            for column, value in enumerate(values):
                self.tblSimulationResult.setItem(row, column, QtWidgets.QTableWidgetItem(value))

    def _constraints_text(self) -> str:
        context = getattr(self.controller, "context", {}) or {}
        value = context.get("constraint_context")
        if self.page_state["dirty"] and not self._updating_widgets:
            return self.txtConstraints.toPlainText()
        if value in (None, ""):
            return "暂无产线约束信息。"
        if isinstance(value, dict):
            raw_text = _text(value.get("raw_text")).strip()
            if raw_text:
                return raw_text
        if isinstance(value, str):
            return value
        return _render_json(value)

    def _build_validation_text(self, warnings: List[str] | None = None) -> str:
        warnings = warnings or []
        summary = self.page_state["validation_summary"]
        lines: List[str] = []

        if self._is_locked():
            lines.append("方案已冻结")
        elif summary.get("passed"):
            lines.append("校验通过")
        elif summary.get("errors") or summary.get("risks"):
            lines.append("校验未通过")
        else:
            lines.append("尚未执行校验")

        errors = summary.get("errors") or []
        risks = summary.get("risks") or []
        if errors:
            lines.append("")
            lines.append("错误：")
            lines.extend(f"- {_text(item)}" for item in errors)
        if risks:
            lines.append("")
            lines.append("风险：")
            lines.extend(f"- {_text(item)}" for item in risks)
        if warnings:
            lines.append("")
            lines.append("提示：")
            lines.extend(f"- {item}" for item in warnings)
        return "\n".join(lines).strip()

    def _render_graph(self, nodes: List[Dict[str, Any]], edges: List[Dict[str, Any]], empty_message: str) -> None:
        scene = QtWidgets.QGraphicsScene(self)
        scene.setBackgroundBrush(QtGui.QBrush(QColor("#F8FAFC")))
        self._node_items = {}

        if not nodes:
            text_item = scene.addText(empty_message or "暂无工艺路线数据")
            text_item.setDefaultTextColor(QColor("#8C8C8C"))
            text_item.setPos(40, 40)
            self.graphicsDigitalTwin.setScene(scene)
            self._graph_scene_rect = scene.itemsBoundingRect()
            self._fit_graph_view()
            return

        ordered_nodes = sorted(
            nodes,
            key=lambda item: (item["loop_index"], item["node_index"], item["node_id"]),
        )

        positions: Dict[str, QRectF] = {}

        for index, node in enumerate(ordered_nodes):
            x = self.START_X + index * (self.NODE_W + self.NODE_GAP_X)
            rect = QRectF(x, self.BASE_Y, self.NODE_W, self.NODE_H)
            positions[node["node_id"]] = rect

        if positions:
            left = min(rect.left() for rect in positions.values()) - 120
            right = max(rect.right() for rect in positions.values()) + 120
            top = 32
            bottom = self.BASE_Y + self.NODE_H + 140
            self._draw_grid(scene, QRectF(left, top, right - left, bottom - top))

        for edge in edges:
            if edge["edge_type"] != "forward":
                continue
            src_rect = positions.get(edge["source"])
            tgt_rect = positions.get(edge["target"])
            if src_rect is None or tgt_rect is None:
                continue
            self._add_straight_edge(scene, src_rect, tgt_rect)

        for edge in edges:
            if edge["edge_type"] != "loop":
                continue
            src_rect = positions.get(edge["source"])
            tgt_rect = positions.get(edge["target"])
            if src_rect is None or tgt_rect is None:
                continue
            loop_data = edge.get("loop_data") or {}
            self._add_loop_edge(scene, src_rect, tgt_rect, loop_data)

        for node in ordered_nodes:
            rect = positions[node["node_id"]]
            item = RouteNodeItem(rect, node, self._open_node_editor, self._is_locked())
            scene.addItem(item)
            self._node_items[node["node_id"]] = item

        self.graphicsDigitalTwin.setScene(scene)
        scene_rect = scene.itemsBoundingRect().adjusted(-48, -48, 48, 48)
        scene.setSceneRect(scene_rect)
        self._graph_scene_rect = scene_rect
        self._fit_graph_view()

    def _draw_grid(self, scene: QtWidgets.QGraphicsScene, rect: QRectF) -> None:
        minor_step = 24
        major_step = 120
        minor_pen = QPen(QColor("#EDF2F7"), 1)
        major_pen = QPen(QColor("#E2E8F0"), 1)

        x = int(rect.left() // minor_step) * minor_step
        while x <= rect.right():
            pen = major_pen if x % major_step == 0 else minor_pen
            scene.addLine(x, rect.top(), x, rect.bottom(), pen).setZValue(0)
            x += minor_step

        y = int(rect.top() // minor_step) * minor_step
        while y <= rect.bottom():
            pen = major_pen if y % major_step == 0 else minor_pen
            scene.addLine(rect.left(), y, rect.right(), y, pen).setZValue(0)
            y += minor_step

    def _add_straight_edge(
        self,
        scene: QtWidgets.QGraphicsScene,
        src_rect: QRectF,
        tgt_rect: QRectF,
    ) -> None:
        p1 = QPointF(src_rect.right(), src_rect.center().y())
        p2 = QPointF(tgt_rect.left(), tgt_rect.center().y())
        line = QtWidgets.QGraphicsLineItem(p1.x(), p1.y(), p2.x(), p2.y())
        line.setPen(QPen(QColor("#64748B"), 2, Qt.SolidLine, Qt.RoundCap))
        line.setZValue(6)
        scene.addItem(line)
        self._draw_arrow_head(scene, p2, p2 - p1, QColor("#64748B"), z_value=7)

    def _add_loop_edge(
        self,
        scene: QtWidgets.QGraphicsScene,
        src_rect: QRectF,
        tgt_rect: QRectF,
        loop_data: Dict[str, Any],
    ) -> None:
        src_top = QPointF(src_rect.center().x(), src_rect.top())
        tgt_top = QPointF(tgt_rect.center().x(), tgt_rect.top())
        mid_y = min(src_top.y(), tgt_top.y()) - self.LOOP_LANE_HEIGHT

        path = QPainterPath(src_top)
        path.lineTo(src_top.x(), mid_y)
        path.lineTo(tgt_top.x(), mid_y)
        path.lineTo(tgt_top.x(), tgt_top.y())

        edge_item = LoopEdgeItem(path, loop_data, self._open_loop_editor, self._is_locked())
        scene.addItem(edge_item)

        loop_id = _text(loop_data.get("loop_id")).strip()
        loop_count = max(1, _to_int(loop_data.get("loop_count"), 1))
        label = f"{loop_id} x{loop_count}" if loop_id else f"x{loop_count}"
        label_item = QtWidgets.QGraphicsSimpleTextItem(label)
        label_font = label_item.font()
        label_font.setPointSize(10)
        label_font.setBold(True)
        label_item.setFont(label_font)
        label_item.setBrush(QtGui.QBrush(QColor("#B45309")))
        label_item.setZValue(9.5)
        label_rect = label_item.boundingRect()
        label_item.setPos(
            (src_top.x() + tgt_top.x()) / 2 - label_rect.width() / 2,
            mid_y - label_rect.height() - 8,
        )
        scene.addItem(label_item)

        self._draw_arrow_head(
            scene,
            tgt_top,
            QPointF(0, 1),
            QColor("#F59E0B"),
            z_value=9,
        )

    def _draw_arrow_head(
        self,
        scene: QtWidgets.QGraphicsScene,
        tip: QPointF,
        direction: QPointF,
        color: QColor,
        z_value: float = 10,
    ) -> None:
        length = (direction.x() ** 2 + direction.y() ** 2) ** 0.5
        if length == 0:
            return
        ux, uy = direction.x() / length, direction.y() / length
        size = 10.0
        perp_x, perp_y = -uy, ux
        left = QPointF(
            tip.x() - ux * size + perp_x * (size / 2),
            tip.y() - uy * size + perp_y * (size / 2),
        )
        right = QPointF(
            tip.x() - ux * size - perp_x * (size / 2),
            tip.y() - uy * size - perp_y * (size / 2),
        )
        polygon = QPolygonF([tip, left, right])
        item = scene.addPolygon(polygon, QPen(color), QtGui.QBrush(color))
        item.setZValue(z_value)

    def _open_node_editor(self, node: Dict[str, Any]) -> None:
        self.page_state["active_node_id"] = _text(node.get("node_id"))
        self.page_state["active_loop_id"] = _text(node.get("loop_id"))

        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle(f"编辑节点 {node.get('node_id')}")
        dialog.resize(680, 520)

        layout = QtWidgets.QVBoxLayout(dialog)

        form = QtWidgets.QFormLayout()
        node_id_label = QtWidgets.QLabel(_text(node.get("node_id")) or "—")
        loop_id_label = QtWidgets.QLabel(_text(node.get("loop_id")) or "—")
        form.addRow("节点ID", node_id_label)
        form.addRow("Loop ID", loop_id_label)
        layout.addLayout(form)

        instruction_label = QtWidgets.QLabel("Instruction / 指令")
        layout.addWidget(instruction_label)

        instruction_edit = QtWidgets.QTextEdit(dialog)
        instruction_edit.setPlainText(_text(node.get("instruction")))
        instruction_edit.setMinimumHeight(120)
        layout.addWidget(instruction_edit)

        params_label = QtWidgets.QLabel("Params (JSON)")
        layout.addWidget(params_label)

        params_edit = QtWidgets.QTextEdit(dialog)
        params_edit.setPlainText(_render_json(node.get("params", {})))
        params_edit.setMinimumHeight(220)
        layout.addWidget(params_edit)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Cancel | QtWidgets.QDialogButtonBox.Save,
            parent=dialog,
        )
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        def save() -> None:
            instruction = instruction_edit.toPlainText().strip()
            params_text = params_edit.toPlainText()

            try:
                params = _parse_params_text(params_text)
            except ValueError as exc:
                QMessageBox.warning(dialog, "编辑节点", str(exc))
                return

            updated = False
            for step in self.page_state["current_route"]["process_route_loop_step_line"]:
                if _text(step.get("node_id")) == _text(node.get("node_id")):
                    step["instruction"] = instruction
                    step["params"] = params
                    updated = True
                    break

            if not updated:
                QMessageBox.warning(dialog, "编辑节点", "未找到当前节点，无法保存修改。")
                return

            self.page_state["current_route"] = self._normalize_route_context(
                self.page_state["current_route"]
            )
            self._mark_route_dirty()
            self._sync_process_route_context()
            self._render_page()
            dialog.accept()

        buttons.accepted.connect(save)
        dialog.exec_()

    def _open_loop_editor(self, loop_data: Dict[str, Any]) -> None:
        if self._is_locked():
            QMessageBox.information(self, "编辑循环边", "当前工艺路线已冻结，无法编辑。")
            return

        self.page_state["active_loop_id"] = _text(loop_data.get("loop_id"))

        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle(f"编辑循环边 {loop_data.get('loop_id')}")
        dialog.resize(420, 260)
        layout = QtWidgets.QFormLayout(dialog)

        loop_id_label = QtWidgets.QLabel(_text(loop_data.get("loop_id")))
        loop_index_spin = QtWidgets.QSpinBox(dialog)
        loop_index_spin.setRange(0, 999)
        loop_index_spin.setValue(_to_int(loop_data.get("loop_index"), 0))

        entry_edit = QtWidgets.QLineEdit(_text(loop_data.get("entry_node_id")), dialog)
        exit_edit = QtWidgets.QLineEdit(_text(loop_data.get("exit_node_id")), dialog)

        loop_count_spin = QtWidgets.QSpinBox(dialog)
        loop_count_spin.setRange(1, 999)
        loop_count_spin.setValue(max(1, _to_int(loop_data.get("loop_count"), 1)))

        layout.addRow("Loop ID", loop_id_label)
        layout.addRow("Loop Index", loop_index_spin)
        layout.addRow("Entry Node", entry_edit)
        layout.addRow("Exit Node", exit_edit)
        layout.addRow("Loop Count", loop_count_spin)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Cancel | QtWidgets.QDialogButtonBox.Save,
            parent=dialog,
        )
        layout.addRow(buttons)
        buttons.rejected.connect(dialog.reject)

        def save() -> None:
            entry_node_id = entry_edit.text().strip()
            exit_node_id = exit_edit.text().strip()
            node_ids = set(self._current_node_ids())
            if not entry_node_id or entry_node_id not in node_ids:
                QMessageBox.warning(dialog, "编辑循环边", "Entry Node 必须是当前工艺路线中的有效节点。")
                return
            if not exit_node_id or exit_node_id not in node_ids:
                QMessageBox.warning(dialog, "编辑循环边", "Exit Node 必须是当前工艺路线中的有效节点。")
                return

            loop_id = _text(loop_data.get("loop_id"))
            for loop in self.page_state["current_route"]["process_route_loop_line"]:
                if _text(loop.get("loop_id")) != loop_id:
                    continue
                loop["loop_index"] = int(loop_index_spin.value())
                loop["entry_node_id"] = entry_node_id
                loop["exit_node_id"] = exit_node_id
                loop["loop_count"] = int(loop_count_spin.value())
                break

            self.page_state["current_route"] = self._normalize_route_context(
                self.page_state["current_route"]
            )
            self._mark_route_dirty()
            self._sync_process_route_context()
            self._render_page()
            dialog.accept()

        buttons.accepted.connect(save)
        dialog.exec_()

    def _collect_payload(self) -> Dict[str, Any]:
        self._update_constraints_context()
        route = self.page_state["current_route"]
        return {
            "process_route_header": dict(route["process_route_header"]),
            "process_route_loop_line": [dict(item) for item in route["process_route_loop_line"]],
            "process_route_loop_step_line": [dict(item) for item in route["process_route_loop_step_line"]],
        }

    def _sync_process_route_context(self) -> None:
        if not hasattr(self.controller, "context"):
            return
        self.controller.context["process_route_context"] = self._collect_payload()

    def _update_constraints_context(self) -> None:
        if not hasattr(self.controller, "context"):
            return
        header = self.page_state.get("current_route", {}).get("process_route_header", {})
        self.controller.context["constraint_context"] = build_constraint_context(
            header,
            self.txtConstraints.toPlainText(),
        )

    def _update_validation_summary(self, result: Dict[str, Any]) -> None:
        self.page_state["validation_summary"] = {
            "passed": bool(result.get("passed")),
            "errors": list(result.get("errors") or []),
            "risks": list(result.get("risks") or []),
        }

    def _on_import_route(self) -> None:
        try:
            routes = self.controller.backend.process_routes.list()
        except BackendError as exc:
            QMessageBox.warning(self, "版本库", f"读取历史工艺路线失败：{exc}")
            self.txtValidationInfo.setPlainText(f"读取历史工艺路线失败：{exc}")
            return

        dialog = ProcessRoutePickerDialog(routes, self)
        if not routes:
            QMessageBox.information(self, "版本库", "暂无历史工艺路线版本。")
        if dialog.exec_() != QtWidgets.QDialog.Accepted:
            return

        selected = dialog.selected_route()
        if not isinstance(selected, dict):
            return

        try:
            detail = self.controller.backend.process_routes.detail(
                _text(selected.get("process_route_id")),
                _to_int(selected.get("process_route_version"), 0),
            )
        except BackendError as exc:
            QMessageBox.warning(self, "版本库", f"加载工艺路线详情失败：{exc}")
            self.txtValidationInfo.setPlainText(f"加载工艺路线详情失败：{exc}")
            return

        self.page_state["current_route"] = self._normalize_route_context(detail)
        status = _text(self.page_state["current_route"]["process_route_header"].get("status")).strip().lower()
        self.page_state["page_status"] = status or "created"
        self.page_state["dirty"] = False
        self._sync_process_route_context()
        self._render_page()

    def _on_validate(self) -> None:
        if not self.page_state["current_route"]["process_route_loop_step_line"]:
            QMessageBox.information(self, "AI校验", "未加载工艺路线方案。")
            self.txtValidationInfo.setPlainText("未加载工艺路线方案。")
            return

        try:
            result = self.controller.backend.process_routes.validate(self._collect_payload())
        except BackendError as exc:
            QMessageBox.warning(self, "AI校验", f"工艺路线校验失败：{exc}")
            self.txtValidationInfo.setPlainText(f"工艺路线校验失败：{exc}")
            return

        self._update_validation_summary(result)
        self.page_state["page_status"] = "validated" if result.get("passed") else "created"
        self.page_state["current_route"]["process_route_header"]["status"] = self.page_state["page_status"]
        self._sync_process_route_context()
        self._render_page()

        message = (
            "工艺路线校验通过。该操作仅执行校验，不会写入数据库。"
            if result.get("passed")
            else "工艺路线校验未通过，请查看反馈。"
        )
        QMessageBox.information(self, "AI校验", message)

    def _on_approve(self) -> None:
        if self.page_state["page_status"] != "validated":
            QMessageBox.warning(self, "批准方案", "请先完成校验并确保校验通过。")
            return

        try:
            result = self.controller.backend.process_routes.approve(self._collect_payload())
        except BackendError as exc:
            QMessageBox.warning(self, "批准方案", f"批准失败：{exc}")
            self.txtValidationInfo.setPlainText(f"批准失败：{exc}")
            return

        self._update_validation_summary(result)
        if not result.get("passed"):
            self.page_state["page_status"] = "created"
            self._render_page()
            QMessageBox.warning(self, "批准方案", "方案批准失败，请检查校验反馈。")
            return

        process_route_id = _text(result.get("process_route_id")).strip()
        process_route_version = _to_int(result.get("process_route_version"), 0)
        if not process_route_id or process_route_version <= 0:
            QMessageBox.warning(
                self,
                "批准方案",
                "批准接口返回成功，但缺少有效的工艺路线ID或版本号，无法确认是否已落库。",
            )
            self.txtValidationInfo.setPlainText(
                "批准接口返回成功，但缺少有效的工艺路线ID或版本号，无法确认是否已落库。"
            )
            return

        try:
            persisted_route = self.controller.backend.process_routes.detail(
                process_route_id,
                process_route_version,
            )
        except BackendError as exc:
            QMessageBox.warning(
                self,
                "批准方案",
                f"批准接口已返回成功，但回查工艺路线详情失败，无法确认是否已落库：{exc}",
            )
            self.txtValidationInfo.setPlainText(
                f"批准接口已返回成功，但回查工艺路线详情失败，无法确认是否已落库：{exc}"
            )
            return

        self.page_state["current_route"] = self._normalize_route_context(persisted_route)
        header = self.page_state["current_route"]["process_route_header"]
        header["process_route_id"] = process_route_id
        header["process_route_version"] = process_route_version
        header["status"] = _text(result.get("status")).strip().lower() or _text(
            header.get("status")
        ).strip().lower() or "validated"
        self.page_state["page_status"] = _text(header.get("status")).strip().lower() or "validated"
        self.page_state["dirty"] = False
        self._sync_process_route_context()
        self._render_page()

        QMessageBox.information(
            self,
            "批准方案",
            (
                f"方案已批准并完成落库校验：{header.get('process_route_id')} "
                f"V{header.get('process_route_version')}。"
            ),
        )

    def _on_next(self) -> None:
        if self.page_state["page_status"] not in {"validated", "approved", "frozen", "locked"}:
            QMessageBox.warning(self, "下一步", "当前工艺路线未批准或未校验通过，无法进入下一步。")
            return

        self._sync_process_route_context()
        self.controller.context.setdefault("order_context", {})
        self.controller.context.setdefault("lot_context", {})
        self.controller.context.setdefault("process_plan_context", {})
        self.controller.context.setdefault("process_route_context", {})
        self.controller.context.setdefault("constraint_context", {})
        if not hasattr(self.controller, "show_page"):
            QMessageBox.critical(self, "下一步", "主窗口未提供页面切换能力。")
            return
        self.controller.show_page("prepare_page")

    def _on_constraints_changed(self) -> None:
        if self._updating_widgets:
            return
        if self._is_locked():
            return
        self._mark_route_dirty()
        self._update_constraints_context()

    def _on_weight_changed(self, value: int) -> None:
        efficiency = max(0.0, min(1.0, value / 100.0))
        self.page_state["objective_weight"] = {"efficiency": efficiency, "cost": 1.0 - efficiency}
        self.page_state["simulation"]["objective_weight"] = dict(self.page_state["objective_weight"])
