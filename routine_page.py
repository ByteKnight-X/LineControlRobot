from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

from PyQt5 import QtCore, QtGui, QtWidgets, uic
from PyQt5.QtCore import QPointF, QRectF, QSize, Qt
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


ROUTE_PRECAUTION_TEXT = """
1. 首检测信息
   -注意对准鞋头中心点及后跟部位变现；后跟要对接不可有高低
   -打底与上色均不可榨浆、溢色、麻面和沙眼等问题
   -油墨上色时注意看色卡
   -油墨烤干后效果不可薄于色卡
2. 环境控制
   -车间温度控制在 22-26℃，避免过高或过低导致油墨胶浆异常；湿度不可高于75%RH，避免静电吸盘异常
3. 异常处置
   -连续出现5双出现异常（榨浆、溢色、麻面、沙眼和色差）立即停机。
"""


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
        self.setZValue(26)

        hint = "已废弃" if locked else "双击编辑循环边"
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


class RotatedTabBar(QtWidgets.QTabBar):
    TAB_WIDTH = 48
    TAB_MIN_HEIGHT = 104

    def tabSizeHint(self, index: int) -> QSize:
        base_size = super().tabSizeHint(index)
        text = self.tabText(index)
        font = self.font()
        font.setBold(index == self.currentIndex())
        metrics = QtGui.QFontMetrics(font)
        text_height = metrics.horizontalAdvance(text) + 28
        height = max(self.TAB_MIN_HEIGHT, text_height, base_size.height())
        return QSize(self.TAB_WIDTH, height)

    def paintEvent(self, event) -> None:
        painter = QtWidgets.QStylePainter(self)
        for index in range(self.count()):
            option = QtWidgets.QStyleOptionTab()
            self.initStyleOption(option, index)
            text = option.text
            option.text = ""
            painter.drawControl(QtWidgets.QStyle.CE_TabBarTabShape, option)

            rect = self.tabRect(index)
            painter.save()
            painter.setClipRect(rect)
            painter.translate(rect.center())
            # painter.rotate(90)

            text_rect = QRectF(-rect.height() / 2, -rect.width() / 2, rect.height(), rect.width())
            color = QColor("#1890ff") if index == self.currentIndex() else QColor("#595959")
            if not (self.isTabEnabled(index)):
                color = QColor("#BFBFBF")
            font = painter.font()
            font.setBold(index == self.currentIndex())
            painter.setFont(font)
            painter.setPen(color)
            painter.drawText(text_rect, int(Qt.AlignCenter | Qt.TextWordWrap), text)
            painter.restore()


class NodeEditorDialog(QtWidgets.QDialog):
    FIELD_LABELS = {
        "speed_percent": "速度",
        "station": "站点",
        "temperature_c": "温度(℃)",
        "duration_s": "时长(秒)",
        "remark": "备注",
        "weight_kg": "重量(kg)",
        "mesh_index": "网版索引号",
        "process_plan_id": "网版ID",
        "process_plan_version": "版本号",
        "custom_flag": "自定义标记",
    }

    def __init__(
        self,
        node: Dict[str, Any],
        locked: bool,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._node = dict(node)
        self._locked = locked
        self._params = dict(node.get("params") or {})
        self._edited_payload: Dict[str, Any] | None = None
        self._tables: Dict[str, QtWidgets.QTableWidget] = {}
        self._instruction_edit: QtWidgets.QTextEdit | None = None
        self._tabs: QtWidgets.QTabWidget | None = None
        self.setWindowTitle(f"编辑节点 {node.get('node_id')}")
        self.resize(900, 680)
        self._apply_styles()
        self._build_ui()

    def result_payload(self) -> Dict[str, Any]:
        return dict(self._edited_payload or {})

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            """
            QDialog { background-color: #f5f7fa; }
            QLabel { color: #262626; }
            QLabel[role="caption"] { color: #8c8c8c; font-size: 12px; }
            QFrame[card="true"] {
                background: #ffffff;
                border: 1px solid #f0f0f0;
                border-radius: 8px;
            }
            QFrame[infoCard="true"] {
                background: #fafafa;
                border: 1px solid #f0f0f0;
                border-radius: 8px;
            }
            QTextEdit, QTableWidget {
                background: #ffffff;
                border: 1px solid #d9d9d9;
                border-radius: 6px;
                color: #262626;
                gridline-color: #f0f0f0;
            }
            QTextEdit { padding: 8px; }
            QHeaderView::section {
                background: #fafafa;
                color: #595959;
                border: none;
                border-bottom: 1px solid #f0f0f0;
                padding: 6px 8px;
                font-weight: 600;
            }
            QTableWidget::item {
                padding: 6px 8px;
                border-bottom: 1px solid #f5f5f5;
            }
            QTableWidget::item:selected {
                background: #e6f7ff;
                color: #1890ff;
            }
            QTabWidget::pane {
                border: 1px solid #f0f0f0;
                background: #ffffff;
                border-radius: 8px;
                margin-left: 6px;
            }
            QTabBar::tab {
                background: #fafafa;
                color: #595959;
                border: 1px solid #f0f0f0;
                border-right: none;
                border-top-left-radius: 6px;
                border-bottom-left-radius: 6px;
                padding: 0px;
                margin: 4px 0;
                min-width: 48px;
                min-height: 104px;
            }
            QTabBar::tab:selected {
                background: #e6f7ff;
                color: #1890ff;
                border-color: #91d5ff;
                font-weight: 600;
            }
            QPushButton {
                min-width: 88px;
                min-height: 34px;
                border-radius: 6px;
                padding: 0 16px;
            }
            """
        )

    def _build_ui(self) -> None:
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(16)

        info_card = QtWidgets.QFrame(self)
        info_card.setProperty("card", True)
        info_layout = QtWidgets.QGridLayout(info_card)
        info_layout.setContentsMargins(16, 14, 16, 14)
        info_layout.setHorizontalSpacing(0)
        info_layout.setVerticalSpacing(8)

        title = QtWidgets.QLabel("节点详情")
        title.setStyleSheet("font-size: 16px; font-weight: 600; color: #262626;")
        info_layout.addWidget(title, 0, 0, 1, 3)
        info_cards = self._build_info_cards()
        info_layout.addLayout(info_cards, 1, 0, 1, 3)
        root.addWidget(info_card)

        instruction_card = QtWidgets.QFrame(self)
        instruction_card.setProperty("card", True)
        instruction_layout = QtWidgets.QVBoxLayout(instruction_card)
        instruction_layout.setContentsMargins(16, 14, 16, 14)
        instruction_layout.setSpacing(8)
        instruction_title = QtWidgets.QLabel("工艺指令")
        instruction_title.setStyleSheet("font-size: 14px; font-weight: 600;")
        instruction_layout.addWidget(instruction_title)
        self._instruction_edit = QtWidgets.QTextEdit(self)
        self._instruction_edit.setPlainText(_text(self._node.get("instruction")))
        self._instruction_edit.setMinimumHeight(110)
        self._instruction_edit.setReadOnly(self._locked)
        instruction_layout.addWidget(self._instruction_edit)
        root.addWidget(instruction_card)

        param_card = QtWidgets.QFrame(self)
        param_card.setProperty("card", True)
        param_layout = QtWidgets.QVBoxLayout(param_card)
        param_layout.setContentsMargins(16, 14, 16, 14)
        param_layout.setSpacing(8)
        param_title = QtWidgets.QLabel("参数设置")
        param_title.setStyleSheet("font-size: 14px; font-weight: 600;")
        param_layout.addWidget(param_title)
        self._tabs = QtWidgets.QTabWidget(self)
        self._tabs.setTabBar(RotatedTabBar(self._tabs))
        self._tabs.setTabPosition(QtWidgets.QTabWidget.West)
        self._tabs.tabBar().setExpanding(False)
        self._tabs.tabBar().setUsesScrollButtons(False)
        param_layout.addWidget(self._tabs)
        self._build_param_tabs()
        root.addWidget(param_card, 1)

        buttons = QtWidgets.QDialogButtonBox(parent=self)
        save_button = buttons.addButton("保存", QtWidgets.QDialogButtonBox.AcceptRole)
        cancel_button = buttons.addButton("取消", QtWidgets.QDialogButtonBox.RejectRole)
        save_button.setStyleSheet(
            "background:#1890ff; color:#ffffff; border:1px solid #1890ff; font-weight:600;"
        )
        cancel_button.setStyleSheet(
            "background:#ffffff; color:#595959; border:1px solid #d9d9d9;"
        )
        save_button.setEnabled(not self._locked)
        buttons.accepted.connect(self._handle_accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _build_info_cards(self) -> QtWidgets.QHBoxLayout:
        layout = QtWidgets.QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        items = [
            ("节点编号", _text(self._node.get("node_id")) or "—"),
            ("循环编号", _text(self._node.get("loop_id")) or "—"),
            ("节点类型", self._node_type_name()),
        ]
        for title, value in items:
            layout.addWidget(self._create_info_card(title, value), 1)
        return layout

    def _create_info_card(self, title: str, value: str) -> QtWidgets.QFrame:
        card = QtWidgets.QFrame(self)
        card.setProperty("infoCard", True)
        card.setMinimumHeight(74)
        layout = QtWidgets.QVBoxLayout(card)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(4)
        caption = QtWidgets.QLabel(title, card)
        caption.setProperty("role", "caption")
        body = QtWidgets.QLabel(value, card)
        body.setWordWrap(True)
        body.setStyleSheet("font-size: 15px; font-weight: 600; color: #262626;")
        layout.addWidget(caption)
        layout.addWidget(body)
        layout.addStretch(1)
        return card

    def _node_type_name(self) -> str:
        node_type = _text(self._node.get("node_type")).strip().lower()
        mapping = {
            "loader": "上料工作站",
            "printer": "丝印工作站",
            "dryer": "烘干机",
        }
        return mapping.get(node_type, _text(self._node.get("node_type")) or "未知节点")

    def _build_param_tabs(self) -> None:
        if self._tabs is None:
            return
        node_type = _text(self._node.get("node_type")).strip().lower()
        if node_type == "loader":
            self._build_loader_tabs()
        elif node_type == "printer":
            self._build_printer_tabs()
        else:
            self._build_generic_tabs(self._params)

    def _create_tab_page(self, title: str) -> QtWidgets.QWidget:
        page = QtWidgets.QWidget(self)
        layout = QtWidgets.QVBoxLayout(page)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)
        if self._tabs is not None:
            self._tabs.addTab(page, title)
            index = self._tabs.indexOf(page)
            self._tabs.tabBar().setTabToolTip(index, title)
        return page

    def _create_table(self, column_titles: List[str], object_name: str) -> QtWidgets.QTableWidget:
        table = QtWidgets.QTableWidget(self)
        table.setObjectName(object_name)
        table.setColumnCount(len(column_titles))
        table.setHorizontalHeaderLabels(column_titles)
        table.verticalHeader().setVisible(False)
        table.setAlternatingRowColors(False)
        table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectItems)
        table.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        table.horizontalHeader().setStretchLastSection(True)
        table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Stretch)
        table.setEditTriggers(
            QtWidgets.QAbstractItemView.NoEditTriggers
            if self._locked
            else QtWidgets.QAbstractItemView.DoubleClicked
            | QtWidgets.QAbstractItemView.SelectedClicked
            | QtWidgets.QAbstractItemView.EditKeyPressed
        )
        self._tables[object_name] = table
        return table

    def _set_table_item(self, table: QtWidgets.QTableWidget, row: int, col: int, value: Any) -> None:
        item = QtWidgets.QTableWidgetItem("" if value is None else str(value))
        table.setItem(row, col, item)

    def _fill_key_value_table(self, table: QtWidgets.QTableWidget, rows: List[Tuple[Any, ...]]) -> None:
        table.setRowCount(len(rows))
        for row, row_data in enumerate(rows):
            if len(row_data) == 3:
                label, actual_key, value = row_data
            else:
                label, value = row_data
                actual_key = None
            self._set_table_item(table, row, 0, label)
            self._set_table_item(table, row, 1, value)
            label_item = table.item(row, 0)
            if label_item is not None:
                if actual_key is not None:
                    label_item.setData(Qt.UserRole, actual_key)
                label_item.setFlags(label_item.flags() & ~Qt.ItemIsEditable)

    def _build_loader_tabs(self) -> None:
        arm_page = self._create_tab_page("机械臂参数")
        arm_layout = arm_page.layout()
        arm_table = self._create_table(["参数项", "参数值"], "loader_arm")
        self._fill_key_value_table(
            arm_table,
            [("速度", "speed_percent", self._params.get("speed_percent", ""))],
        )
        arm_layout.addWidget(arm_table)

        target_page = self._create_tab_page("目标位置")
        target_layout = target_page.layout()
        target_table = self._create_table(["序号", "X", "Y", "Z", "R"], "loader_targets")
        target_positions = self._params.get("target_positions") or []
        if not isinstance(target_positions, list):
            target_positions = []
        target_table.setRowCount(max(len(target_positions), 1))
        for row, values in enumerate(target_positions):
            seq_item = QtWidgets.QTableWidgetItem(str(row + 1))
            seq_item.setFlags(seq_item.flags() & ~Qt.ItemIsEditable)
            target_table.setItem(row, 0, seq_item)
            values = values if isinstance(values, list) else []
            for col in range(4):
                self._set_table_item(target_table, row, col + 1, values[col] if col < len(values) else "")
        if target_table.rowCount() == 1 and target_table.item(0, 0) is None:
            seq_item = QtWidgets.QTableWidgetItem("1")
            seq_item.setFlags(seq_item.flags() & ~Qt.ItemIsEditable)
            target_table.setItem(0, 0, seq_item)
        target_layout.addWidget(target_table)
        target_hint = QtWidgets.QLabel("每行表示一个目标点，依次填写 X、Y、Z、R。")
        target_hint.setProperty("role", "caption")
        target_layout.addWidget(target_hint)

        extra = {k: v for k, v in self._params.items() if k not in {"speed_percent", "target_positions"}}
        if extra:
            self._build_generic_tabs(extra, "其他参数")

    def _build_printer_tabs(self) -> None:
        scraper_page = self._create_tab_page("刮刀")
        scraper_layout = scraper_page.layout()
        scraper_table = self._create_table(["参数项", "参数值"], "printer_scraper")
        print_range = self._params.get("print_range_mm") or []
        if not isinstance(print_range, list):
            print_range = []
        scraper_rows = [
            ("角度", self._params.get("squeegee_angle_deg", "")),
            ("速度", self._params.get("squeegee_speed_mps", "")),
            ("行程起点", print_range[0] if len(print_range) > 0 else ""),
            ("行程终点", print_range[1] if len(print_range) > 1 else ""),
            ("间距", self._params.get("spacing_mm", "")),
            ("压缩量", self._params.get("compression_mm", "")),
            ("刮印模式", self._params.get("print_mode", "")),
        ]
        self._fill_key_value_table(scraper_table, scraper_rows)
        scraper_layout.addWidget(scraper_table)

        ink_page = self._create_tab_page("印料")
        ink_layout = ink_page.layout()
        ink = self._params.get("ink") or {}
        if not isinstance(ink, dict):
            ink = {}
        ink_base_table = self._create_table(["参数项", "参数值"], "printer_ink_base")
        self._fill_key_value_table(ink_base_table, [("重量(kg)", ink.get("weight_kg", ""))])
        ink_layout.addWidget(ink_base_table)
        ingredients_title = QtWidgets.QLabel("配方组成")
        ingredients_title.setStyleSheet("font-size: 13px; font-weight: 600;")
        ink_layout.addWidget(ingredients_title)
        ingredients_table = self._create_table(["材料名称", "比例"], "printer_ink_ingredients")
        ingredients = ink.get("ingredients") or {}
        if not isinstance(ingredients, dict):
            ingredients = {}
        ingredient_rows = list(ingredients.items()) or [("", "")]
        ingredients_table.setRowCount(len(ingredient_rows))
        for row, (key, value) in enumerate(ingredient_rows):
            self._set_table_item(ingredients_table, row, 0, key)
            self._set_table_item(ingredients_table, row, 1, value)
        ink_layout.addWidget(ingredients_table)

        mesh_page = self._create_tab_page("网版")
        mesh_layout = mesh_page.layout()
        mesh = self._params.get("mesh") or {}
        if not isinstance(mesh, dict):
            mesh = {}
        mesh_table = self._create_table(["参数项", "参数值"], "printer_mesh")
        self._fill_key_value_table(
            mesh_table,
            [
                ("网版索引号", "mesh_index", mesh.get("mesh_index", "")),
                ("网版ID", "process_plan_id", mesh.get("process_plan_id", "")),
                ("版本号", "process_plan_version", mesh.get("process_plan_version", "")),
            ],
        )
        mesh_layout.addWidget(mesh_table)

        extra = {
            k: v
            for k, v in self._params.items()
            if k
            not in {
                "squeegee_angle_deg",
                "squeegee_speed_mps",
                "print_range_mm",
                "spacing_mm",
                "compression_mm",
                "print_mode",
                "ink",
                "mesh",
            }
        }
        if extra:
            self._build_generic_tabs(extra, "其他参数")

    def _build_generic_tabs(self, params: Dict[str, Any], first_title: str = "参数") -> None:
        scalar_rows: List[Tuple[str, Any]] = []
        dict_items: List[Tuple[str, Dict[str, Any]]] = []
        list_items: List[Tuple[str, List[Any]]] = []
        for key, value in params.items():
            if isinstance(value, dict):
                dict_items.append((key, value))
            elif isinstance(value, list):
                list_items.append((key, value))
            else:
                scalar_rows.append((self._field_label(key), value))

        if scalar_rows:
            page = self._create_tab_page(first_title)
            table = self._create_table(["参数项", "参数值"], f"generic_scalar_{len(self._tables)}")
            self._fill_key_value_table(table, [(label, key, value) for key, (label, value) in zip([k for k, v in params.items() if not isinstance(v, (dict, list))], scalar_rows)])
            page.layout().addWidget(table)

        for key, value in dict_items:
            page = self._create_tab_page(self._field_label(key))
            table = self._create_table(["参数项", "参数值"], f"generic_dict_{key}")
            self._fill_key_value_table(
                table,
                [(self._field_label(sub_key), sub_key, sub_value) for sub_key, sub_value in value.items()],
            )
            page.layout().addWidget(table)

        for key, value in list_items:
            page = self._create_tab_page(self._field_label(key))
            if value and all(isinstance(item, list) for item in value):
                width = max((len(item) for item in value if isinstance(item, list)), default=0)
                headers = ["序号"] + [f"值{index + 1}" for index in range(width)]
                table = self._create_table(headers, f"generic_list_{key}")
                table.setRowCount(len(value))
                for row, item in enumerate(value):
                    seq_item = QtWidgets.QTableWidgetItem(str(row + 1))
                    seq_item.setFlags(seq_item.flags() & ~Qt.ItemIsEditable)
                    table.setItem(row, 0, seq_item)
                    for col in range(width):
                        self._set_table_item(table, row, col + 1, item[col] if col < len(item) else "")
            else:
                table = self._create_table(["序号", "参数值"], f"generic_list_{key}")
                rows = value or [""]
                table.setRowCount(len(rows))
                for row, item in enumerate(rows):
                    seq_item = QtWidgets.QTableWidgetItem(str(row + 1))
                    seq_item.setFlags(seq_item.flags() & ~Qt.ItemIsEditable)
                    table.setItem(row, 0, seq_item)
                    self._set_table_item(table, row, 1, item)
            page.layout().addWidget(table)

    def _field_label(self, key: str) -> str:
        if key in self.FIELD_LABELS:
            return self.FIELD_LABELS[key]
        if key.endswith("_id"):
            return "编号"
        if key.endswith("_version"):
            return "版本号"
        return "参数项"

    def _convert_value(self, text: str, original: Any = None) -> Any:
        stripped = text.strip()
        if stripped == "":
            return "" if original not in (None, []) else original if isinstance(original, list) else ""
        if isinstance(original, int) and not isinstance(original, bool):
            try:
                return int(float(stripped))
            except ValueError:
                return stripped
        if isinstance(original, float):
            try:
                return float(stripped)
            except ValueError:
                return stripped
        try:
            if "." in stripped:
                return float(stripped)
            return int(stripped)
        except ValueError:
            return stripped

    def _read_key_value_table(
        self,
        table: QtWidgets.QTableWidget | None,
        originals: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        data: Dict[str, Any] = {}
        if table is None:
            return data
        originals = originals or {}
        for row in range(table.rowCount()):
            key_item = table.item(row, 0)
            value_item = table.item(row, 1)
            key = _text(key_item.text() if key_item else "").strip()
            if not key:
                continue
            reverse_key = _text(key_item.data(Qt.UserRole) if key_item else "").strip() or self._reverse_field_key(key, originals)
            original = originals.get(reverse_key)
            data[reverse_key] = self._convert_value(_text(value_item.text() if value_item else ""), original)
        return data

    def _reverse_field_key(self, label: str, originals: Dict[str, Any]) -> str:
        for key in originals:
            if self._field_label(key) == label:
                return key
        reverse_fixed = {value: key for key, value in self.FIELD_LABELS.items()}
        return reverse_fixed.get(label, label.replace(" ", "_"))

    def _collect_loader_params(self) -> Dict[str, Any]:
        params = dict(self._params)
        arm = self._read_key_value_table(self._tables.get("loader_arm"), {"speed_percent": self._params.get("speed_percent", "")})
        speed = arm.get("speed_percent", arm.get("速度", ""))
        if str(speed).strip() == "":
            raise ValueError("速度不能为空。")
        params["speed_percent"] = self._convert_value(str(speed), self._params.get("speed_percent", 0))

        target_table = self._tables.get("loader_targets")
        positions: List[List[Any]] = []
        if target_table is not None:
            for row in range(target_table.rowCount()):
                values = []
                raw_values = []
                for col in range(1, 5):
                    item = target_table.item(row, col)
                    text = _text(item.text() if item else "").strip()
                    raw_values.append(text)
                if not any(raw_values):
                    continue
                if any(value == "" for value in raw_values):
                    raise ValueError(f"目标位置第 {row + 1} 行缺少坐标值。")
                for col, text in enumerate(raw_values):
                    values.append(self._convert_value(text, 0.0))
                positions.append(values)
        params["target_positions"] = positions

        extra = self._collect_generic_params(prefix="generic_")
        params.update(extra)
        return params

    def _collect_printer_params(self) -> Dict[str, Any]:
        params = dict(self._params)
        scraper_originals = {
            "squeegee_angle_deg": self._params.get("squeegee_angle_deg", 0),
            "squeegee_speed_mps": self._params.get("squeegee_speed_mps", 0.0),
            "行程起点": "",
            "行程终点": "",
            "spacing_mm": self._params.get("spacing_mm", 0),
            "compression_mm": self._params.get("compression_mm", 0),
            "print_mode": self._params.get("print_mode", ""),
        }
        scraper_data = self._read_key_value_table(self._tables.get("printer_scraper"), scraper_originals)
        params["squeegee_angle_deg"] = self._convert_value(str(scraper_data.get("squeegee_angle_deg", "")), self._params.get("squeegee_angle_deg", 0))
        params["squeegee_speed_mps"] = self._convert_value(str(scraper_data.get("squeegee_speed_mps", "")), self._params.get("squeegee_speed_mps", 0.0))
        start = scraper_data.get("行程起点", "")
        end = scraper_data.get("行程终点", "")
        if str(start).strip() == "" or str(end).strip() == "":
            raise ValueError("行程起点和行程终点不能为空。")
        params["print_range_mm"] = [
            self._convert_value(str(start), 0.0),
            self._convert_value(str(end), 0.0),
        ]
        params["spacing_mm"] = self._convert_value(str(scraper_data.get("spacing_mm", "")), self._params.get("spacing_mm", 0))
        params["compression_mm"] = self._convert_value(str(scraper_data.get("compression_mm", "")), self._params.get("compression_mm", 0))
        params["print_mode"] = _text(scraper_data.get("print_mode", "")).strip()

        ink = dict(self._params.get("ink") or {})
        ink_base = self._read_key_value_table(self._tables.get("printer_ink_base"), {"weight_kg": ink.get("weight_kg", 0)})
        ink["weight_kg"] = self._convert_value(str(ink_base.get("weight_kg", ink_base.get("重量(kg)", ""))), ink.get("weight_kg", 0))
        ingredients_table = self._tables.get("printer_ink_ingredients")
        ingredients: Dict[str, Any] = {}
        if ingredients_table is not None:
            for row in range(ingredients_table.rowCount()):
                name_item = ingredients_table.item(row, 0)
                ratio_item = ingredients_table.item(row, 1)
                name = _text(name_item.text() if name_item else "").strip()
                ratio = _text(ratio_item.text() if ratio_item else "").strip()
                if not name and not ratio:
                    continue
                if not name:
                    raise ValueError("印料配方中存在空的材料名称。")
                ingredients[name] = self._convert_value(ratio, 0.0)
        ink["ingredients"] = ingredients
        params["ink"] = ink

        mesh_originals = dict(self._params.get("mesh") or {})
        params["mesh"] = self._read_key_value_table(self._tables.get("printer_mesh"), mesh_originals)
        extra = self._collect_generic_params(prefix="generic_")
        params.update(extra)
        return params

    def _collect_generic_params(self, prefix: str = "generic_") -> Dict[str, Any]:
        data: Dict[str, Any] = {}
        for name, table in self._tables.items():
            if not name.startswith(prefix):
                continue
            if name.startswith("generic_scalar_"):
                data.update(self._read_key_value_table(table, self._params))
            elif name.startswith("generic_dict_"):
                key = name[len("generic_dict_") :]
                original = self._params.get(key) if isinstance(self._params.get(key), dict) else {}
                data[key] = self._read_key_value_table(table, original)
            elif name.startswith("generic_list_"):
                key = name[len("generic_list_") :]
                original = self._params.get(key) if isinstance(self._params.get(key), list) else []
                rows: List[Any] = []
                for row in range(table.rowCount()):
                    row_values = []
                    for col in range(1, table.columnCount()):
                        item = table.item(row, col)
                        text = _text(item.text() if item else "").strip()
                        row_values.append(text)
                    if not any(row_values):
                        continue
                    if table.columnCount() == 2:
                        base_original = original[row] if row < len(original) else ""
                        rows.append(self._convert_value(row_values[0], base_original))
                    else:
                        base_original = original[row] if row < len(original) and isinstance(original[row], list) else []
                        parsed_row = []
                        for index, text in enumerate(row_values):
                            original_value = base_original[index] if index < len(base_original) else ""
                            parsed_row.append(self._convert_value(text, original_value))
                        rows.append(parsed_row)
                data[key] = rows
        return data

    def _collect_params(self) -> Dict[str, Any]:
        node_type = _text(self._node.get("node_type")).strip().lower()
        if node_type == "loader":
            return self._collect_loader_params()
        if node_type == "printer":
            return self._collect_printer_params()
        return self._collect_generic_params(prefix="generic_")

    def _handle_accept(self) -> None:
        if self._locked:
            self.reject()
            return
        instruction = self._instruction_edit.toPlainText().strip() if self._instruction_edit else ""
        try:
            params = self._collect_params()
        except ValueError as exc:
            QMessageBox.warning(self, "编辑节点", str(exc))
            return
        self._edited_payload = {"instruction": instruction, "params": params}
        self.accept()


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
    NODE_GAP_Y = 112
    MAX_NODES_PER_ROW = 10
    START_X = 64
    BASE_Y = 184
    LOOP_LANE_HEIGHT = 84
    LOOP_LANE_GAP = 28
    LOOP_SIDE_MARGIN = 40

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
        self.txtPrecaution.textChanged.connect(self._on_precaution_changed)
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
        return self.page_state["page_status"] == "obsolete"

    def _has_loaded_route(self) -> bool:
        route = self.page_state.get("current_route") or {}
        header = route.get("process_route_header") or {}
        loops = route.get("process_route_loop_line") or []
        steps = route.get("process_route_loop_step_line") or []
        return bool(header or loops or steps)

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
            self.txtPrecaution.setReadOnly(not self._has_loaded_route())
            self.txtPrecaution.setPlainText(self._precaution_text())
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

    def _precaution_text(self) -> str:
        if not self._has_loaded_route():
            return ""
        return ROUTE_PRECAUTION_TEXT

    def _build_validation_text(self, warnings: List[str] | None = None) -> str:
        warnings = warnings or []
        summary = self.page_state["validation_summary"]
        lines: List[str] = []

        if self._is_locked():
            lines.append("方案已废弃")
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

        positions, node_row_col = self._compute_snake_positions(ordered_nodes)

        if positions:
            loop_count = sum(1 for edge in edges if edge["edge_type"] == "loop")
            left = min(rect.left() for rect in positions.values()) - 120
            right = max(rect.right() for rect in positions.values()) + 120
            loop_left, loop_right = self._loop_side_bounds(edges, positions, node_row_col)
            if loop_left is not None:
                left = min(left, loop_left - 80)
            if loop_right is not None:
                right = max(right, loop_right + 80)
            top = min(rect.top() for rect in positions.values()) - 120
            top -= self.LOOP_LANE_HEIGHT + max(0, loop_count - 1) * self.LOOP_LANE_GAP
            bottom = max(rect.bottom() for rect in positions.values()) + 140
            loop_bottom = self._loop_bottom_bound(edges, positions, node_row_col)
            if loop_bottom is not None:
                bottom = max(bottom, loop_bottom + 80)
            self._draw_grid(scene, QRectF(left, top, right - left, bottom - top))

        for edge in edges:
            if edge["edge_type"] != "forward":
                continue
            src_rect = positions.get(edge["source"])
            tgt_rect = positions.get(edge["target"])
            if src_rect is None or tgt_rect is None:
                continue
            src_meta = node_row_col.get(edge["source"])
            tgt_meta = node_row_col.get(edge["target"])
            if src_meta is None or tgt_meta is None:
                continue
            self._add_forward_edge(scene, src_rect, tgt_rect, src_meta[0], tgt_meta[0])

        loop_lane_index = 0
        for edge in edges:
            if edge["edge_type"] != "loop":
                continue
            src_rect = positions.get(edge["source"])
            tgt_rect = positions.get(edge["target"])
            if src_rect is None or tgt_rect is None:
                continue
            loop_data = edge.get("loop_data") or {}
            src_meta = node_row_col.get(edge["source"])
            tgt_meta = node_row_col.get(edge["target"])
            src_row = src_meta[0] if src_meta else 0
            tgt_row = tgt_meta[0] if tgt_meta else 0
            self._add_loop_edge(scene, src_rect, tgt_rect, loop_data, loop_lane_index, src_row, tgt_row)
            loop_lane_index += 1

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

    def _compute_snake_positions(
        self,
        ordered_nodes: List[Dict[str, Any]],
    ) -> Tuple[Dict[str, QRectF], Dict[str, Tuple[int, int]]]:
        positions: Dict[str, QRectF] = {}
        node_row_col: Dict[str, Tuple[int, int]] = {}
        step_x = self.NODE_W + self.NODE_GAP_X
        step_y = self.NODE_H + self.NODE_GAP_Y

        for index, node in enumerate(ordered_nodes):
            row = index // self.MAX_NODES_PER_ROW
            col_in_row = index % self.MAX_NODES_PER_ROW
            visual_col = (
                col_in_row
                if row % 2 == 0
                else self.MAX_NODES_PER_ROW - 1 - col_in_row
            )
            x = self.START_X + visual_col * step_x
            y = self.BASE_Y + row * step_y
            positions[node["node_id"]] = QRectF(x, y, self.NODE_W, self.NODE_H)
            node_row_col[node["node_id"]] = (row, visual_col)

        return positions, node_row_col

    def _classify_loop_route(self, src_row: int, tgt_row: int) -> str:
        if src_row == tgt_row:
            return "top_lane" if src_row == 0 else "bottom_lane"
        return "side_lane_right" if min(src_row, tgt_row) % 2 == 0 else "side_lane_left"

    def _loop_anchor_point(self, rect: QRectF, anchor: str) -> QPointF:
        if anchor == "right":
            return QPointF(rect.right(), rect.center().y())
        if anchor == "left":
            return QPointF(rect.left(), rect.center().y())
        if anchor == "bottom":
            return QPointF(rect.center().x(), rect.bottom())
        return QPointF(rect.center().x(), rect.top())

    def _build_side_loop_path(
        self,
        src_anchor: QPointF,
        tgt_anchor: QPointF,
        outer_x: float,
    ) -> QPainterPath:
        path = QPainterPath(src_anchor)
        path.lineTo(outer_x, src_anchor.y())
        path.lineTo(outer_x, tgt_anchor.y())
        path.lineTo(tgt_anchor)
        return path

    def _loop_side_bounds(
        self,
        edges: List[Dict[str, Any]],
        positions: Dict[str, QRectF],
        node_row_col: Dict[str, Tuple[int, int]],
    ) -> Tuple[float | None, float | None]:
        left_bound: float | None = None
        right_bound: float | None = None
        loop_lane_index = 0
        for edge in edges:
            if edge.get("edge_type") != "loop":
                continue
            src_rect = positions.get(edge["source"])
            tgt_rect = positions.get(edge["target"])
            src_meta = node_row_col.get(edge["source"])
            tgt_meta = node_row_col.get(edge["target"])
            if src_rect is None or tgt_rect is None or src_meta is None or tgt_meta is None:
                continue
            route_type = self._classify_loop_route(src_meta[0], tgt_meta[0])
            lane_offset = loop_lane_index * self.LOOP_LANE_GAP
            if route_type == "side_lane_right":
                bound = max(src_rect.right(), tgt_rect.right()) + self.LOOP_SIDE_MARGIN + lane_offset
                right_bound = bound if right_bound is None else max(right_bound, bound)
            elif route_type == "side_lane_left":
                bound = min(src_rect.left(), tgt_rect.left()) - self.LOOP_SIDE_MARGIN - lane_offset
                left_bound = bound if left_bound is None else min(left_bound, bound)
            loop_lane_index += 1
        return left_bound, right_bound

    def _loop_bottom_bound(
        self,
        edges: List[Dict[str, Any]],
        positions: Dict[str, QRectF],
        node_row_col: Dict[str, Tuple[int, int]],
    ) -> float | None:
        bottom_bound: float | None = None
        loop_lane_index = 0
        for edge in edges:
            if edge.get("edge_type") != "loop":
                continue
            src_rect = positions.get(edge["source"])
            tgt_rect = positions.get(edge["target"])
            src_meta = node_row_col.get(edge["source"])
            tgt_meta = node_row_col.get(edge["target"])
            if src_rect is None or tgt_rect is None or src_meta is None or tgt_meta is None:
                continue
            route_type = self._classify_loop_route(src_meta[0], tgt_meta[0])
            if route_type == "bottom_lane":
                lane_offset = loop_lane_index * self.LOOP_LANE_GAP
                bound = max(src_rect.bottom(), tgt_rect.bottom()) + self.LOOP_LANE_HEIGHT + lane_offset
                bottom_bound = bound if bottom_bound is None else max(bottom_bound, bound)
            loop_lane_index += 1
        return bottom_bound

    def _add_forward_edge(
        self,
        scene: QtWidgets.QGraphicsScene,
        src_rect: QRectF,
        tgt_rect: QRectF,
        src_row: int,
        tgt_row: int,
    ) -> None:
        color = QColor("#64748B")
        pen = QPen(color, 2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)

        if src_row == tgt_row:
            if src_row % 2 == 0:
                p1 = QPointF(src_rect.right(), src_rect.center().y())
                p2 = QPointF(tgt_rect.left(), tgt_rect.center().y())
                direction = QPointF(1, 0)
            else:
                p1 = QPointF(src_rect.left(), src_rect.center().y())
                p2 = QPointF(tgt_rect.right(), tgt_rect.center().y())
                direction = QPointF(-1, 0)
            line = QtWidgets.QGraphicsLineItem(p1.x(), p1.y(), p2.x(), p2.y())
            line.setPen(pen)
            line.setZValue(6)
            scene.addItem(line)
            self._draw_arrow_head(scene, p2, direction, color, z_value=7)
            return

        p1 = QPointF(src_rect.center().x(), src_rect.bottom())
        p2 = QPointF(tgt_rect.center().x(), tgt_rect.top())
        path = QPainterPath(p1)
        if abs(p1.x() - p2.x()) < 0.1:
            path.lineTo(p2)
        else:
            mid_y = (p1.y() + p2.y()) / 2
            path.lineTo(p1.x(), mid_y)
            path.lineTo(p2.x(), mid_y)
            path.lineTo(p2)
        edge_item = QtWidgets.QGraphicsPathItem(path)
        edge_item.setPen(pen)
        edge_item.setBrush(QtGui.QBrush(Qt.NoBrush))
        edge_item.setZValue(6)
        scene.addItem(edge_item)
        self._draw_arrow_head(scene, p2, QPointF(0, 1), color, z_value=7)

    def _add_loop_edge(
        self,
        scene: QtWidgets.QGraphicsScene,
        src_rect: QRectF,
        tgt_rect: QRectF,
        loop_data: Dict[str, Any],
        lane_index: int = 0,
        src_row: int = 0,
        tgt_row: int = 0,
    ) -> None:
        route_type = self._classify_loop_route(src_row, tgt_row)
        lane_offset = lane_index * self.LOOP_LANE_GAP
        row_span = abs(src_row - tgt_row)
        color = QColor("#F59E0B")

        if route_type == "top_lane":
            src_anchor = self._loop_anchor_point(src_rect, "top")
            tgt_anchor = self._loop_anchor_point(tgt_rect, "top")
            mid_y = min(src_anchor.y(), tgt_anchor.y()) - self.LOOP_LANE_HEIGHT
            mid_y -= lane_offset
            mid_y -= row_span * 12

            path = QPainterPath(src_anchor)
            path.lineTo(src_anchor.x(), mid_y)
            path.lineTo(tgt_anchor.x(), mid_y)
            path.lineTo(tgt_anchor)
            label_anchor_x = (src_anchor.x() + tgt_anchor.x()) / 2
            label_anchor_y = mid_y - 8
            arrow_tip = tgt_anchor
            arrow_direction = QPointF(0, 1)
        elif route_type == "bottom_lane":
            src_anchor = self._loop_anchor_point(src_rect, "bottom")
            tgt_anchor = self._loop_anchor_point(tgt_rect, "bottom")
            mid_y = max(src_anchor.y(), tgt_anchor.y()) + self.LOOP_LANE_HEIGHT
            mid_y += lane_offset
            mid_y += row_span * 12

            path = QPainterPath(src_anchor)
            path.lineTo(src_anchor.x(), mid_y)
            path.lineTo(tgt_anchor.x(), mid_y)
            path.lineTo(tgt_anchor)
            label_anchor_x = (src_anchor.x() + tgt_anchor.x()) / 2
            label_anchor_y = mid_y + 8
            arrow_tip = tgt_anchor
            arrow_direction = QPointF(0, -1)
        else:
            anchor_side = "right" if route_type == "side_lane_right" else "left"
            src_anchor = self._loop_anchor_point(src_rect, anchor_side)
            tgt_anchor = self._loop_anchor_point(tgt_rect, anchor_side)
            if anchor_side == "right":
                outer_x = max(src_rect.right(), tgt_rect.right()) + self.LOOP_SIDE_MARGIN + lane_offset
                label_anchor_x = outer_x - 12
                arrow_direction = QPointF(-1, 0)
            else:
                outer_x = min(src_rect.left(), tgt_rect.left()) - self.LOOP_SIDE_MARGIN - lane_offset
                label_anchor_x = outer_x + 12
                arrow_direction = QPointF(1, 0)
            path = self._build_side_loop_path(src_anchor, tgt_anchor, outer_x)
            label_anchor_y = min(src_anchor.y(), tgt_anchor.y()) - 10
            arrow_tip = tgt_anchor

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
        label_item.setZValue(28)
        label_rect = label_item.boundingRect()
        if route_type == "top_lane":
            label_item.setPos(
                label_anchor_x - label_rect.width() / 2,
                label_anchor_y - label_rect.height(),
            )
        elif route_type == "bottom_lane":
            label_item.setPos(
                label_anchor_x - label_rect.width() / 2,
                label_anchor_y,
            )
        elif route_type == "side_lane_right":
            label_item.setPos(
                label_anchor_x - label_rect.width(),
                label_anchor_y - label_rect.height(),
            )
        else:
            label_item.setPos(
                label_anchor_x,
                label_anchor_y - label_rect.height(),
            )
        scene.addItem(label_item)

        self._draw_arrow_head(
            scene,
            arrow_tip,
            arrow_direction,
            color,
            z_value=27,
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
        if self._is_locked():
            QMessageBox.information(self, "编辑节点", "当前工艺路线已废弃，无法编辑。")
            return

        self.page_state["active_node_id"] = _text(node.get("node_id"))
        self.page_state["active_loop_id"] = _text(node.get("loop_id"))
        dialog = NodeEditorDialog(node, self._is_locked(), self)
        if dialog.exec_() != QtWidgets.QDialog.Accepted:
            return

        payload = dialog.result_payload()
        updated = False
        for step in self.page_state["current_route"]["process_route_loop_step_line"]:
            if _text(step.get("node_id")) == _text(node.get("node_id")):
                step["instruction"] = payload.get("instruction", "")
                step["params"] = payload.get("params", {})
                updated = True
                break

        if not updated:
            QMessageBox.warning(self, "编辑节点", "未找到当前节点，无法保存修改。")
            return

        self.page_state["current_route"] = self._normalize_route_context(
            self.page_state["current_route"]
        )
        self._mark_route_dirty()
        self._sync_process_route_context()
        self._render_page()

    def _open_loop_editor(self, loop_data: Dict[str, Any]) -> None:
        if self._is_locked():
            QMessageBox.information(self, "编辑循环边", "当前工艺路线已废弃，无法编辑。")
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
        self._update_constraint_context()
        route = self.page_state["current_route"]
        return {
            "process_route_header": dict(route["process_route_header"]),
            "process_route_loop_line": [dict(item) for item in route["process_route_loop_line"]],
            "process_route_loop_step_line": [dict(item) for item in route["process_route_loop_step_line"]],
        }

    def _sync_process_route_context(self) -> None:
        if not hasattr(self.controller, "context"):
            return
        payload = self._collect_payload()
        self.controller.context["process_route_context"] = payload
        if not hasattr(self.controller, "production_context"):
            self.controller.production_context = self.controller.context
        self.controller.production_context["process_route_context"] = payload

    def _update_constraint_context(self) -> None:
        if not hasattr(self.controller, "context"):
            return
        if not self._has_loaded_route():
            return
        header = self.page_state.get("current_route", {}).get("process_route_header", {})
        self.controller.context["constraint_context"] = build_constraint_context(
            header,
            self.txtPrecaution.toPlainText(),
        )
        if not hasattr(self.controller, "production_context"):
            self.controller.production_context = self.controller.context
        self.controller.production_context["constraint_context"] = self.controller.context["constraint_context"]

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

    def _approve_and_refresh(self, show_message: bool = True) -> bool:
        try:
            result = self.controller.backend.process_routes.approve(self._collect_payload())
        except BackendError as exc:
            QMessageBox.warning(self, "批准方案", f"批准失败：{exc}")
            self.txtValidationInfo.setPlainText(f"批准失败：{exc}")
            return False

        self._update_validation_summary(result)
        if not result.get("passed"):
            self.page_state["page_status"] = "created"
            self._render_page()
            QMessageBox.warning(self, "批准方案", "方案批准失败，请检查校验反馈。")
            return False

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
            return False

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
            return False

        self.page_state["current_route"] = self._normalize_route_context(persisted_route)
        header = self.page_state["current_route"]["process_route_header"]
        header["process_route_id"] = process_route_id
        header["process_route_version"] = process_route_version
        header["status"] = "validated"
        self.page_state["page_status"] = "validated"
        self.page_state["dirty"] = False
        self._sync_process_route_context()
        self._render_page()

        if show_message:
            QMessageBox.information(
                self,
                "批准方案",
                f"方案已批准并完成落库校验：{header.get('process_route_id')} V{header.get('process_route_version')}。",
            )
        return True

    def _on_approve(self) -> None:
        if self.page_state["page_status"] != "validated":
            QMessageBox.warning(self, "批准方案", "请先完成校验并确保校验通过。")
            return
        self._approve_and_refresh(show_message=True)

    def _on_next(self) -> None:
        if self.page_state["page_status"] != "validated":
            QMessageBox.warning(self, "下一步", "当前工艺路线未通过校验，无法进入下一步。")
            return

        if not self._approve_and_refresh(show_message=False):
            return

        self._sync_process_route_context()
        self.controller.context.setdefault("order_context", {})
        self.controller.context.setdefault("lot_context", {})
        self.controller.context.setdefault("process_plan_context", {})
        self.controller.context.setdefault("process_route_context", {})
        self.controller.context.setdefault("constraint_context", {})
        if not hasattr(self.controller, "production_context"):
            self.controller.production_context = self.controller.context
        self.controller.production_context.setdefault("order_context", self.controller.context["order_context"])
        self.controller.production_context.setdefault("lot_context", self.controller.context["lot_context"])
        self.controller.production_context.setdefault("process_plan_context", self.controller.context["process_plan_context"])
        self.controller.production_context["process_route_context"] = self.controller.context["process_route_context"]
        self.controller.production_context["constraint_context"] = self.controller.context["constraint_context"]
        if not hasattr(self.controller, "show_page"):
            QMessageBox.critical(self, "下一步", "主窗口未提供页面切换能力。")
            return
        self.controller.show_page("prepare_page")

    def _on_precaution_changed(self) -> None:
        if self._updating_widgets:
            return
        if not self._has_loaded_route():
            return
        self._update_constraint_context()

    def _on_weight_changed(self, value: int) -> None:
        efficiency = max(0.0, min(1.0, value / 100.0))
        self.page_state["objective_weight"] = {"efficiency": efficiency, "cost": 1.0 - efficiency}
        self.page_state["simulation"]["objective_weight"] = dict(self.page_state["objective_weight"])
