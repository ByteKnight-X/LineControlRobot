from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from datetime import datetime, timezone
import xml.etree.ElementTree as ET

from PyQt5 import QtCore, QtWidgets, uic
from PyQt5.QtWidgets import QFileDialog, QMessageBox, QTableWidget, QTableWidgetItem

from utilities.backend_client import BackendError


PRIMARY_BUTTON_STYLE = (
    "background-color: #52c41a; "
    "border: 1px solid #52c41a; "
    "color: #ffffff; "
    "font-weight: 600; "
    "padding: 6px 12px; "
    "border-radius: 6px;"
)

SECONDARY_BUTTON_STYLE = (
    "background-color: #ffffff; "
    "border: 1px solid #d9d9d9; "
    "color: #333333; "
    "padding: 6px 12px; "
    "border-radius: 6px;"
)

DISABLED_BUTTON_STYLE = (
    "background-color: #f5f5f5; "
    "border: 1px solid #d9d9d9; "
    "color: #bfbfbf; "
    "font-weight: 600; "
    "padding: 6px 12px; "
    "border-radius: 6px;"
)

DEFAULT_PENDING_PRODUCTION_LINE_ID = "F01-SP01"
FIXED_PROCESS_PLAN_ID = "PP-8Pro-梦幻世界-40-41"
FIXED_PROCESS_PLAN_VERSION = 1

DB_ALLOWED_STATUSES = {"created", "validated", "released", "finished"}
PENDING_ALLOWED_STATUSES = {"created", "validated"}
PENDING_LOT_ORIGINS = {"manual", "auto"}


def _safe_text(value: Any) -> str:
    return "" if value is None else str(value)


def _as_list(value: Any) -> List[Dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _ms_to_datetime(ms: Any, fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
    if ms in (None, ""):
        return ""
    try:
        timestamp = int(ms)
    except (TypeError, ValueError):
        return ""
    if timestamp <= 0:
        return ""
    if timestamp >= 10**12:
        timestamp = timestamp / 1000
    dt = datetime.fromtimestamp(timestamp, tz=timezone.utc).astimezone()
    return dt.strftime(fmt)


def _order_line_id(line: Dict[str, Any]) -> Any:
    return line.get("order_line_id", line.get("id"))


def _display_lot_line_order_id(line: Dict[str, Any]) -> str:
    return _safe_text(line.get("source_order_id") or line.get("order_id"))


def _display_lot_line_order_line_id(line: Dict[str, Any]) -> Any:
    return line.get("source_order_line_id", line.get("order_line_id", line.get("id")))


def _orders(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    return _as_list(payload.get("production_order_list") or payload.get("orders") or payload.get("items"))


def _lots(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    return _as_list(payload.get("lots") or payload.get("items") or payload.get("lot_list"))


def _parse_order_detail(payload: Dict[str, Any]) -> tuple[Dict[str, Any], List[Dict[str, Any]]]:
    header = payload.get("header") or payload.get("production_order_header")
    lines = payload.get("lines") or payload.get("production_order_line") or payload.get("order_lines")
    if not isinstance(header, dict):
        header = {}
    return header, _as_list(lines)


def _parse_lot_detail(payload: Dict[str, Any]) -> tuple[Dict[str, Any], List[Dict[str, Any]]]:
    header = payload.get("header") or payload.get("lot_header")
    lines = payload.get("lines") or payload.get("lot_line")
    if not isinstance(header, dict):
        header = {}
    return header, _as_list(lines)


def _display_order_id(value: Any) -> str:
    if isinstance(value, list):
        return ", ".join(_safe_text(item) for item in value if _safe_text(item))
    return _safe_text(value)


def _extract_order_header(item: Dict[str, Any]) -> Dict[str, Any]:
    header = item.get("production_order_header")
    return dict(header) if isinstance(header, dict) else {}


def _extract_order_lines(item: Dict[str, Any]) -> List[Dict[str, Any]]:
    return _as_list(item.get("production_order_line"))


def _persisted_order_id(lot: Dict[str, Any]) -> str:
    header = lot.get("lot_header")
    if isinstance(header, dict):
        source_order_id = header.get("source_order_id")
        if source_order_id not in (None, ""):
            return _display_order_id(source_order_id)
        return _safe_text(header.get("order_id"))
    return _display_order_id(lot.get("source_order_id")) or _safe_text(lot.get("order_id"))


def _candidate_source_order_id(header: Dict[str, Any]) -> str:
    return _safe_text(header.get("source_order_id"))


def _normalize_pending_status(value: Any, fallback: str = "validated") -> str:
    status = _safe_text(value).strip().lower()
    if status not in PENDING_ALLOWED_STATUSES:
        return fallback
    return status


def _normalize_db_status(value: Any) -> str:
    return _safe_text(value).strip().lower()


def _lot_can_start_separation(value: Any) -> bool:
    return _normalize_db_status(value) in {"validated", "released", "finished"}


def _normalize_int(value: Optional[str]) -> Any:
    if value in (None, ""):
        return ""
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return value


def _normalize_number(value: Optional[str]) -> Any:
    if value in (None, ""):
        return ""
    raw = str(value).strip()
    try:
        number = float(raw)
    except (TypeError, ValueError):
        return raw
    return int(number) if number.is_integer() else number


def _display_progress(value: Any) -> Any:
    return 0.0 if value in (None, "") else value


def _normalize_lot_origin(value: Any, fallback: str = "manual") -> str:
    origin = _safe_text(value).strip().lower()
    if origin not in PENDING_LOT_ORIGINS:
        return fallback
    return origin


def _generate_temporary_lot_id(existing_lot_ids: List[str], order_id: str) -> str:
    date_token = "00000000"
    order_parts = _safe_text(order_id).split("-")
    if len(order_parts) >= 2 and order_parts[1].isdigit():
        date_token = order_parts[1]

    prefix = f"TMP-LOT-{date_token}-"
    max_sequence = 0
    for lot_id in existing_lot_ids:
        if not _safe_text(lot_id).startswith(prefix):
            continue
        suffix = _safe_text(lot_id).rsplit("-", 1)[-1]
        if suffix.isdigit():
            max_sequence = max(max_sequence, int(suffix))
    return f"{prefix}{max_sequence + 1:03d}"


def _merge_source_order_ids_from_lines(lines: List[Dict[str, Any]]) -> str:
    order_ids = sorted(
        {
            _safe_text(line.get("source_order_id") or line.get("order_id"))
            for line in lines
            if isinstance(line, dict) and _safe_text(line.get("source_order_id") or line.get("order_id"))
        }
    )
    return ",".join(order_ids)


def _normalize_pending_candidate(candidate: Dict[str, Any]) -> Dict[str, Any]:
    header = dict(candidate.get("lot_header") or {})
    raw_lines = _as_list(candidate.get("lot_line"))
    lot_id = _safe_text(header.get("lot_id") or candidate.get("lot_id"))
    normalized_lines: List[Dict[str, Any]] = []
    for index, line in enumerate(raw_lines, start=1):
        source_order_id = _safe_text(line.get("source_order_id") or line.get("order_id"))
        normalized_lines.append(
            {
                "lot_id": _safe_text(line.get("lot_id") or lot_id),
                "lot_line_id": line.get("lot_line_id", index),
                "source_order_id": source_order_id,
                "source_order_line_id": line.get("source_order_line_id", line.get("order_line_id")),
                "sku": line.get("sku", ""),
                "color": line.get("color", ""),
                "pattern_design_id": line.get("pattern_design_id"),
                "separation_plan_id": line.get("separation_plan_id"),
                "separation_plan_version": line.get("separation_plan_version") or 1,
                "size": line.get("size", ""),
                "quantity_planned": line.get("quantity_planned", ""),
                "status": _normalize_pending_status(line.get("status"), fallback="created"),
            }
        )
    merged_source_order_id = _merge_source_order_ids_from_lines(normalized_lines)
    return {
        "lot_header": {
            "lot_id": lot_id,
            "source_order_id": merged_source_order_id or _safe_text(header.get("source_order_id")),
            "production_line_id": _safe_text(
                header.get("production_line_id") or candidate.get("production_line_id")
            ),
            "progress": _display_progress(header.get("progress", candidate.get("progress"))),
            "status": _normalize_pending_status(
                header.get("status", candidate.get("status")),
                fallback="created",
            ),
        },
        "lot_line": normalized_lines,
        "lot_origin": _normalize_lot_origin(candidate.get("lot_origin"), fallback="manual"),
    }


def _parse_import_order_xml(xml_bytes: bytes) -> Dict[str, Any]:
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        raise BackendError(f"本地订单 XML 解析失败：{exc}") from exc

    header_node = root.find("./header")
    lines_node = root.find("./lines")
    if header_node is None or lines_node is None:
        raise BackendError("本地订单 XML 缺少 header 或 lines 节点。")

    header = {
        "order_id": _safe_text(header_node.findtext("order_id")).strip(),
        "client_id": _safe_text(header_node.findtext("client_id")).strip(),
        "date_ms": _normalize_int(header_node.findtext("date_ms")),
        "delivery_date_ms": _normalize_int(header_node.findtext("delivery_date_ms")),
        "progress": _normalize_number(header_node.findtext("progress")),
        "status": "validated",
    }
    if not header["order_id"]:
        raise BackendError("本地订单 XML 缺少 header.order_id。")

    lines: List[Dict[str, Any]] = []
    for line_node in lines_node.findall("./line"):
        sku = _safe_text(line_node.findtext("sku")).strip()
        color = _safe_text(line_node.findtext("color")).strip()
        size = _safe_text(line_node.findtext("size")).strip()
        pattern_design_id = _safe_text(line_node.findtext("pattern_design_id")).strip()
        separation_plan_id = _safe_text(line_node.findtext("separation_plan_id")).strip()
        legacy_separation_plan_id = _safe_text(line_node.findtext("color_separation_plan")).strip()
        line = {
            "order_id": _safe_text(line_node.findtext("order_id")).strip() or header["order_id"],
            "order_line_id": _normalize_int(line_node.findtext("order_line_id")),
            "sku": sku,
            "size": size,
            "color": color,
            "pattern_design_id": pattern_design_id or f"PD-{sku}-{color}-{size}",
            "separation_plan_id": separation_plan_id or legacy_separation_plan_id or f"CS-{sku}-{color}-{size}",
            "separation_plan_version": _normalize_int(line_node.findtext("separation_plan_version")) or 1,
            "quantity_planned": _normalize_int(line_node.findtext("quantity_planned")),
            "status": "validated",
        }
        if line["order_line_id"] in ("", None):
            raise BackendError(f"本地订单 {header['order_id']} 缺少 line.order_line_id。")
        lines.append(line)

    if not lines:
        raise BackendError(f"本地订单 {header['order_id']} 缺少 production_order_line。")
    return {
        "production_order_header": header,
        "production_order_line": lines,
    }


def _setup_table(
    table: QTableWidget,
    headers: List[str],
    selection_mode: QtWidgets.QAbstractItemView.SelectionMode = QtWidgets.QAbstractItemView.SingleSelection,
) -> None:
    table.setColumnCount(len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
    table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
    table.setSelectionMode(selection_mode)
    table.setAlternatingRowColors(True)
    table.verticalHeader().setVisible(False)
    table.horizontalHeader().setStretchLastSection(True)


def _fill_table(table: QTableWidget, rows: List[List[Any]]) -> None:
    table.setRowCount(len(rows))
    for row_index, row_values in enumerate(rows):
        for col_index, value in enumerate(row_values):
            item = QTableWidgetItem(_safe_text(value))
            item.setTextAlignment(QtCore.Qt.AlignCenter)
            table.setItem(row_index, col_index, item)


def _filter_table(table: QTableWidget, keyword: str) -> None:
    keyword = keyword.strip().lower()
    for row in range(table.rowCount()):
        values = []
        for col in range(table.columnCount()):
            item = table.item(row, col)
            values.append(item.text() if item else "")
        row_text = " ".join(values).lower()
        table.setRowHidden(row, bool(keyword and keyword not in row_text))


class OrderLineAssignDialog(QtWidgets.QDialog):
    LINE_HEADERS = ["订单行ID", "SKU", "尺码", "颜色", "图案设计ID", "分色方案ID", "分色版本", "计划数量", "状态"]
    LOT_HEADERS = ["关联订单ID", "批次ID", "开始时间", "产线编号", "进度", "状态"]

    def __init__(
        self,
        order_header: Dict[str, Any],
        order_lines: List[Dict[str, Any]],
        persisted_lots: List[Dict[str, Any]],
        pending_lots: List[Dict[str, Any]],
        imported_order_line_refs: set[tuple[str, int]],
        imports_api: Any,
        on_pending_lots_changed: Callable[[List[Dict[str, Any]]], None],
        parent: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.imports_api = imports_api
        self.on_pending_lots_changed = on_pending_lots_changed
        self.imported_order_line_refs = imported_order_line_refs
        self.order_id = _safe_text(order_header.get("order_id"))
        self.order_lines = [line for line in order_lines if isinstance(line, dict)]
        self.persisted_lots = [lot for lot in persisted_lots if isinstance(lot, dict)]
        self.pending_lots = [
            _normalize_pending_candidate(lot) for lot in pending_lots if isinstance(lot, dict)
        ]
        self.lots: List[Dict[str, Any]] = []
        self.selected_lot_id = ""

        self.setWindowTitle(f"订单行导入批次 - {self.order_id}")
        self.resize(1320, 680)

        self._build_ui()
        self._load_order_lines()
        self._load_lots()
        self._load_selected_lot_lines()

    def _build_ui(self) -> None:
        root = QtWidgets.QVBoxLayout(self)

        header = QtWidgets.QFrame()
        header_layout = QtWidgets.QHBoxLayout(header)
        title = QtWidgets.QLabel(f"订单行导入批次 - {self.order_id}")
        title.setStyleSheet("font-weight: 600; font-size: 14px; color: #262626;")
        header_layout.addWidget(title)
        header_layout.addStretch(1)
        root.addWidget(header)

        body = QtWidgets.QHBoxLayout()

        left = QtWidgets.QVBoxLayout()
        left.addWidget(QtWidgets.QLabel("待导入订单行"))
        self.tblOrderLines = QtWidgets.QTableWidget()
        _setup_table(
            self.tblOrderLines,
            self.LINE_HEADERS,
            selection_mode=QtWidgets.QAbstractItemView.ExtendedSelection,
        )
        left.addWidget(self.tblOrderLines)
        body.addLayout(left, 5)

        middle = QtWidgets.QVBoxLayout()
        middle.addStretch(1)
        self.btnAssign = QtWidgets.QPushButton(">>")
        self.btnAssign.setMinimumWidth(72)
        self.btnAssign.setStyleSheet(PRIMARY_BUTTON_STYLE)
        self.btnAssign.clicked.connect(self.assign_selected_lines)
        middle.addWidget(self.btnAssign)
        middle.addStretch(1)
        body.addLayout(middle, 1)

        right = QtWidgets.QVBoxLayout()
        right.addWidget(QtWidgets.QLabel("已有批次"))
        self.tblLots = QtWidgets.QTableWidget()
        _setup_table(self.tblLots, self.LOT_HEADERS)
        self.tblLots.itemSelectionChanged.connect(self._on_lot_changed)
        right.addWidget(self.tblLots, 3)

        right.addWidget(QtWidgets.QLabel("所选批次已包含行"))
        self.tblSelectedLotLines = QtWidgets.QTableWidget()
        _setup_table(self.tblSelectedLotLines, self.LINE_HEADERS)
        right.addWidget(self.tblSelectedLotLines, 2)
        body.addLayout(right, 6)

        root.addLayout(body)

        self.lblStatus = QtWidgets.QLabel("未选择已有批次，导入时将自动新建。")
        self.lblStatus.setWordWrap(True)
        self.lblStatus.setStyleSheet("color: #595959;")
        root.addWidget(self.lblStatus)

    def _set_status(self, message: str, is_error: bool = False) -> None:
        color = "#cf1322" if is_error else "#595959"
        self.lblStatus.setStyleSheet(f"color: {color};")
        self.lblStatus.setText(message)

    def _line_row(self, line: Dict[str, Any]) -> List[Any]:
        order_line_id = line.get("source_order_line_id", _order_line_id(line))
        imported = False
        try:
            imported = (self.order_id, int(order_line_id)) in self.imported_order_line_refs
        except (TypeError, ValueError):
            imported = False
        return [
            order_line_id,
            line.get("sku", ""),
            line.get("size", ""),
            line.get("color", ""),
            line.get("pattern_design_id", ""),
            line.get("separation_plan_id", ""),
            line.get("separation_plan_version", ""),
            line.get("quantity_planned", ""),
            "已导批" if imported else (line.get("status", "") or "未导批"),
        ]

    def _lot_row(self, lot: Dict[str, Any]) -> List[Any]:
        return [
            lot.get("order_id_display") or lot.get("source_order_id") or lot.get("order_id", ""),
            lot.get("lot_id", ""),
            _ms_to_datetime(lot.get("start_time_ms")),
            lot.get("production_line_id", ""),
            _display_progress(lot.get("progress")),
            lot.get("status", ""),
        ]

    def _load_order_lines(self) -> None:
        _fill_table(self.tblOrderLines, [self._line_row(line) for line in self.order_lines])

    def _load_lots(self) -> None:
        self.lots = []
        for lot in self.persisted_lots:
            row = dict(lot)
            row["row_kind"] = "persisted"
            row["order_id_display"] = _persisted_order_id(row)
            self.lots.append(row)
        for lot in self.pending_lots:
            header = dict(lot.get("lot_header") or {})
            lines = _as_list(lot.get("lot_line"))
            self.lots.append(
                {
                    "row_kind": "pending",
                    "order_id_display": _safe_text(header.get("source_order_id") or header.get("order_id")),
                    "lot_id": _safe_text(header.get("lot_id")),
                    "start_time_ms": header.get("start_time_ms"),
                    "production_line_id": _safe_text(header.get("production_line_id")),
                    "progress": _display_progress(header.get("progress")),
                    "status": _safe_text(header.get("status")),
                    "lot_header": header,
                    "lot_line": lines,
                }
            )
        self.tblLots.blockSignals(True)
        _fill_table(self.tblLots, [self._lot_row(lot) for lot in self.lots])
        self.tblLots.blockSignals(False)

    def _selected_lot(self) -> Optional[Dict[str, Any]]:
        selection_model = self.tblLots.selectionModel()
        if selection_model is None:
            return None

        selected_rows = selection_model.selectedRows()
        if not selected_rows:
            return None

        row = selected_rows[0].row()
        if row >= len(self.lots):
            return None
        return self.lots[row]

    def _selected_line_ids(self) -> List[int]:
        selection_model = self.tblOrderLines.selectionModel()
        if selection_model is None:
            return []

        selected_rows = sorted(index.row() for index in selection_model.selectedRows())
        result: List[int] = []
        for row in selected_rows:
            if row >= len(self.order_lines):
                continue
            try:
                result.append(int(_order_line_id(self.order_lines[row])))
            except (TypeError, ValueError):
                continue
        return result

    def _on_lot_changed(self) -> None:
        self._load_selected_lot_lines()

    def _load_selected_lot_lines(self) -> None:
        selected_lot = self._selected_lot()
        if selected_lot is None:
            self.selected_lot_id = ""
            _fill_table(self.tblSelectedLotLines, [])
            self._set_status("未选择已有批次，导入时将自动新建。")
            return

        lot_id = _safe_text(selected_lot.get("lot_id"))
        self.selected_lot_id = lot_id
        if not lot_id:
            _fill_table(self.tblSelectedLotLines, [])
            self._set_status("当前选中的批次缺少批次ID，无法读取批次行。", is_error=True)
            return

        if selected_lot.get("row_kind") == "pending":
            lines = _as_list(selected_lot.get("lot_line"))
            _fill_table(self.tblSelectedLotLines, [self._line_row(line) for line in lines])
            if lines:
                self._set_status(f"当前候选批次 {lot_id} 已包含 {len(lines)} 条批次行。")
            else:
                self._set_status(f"当前候选批次 {lot_id} 暂无批次行。")
            return

        try:
            payload = self.imports_api.get_lot(lot_id)
        except BackendError as exc:
            _fill_table(self.tblSelectedLotLines, [])
            self._set_status(f"读取批次 {lot_id} 失败：{exc}", is_error=True)
            return

        _, lines = _parse_lot_detail(payload)
        _fill_table(self.tblSelectedLotLines, [self._line_row(line) for line in lines])

        if lines:
            self._set_status(f"当前批次 {lot_id} 已包含 {len(lines)} 条批次行。")
        else:
            self._set_status(f"当前批次 {lot_id} 暂无批次行。")

    def assign_selected_lines(self) -> None:
        line_ids = self._selected_line_ids()
        if not line_ids:
            QMessageBox.information(self, "", "请先在左侧选择至少一条订单行。")
            return

        selected_lot = self._selected_lot()
        if selected_lot and selected_lot.get("row_kind") == "persisted":
            self._set_status(
                "已落库批次不可在当前弹窗中追加，请选择候选批次或不选择以新建候选批次。",
                is_error=True,
            )
            return
        if selected_lot and selected_lot.get("row_kind") == "pending":
            lot_id = _safe_text(selected_lot.get("lot_id"))
            lot_order_id = _safe_text(
                selected_lot.get("order_id_display")
                or selected_lot.get("source_order_id")
                or (selected_lot.get("lot_header") or {}).get("source_order_id")
            )
            if lot_order_id and lot_order_id != self.order_id:
                answer = QMessageBox.question(
                    self,
                    "确认跨订单导入",
                    (
                        f"当前选中的批次 {lot_id} 关联订单为 {lot_order_id}，"
                        f"与当前订单 {self.order_id} 不一致，仍要继续导入吗？"
                    ),
                )
                if answer != QMessageBox.Yes:
                    return

        line_map = {
            int(_order_line_id(line)): line
            for line in self.order_lines
            if _order_line_id(line) not in (None, "")
        }
        selected_lines: List[Dict[str, Any]] = []
        for line_id in line_ids:
            line = line_map.get(line_id)
            if line is not None:
                selected_lines.append(line)
        if not selected_lines:
            self._set_status("未找到有效的订单行，无法加入候选批次。", is_error=True)
            return

        target_lot: Optional[Dict[str, Any]] = None
        if selected_lot and selected_lot.get("row_kind") == "pending":
            target_lot_id = _safe_text(selected_lot.get("lot_id"))
            for lot in self.pending_lots:
                header = lot.get("lot_header")
                if isinstance(header, dict) and _safe_text(header.get("lot_id")) == target_lot_id:
                    target_lot = lot
                    break
        created_new_lot = target_lot is None
        if target_lot is None:
            existing_ids = [
                _safe_text(lot.get("lot_id"))
                for lot in self.persisted_lots
            ]
            existing_ids.extend(
                _safe_text((lot.get("lot_header") or {}).get("lot_id"))
                for lot in self.pending_lots
            )
            target_lot = {
                "lot_header": {
                    "lot_id": _generate_temporary_lot_id(existing_ids, self.order_id),
                    "source_order_id": self.order_id,
                    "production_line_id": DEFAULT_PENDING_PRODUCTION_LINE_ID,
                    "progress": 0.0,
                    "status": "created",
                },
                "lot_line": [],
                "lot_origin": "manual",
            }
            self.pending_lots.append(target_lot)
        else:
            target_lot["lot_origin"] = "manual"

        header = target_lot.get("lot_header") or {}
        lines = _as_list(target_lot.get("lot_line"))
        existing_keys = {
            _safe_text(line.get("source_order_line_id"))
            for line in lines
            if isinstance(line, dict)
        }
        added_count = 0
        duplicate_count = 0
        next_line_id = max(
            [int(line.get("lot_line_id")) for line in lines if str(line.get("lot_line_id")).isdigit()] or [0]
        ) + 1
        for line in selected_lines:
            source_order_line_id = _order_line_id(line)
            key = _safe_text(source_order_line_id)
            if not key or key in existing_keys:
                duplicate_count += 1
                continue
            lines.append(
                {
                    "lot_id": _safe_text(header.get("lot_id")),
                    "lot_line_id": next_line_id,
                    "source_order_id": self.order_id,
                    "source_order_line_id": source_order_line_id,
                    "sku": line.get("sku", ""),
                    "color": line.get("color", ""),
                    "pattern_design_id": line.get("pattern_design_id"),
                    "separation_plan_id": line.get("separation_plan_id"),
                    "separation_plan_version": line.get("separation_plan_version") or 1,
                    "size": line.get("size", ""),
                    "quantity_planned": line.get("quantity_planned", ""),
                    "status": "created",
                }
            )
            existing_keys.add(key)
            next_line_id += 1
            added_count += 1
        header["source_order_id"] = _merge_source_order_ids_from_lines(lines)
        target_lot["lot_line"] = lines

        if added_count == 0:
            self._set_status("部分订单行已存在，已忽略重复项。", is_error=True)
            return

        self._load_lots()
        target_lot_id = _safe_text(header.get("lot_id"))
        self.tblLots.blockSignals(True)
        self.tblLots.clearSelection()
        for row_index, lot in enumerate(self.lots):
            if _safe_text(lot.get("lot_id")) == target_lot_id:
                self.tblLots.selectRow(row_index)
                break
        self.tblLots.blockSignals(False)
        self._load_selected_lot_lines()
        self.pending_lots = [
            _normalize_pending_candidate(lot) for lot in self.pending_lots if isinstance(lot, dict)
        ]
        self.on_pending_lots_changed(self.pending_lots)

        message = (
            f"{'已新建候选批次' if created_new_lot else '已更新候选批次'} {target_lot_id}，"
            f" 新增 {added_count} 条订单行。"
        )
        if duplicate_count:
            message = f"{message} 部分订单行已存在，已忽略重复项。"
        self._set_status(message)


class LotDetailDialog(QtWidgets.QDialog):
    LINE_HEADERS = ["关联订单ID", "关联订单行ID", "SKU", "尺码", "颜色", "分色方案ID", "分色版本", "计划数量", "状态"]

    def __init__(
        self,
        lot_summary: Dict[str, Any],
        lot_header: Dict[str, Any],
        lot_lines: List[Dict[str, Any]],
        allow_next_step: bool = True,
        parent: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.lot_summary = lot_summary
        self.lot_header = lot_header
        self.lot_lines = [line for line in lot_lines if isinstance(line, dict)]
        self.next_request: Optional[Dict[str, Any]] = None
        self.allow_next_step = allow_next_step
        self.requires_commit = bool(lot_summary.get("row_kind") == "pending")

        self.lot_id = _safe_text(lot_header.get("lot_id") or lot_summary.get("lot_id"))
        self.order_id = _display_order_id(
            lot_header.get("order_id")
            or lot_summary.get("order_id")
            or lot_header.get("source_order_id")
            or lot_summary.get("source_order_id")
        )

        self.setWindowTitle(f"批次详情 - {self.lot_id or '未命名批次'}")
        self.resize(980, 620)

        self._build_ui()
        self._load_summary()
        self._load_lines()

    def _build_ui(self) -> None:
        root = QtWidgets.QVBoxLayout(self)
        group = QtWidgets.QGroupBox("批次摘要")
        form = QtWidgets.QFormLayout(group)
        self.lblLotId = QtWidgets.QLabel()
        self.lblOrderId = QtWidgets.QLabel()
        self.lblStartTime = QtWidgets.QLabel()
        self.lblProductionLine = QtWidgets.QLabel()
        self.lblProgress = QtWidgets.QLabel()
        self.lblStatus = QtWidgets.QLabel()
        form.addRow("批次ID", self.lblLotId)
        form.addRow("关联订单ID", self.lblOrderId)
        form.addRow("开始时间", self.lblStartTime)
        form.addRow("产线编号", self.lblProductionLine)
        form.addRow("进度", self.lblProgress)
        form.addRow("状态", self.lblStatus)
        root.addWidget(group)

        self.tblLotLines = QtWidgets.QTableWidget()
        _setup_table(self.tblLotLines, self.LINE_HEADERS)
        root.addWidget(self.tblLotLines)

        self.lblFeedback = QtWidgets.QLabel()
        self.lblFeedback.setWordWrap(True)
        self.lblFeedback.setStyleSheet("color: #595959;")
        root.addWidget(self.lblFeedback)

        button_row = QtWidgets.QHBoxLayout()
        button_row.addStretch(1)

        self.btnNext = QtWidgets.QPushButton("开始工艺设计")
        self.btnNext.clicked.connect(self.start_separation)
        button_row.addWidget(self.btnNext)
        self._apply_next_button_state()

        root.addLayout(button_row)

    def _apply_next_button_state(self) -> None:
        self.btnNext.setEnabled(self.allow_next_step)
        if self.allow_next_step:
            self.btnNext.setStyleSheet(PRIMARY_BUTTON_STYLE)
        else:
            self.btnNext.setStyleSheet(DISABLED_BUTTON_STYLE)

    def _load_summary(self) -> None:
        header = self.lot_header if isinstance(self.lot_header, dict) else {}
        summary = self.lot_summary if isinstance(self.lot_summary, dict) else {}

        self.lblLotId.setText(_safe_text(header.get("lot_id") or summary.get("lot_id")))
        self.lblOrderId.setText(
            _display_order_id(
                header.get("order_id")
                or summary.get("order_id")
                or header.get("source_order_id")
                or summary.get("source_order_id")
            )
        )
        self.lblStartTime.setText(
            _ms_to_datetime(header.get("start_time_ms") or summary.get("start_time_ms"))
        )
        self.lblProductionLine.setText(
            _safe_text(header.get("production_line_id") or summary.get("production_line_id"))
        )
        self.lblProgress.setText(_safe_text(header.get("progress") or summary.get("progress")))
        self.lblStatus.setText(_safe_text(header.get("status") or summary.get("status")))

    def _load_lines(self) -> None:
        rows = []
        for line in self.lot_lines:
            rows.append(
                [
                    _display_lot_line_order_id(line),
                    _display_lot_line_order_line_id(line),
                    line.get("sku", ""),
                    line.get("size", ""),
                    line.get("color", ""),
                    line.get("separation_plan_id", ""),
                    line.get("separation_plan_version", ""),
                    line.get("quantity_planned", ""),
                    line.get("status", ""),
                ]
            )

        _fill_table(self.tblLotLines, rows)

        if self.lot_lines:
            self.lblFeedback.setText(f"当前批次包含 {len(self.lot_lines)} 条批次行。")
        else:
            self.lblFeedback.setText("当前批次详情未返回批次行。")
        if not self.allow_next_step:
            status = _safe_text(
                (self.lot_header if isinstance(self.lot_header, dict) else {}).get("status")
                or (self.lot_summary if isinstance(self.lot_summary, dict) else {}).get("status")
            )
            self.lblFeedback.setText(
                f"{self.lblFeedback.text()}\n当前批次状态为 {status or 'created'}，暂不可开始工艺设计。"
            )

    def start_separation(self) -> None:
        if not self.allow_next_step:
            self.lblFeedback.setText("当前批次未达到可开始工艺设计状态。")
            return
        if not self.order_id:
            self.lblFeedback.setText("当前批次缺少关联订单ID。")
            return
        
        

        self.next_request = {
            "lot_id": self.lot_id,
            "order_id": self.order_id,
            "requires_commit": self.requires_commit,
        }
        self.accept()


class ThinkingDialog(QtWidgets.QDialog):
    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self.setModal(True)
        self.setWindowTitle("")
        self.setWindowFlags(QtCore.Qt.Dialog | QtCore.Qt.FramelessWindowHint)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)

        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        card = QtWidgets.QFrame()
        card.setStyleSheet(
            "QFrame {"
            "background: #ffffff;"
            "border: 1px solid #f0f0f0;"
            "border-radius: 12px;"
            "}"
            "QLabel { color: #262626; }"
            "QProgressBar {"
            "border: none;"
            "background: #f5f5f5;"
            "border-radius: 4px;"
            "height: 8px;"
            "}"
            "QProgressBar::chunk {"
            "background: #52c41a;"
            "border-radius: 4px;"
            "}"
        )
        card_layout = QtWidgets.QVBoxLayout(card)
        card_layout.setContentsMargins(24, 20, 24, 20)
        card_layout.setSpacing(12)

        title = QtWidgets.QLabel("Thinking")
        title.setAlignment(QtCore.Qt.AlignCenter)
        title.setStyleSheet("font-size: 16px; font-weight: 600;")
        card_layout.addWidget(title)

        hint = QtWidgets.QLabel("正在生成候选批次，请稍候")
        hint.setAlignment(QtCore.Qt.AlignCenter)
        hint.setStyleSheet("font-size: 12px; color: #8c8c8c;")
        card_layout.addWidget(hint)

        progress = QtWidgets.QProgressBar()
        progress.setRange(0, 0)
        progress.setTextVisible(False)
        card_layout.addWidget(progress)

        root.addWidget(card)
        self.setFixedSize(300, 132)

    def reject(self) -> None:
        return


class ImportPage(QtWidgets.QWidget):
    ORDER_HEADERS = ["订单ID", "客户ID", "下单日期", "交付日期", "进度", "状态"]
    LOT_HEADERS = ["关联订单ID", "批次ID", "开始时间", "产线编号", "进度", "状态"]

    def __init__(self, controller):
        super().__init__()
        uic.loadUi(str(Path(__file__).resolve().parent / "forms" / "import_page.ui"), self)

        self.controller = controller
        self.imports_api = controller.backend.imports
        self.page_state = self._create_initial_page_state()
        self.order_list_items: List[Dict[str, Any]] = []
        self.order_rows: List[Dict[str, Any]] = []
        self.pending_order_rows: List[Dict[str, Any]] = []
        self.lot_rows: List[Dict[str, Any]] = []
        self.persisted_lot_rows: List[Dict[str, Any]] = []
        self.pending_lot_rows: List[Dict[str, Any]] = []
        self.pending_validation_results: Dict[str, Dict[str, Any]] = {}
        self.last_feedback_text = "请先通过“本地导入”读取生产订单，或点击“刷新数据”从后端数据库同步。"

        self._setup_ui()
        self.refresh_data()

    def _setup_ui(self) -> None:
        _setup_table(self.tblProductionOrders, self.ORDER_HEADERS)
        _setup_table(self.tblBatchOrders, self.LOT_HEADERS)
        self.btnSyncErp.setText("刷新数据")
        self.btnSyncErp.setToolTip("从当前后端数据库刷新订单和批次，不会主动从 ERP 拉取。")

        self.tblProductionOrders.cellDoubleClicked.connect(self.on_order_double_clicked)
        self.tblBatchOrders.cellDoubleClicked.connect(self.on_lot_double_clicked)
        self.tblProductionOrders.itemSelectionChanged.connect(self._on_order_selection_changed)
        self.tblBatchOrders.itemSelectionChanged.connect(self._on_lot_selection_changed)

        self.btnImportOrder.clicked.connect(self.import_order)
        self.btnSyncErp.clicked.connect(self.sync_with_erp)
        self.btnAIOptimize.clicked.connect(self.ai_optimize_lots)
        self.btnValidate.clicked.connect(self.ai_validate_lots)

        self.txtSearch.textChanged.connect(self.refresh_order_list)
        self.txtSearch.textChanged.connect(self.refresh_lot_list)

        self.cmbPriority.setEnabled(False)
        self.cmbPriority.setToolTip("当前后端未提供优先级字段。")

        self.txtValidationFeedback.setReadOnly(True)
        self.txtValidationFeedback.setPlainText(self.last_feedback_text)

    def set_feedback(self, message: str) -> None:
        self.last_feedback_text = message
        self.txtValidationFeedback.setPlainText(message)

    def _create_initial_page_state(self) -> Dict[str, Any]:
        return {
            "loading": False,
            "dirty": False,
            "focus": {
                "selected_order_ids": [],
                "selected_order_lines": [],
                "selected_lot_ids": [],
                "selected_lot_lines": [],
            },
            "data": {
                "db_orders": [],
                "db_lots": [],
                "pending_orders": [],
                "pending_lots": [],
            },
            "validation_summary": {
                "passed": False,
                "errors": [],
                "risks": [],
                "message": "",
            },
            "sync_diagnostics": {
                "raw_orders": 0,
                "display_orders": 0,
                "raw_lots": 0,
                "display_lots": 0,
                "unknown_order_statuses": [],
                "unknown_lot_statuses": [],
                "lot_detail_failures": [],
            },
        }

    def _set_loading(self, is_loading: bool) -> None:
        self.page_state["loading"] = bool(is_loading)
        self.btnSyncErp.setEnabled(not is_loading)
        self.btnImportOrder.setEnabled(not is_loading)
        self.btnAIOptimize.setEnabled(not is_loading)
        self.btnValidate.setEnabled(not is_loading)

    def _clear_validation_summary(self) -> None:
        self.page_state["validation_summary"] = {
            "passed": False,
            "errors": [],
            "risks": [],
            "message": "",
        }

    def _set_dirty(self, is_dirty: bool, clear_validation: bool = False) -> None:
        self.page_state["dirty"] = bool(is_dirty)
        if clear_validation:
            self._clear_validation_summary()

    def _update_validation_summary(
        self,
        passed: bool,
        errors: List[str],
        risks: List[str],
        message: str = "",
    ) -> None:
        self.page_state["validation_summary"] = {
            "passed": bool(passed),
            "errors": [item for item in errors if _safe_text(item)],
            "risks": [item for item in risks if _safe_text(item)],
            "message": _safe_text(message),
        }

    def _sync_view_rows_from_page_state(self) -> None:
        data = self.page_state["data"]
        self.persisted_order_items = _as_list(data.get("db_orders"))
        self.pending_order_items = _as_list(data.get("pending_orders"))
        self.persisted_lot_rows = _as_list(data.get("db_lots"))
        self.pending_lot_rows = _as_list(data.get("pending_lots"))

    def _build_order_rows_from_page_state(self) -> None:
        order_items: List[Dict[str, Any]] = []
        order_rows: List[Dict[str, Any]] = []
        pending_rows: List[Dict[str, Any]] = []
        for row_kind, source_items in (("db", self.persisted_order_items), ("pending", self.pending_order_items)):
            for item in source_items:
                if not isinstance(item, dict):
                    continue
                header = _extract_order_header(item)
                if not header:
                    continue
                row = dict(header)
                row["_row_kind"] = row_kind
                row["_source_item"] = item
                order_items.append(item)
                order_rows.append(row)
                if row_kind == "pending":
                    pending_rows.append(row)
        self.order_list_items = order_items
        self.order_rows = order_rows
        self.pending_order_rows = pending_rows

    def _selected_lot_ids(self) -> List[str]:
        selection_model = self.tblBatchOrders.selectionModel()
        if selection_model is None:
            return []
        selected_rows = sorted(index.row() for index in selection_model.selectedRows())
        lot_ids: List[str] = []
        seen = set()
        for row in selected_rows:
            if row >= len(self.lot_rows):
                continue
            lot_id = _safe_text(self.lot_rows[row].get("lot_id"))
            if lot_id and lot_id not in seen:
                seen.add(lot_id)
                lot_ids.append(lot_id)
        return lot_ids

    def _sync_focus_from_tables(self) -> None:
        focus = self.page_state["focus"]
        focus["selected_order_ids"] = self._selected_order_ids()
        focus["selected_lot_ids"] = self._selected_lot_ids()
        focus["selected_lot_lines"] = []

    def _on_order_selection_changed(self) -> None:
        self._sync_focus_from_tables()

    def _on_lot_selection_changed(self) -> None:
        self._sync_focus_from_tables()

    def _reset_pending_lot_state(self, clear_feedback_summary: bool = True) -> None:
        self.pending_validation_results = {}
        self.page_state["data"]["pending_lots"] = []
        self._sync_view_rows_from_page_state()
        if clear_feedback_summary:
            self._clear_validation_summary()

    def refresh_data(self) -> None:
        self._sync_view_rows_from_page_state()
        self._build_order_rows_from_page_state()
        self._render_order_rows()
        self.rebuild_lot_rows()
        self._restore_focus_from_page_state()

    def _restore_focus_from_page_state(self) -> None:
        self._restore_order_focus()
        self._restore_lot_focus()
        self._sync_focus_from_tables()

    def _restore_order_focus(self) -> None:
        selected_order_ids = {
            _safe_text(order_id)
            for order_id in self.page_state["focus"].get("selected_order_ids", [])
            if _safe_text(order_id)
        }
        self.tblProductionOrders.blockSignals(True)
        self.tblProductionOrders.clearSelection()
        for row_index, order in enumerate(self.order_rows):
            order_id = _safe_text(order.get("order_id"))
            if order_id and order_id in selected_order_ids:
                self.tblProductionOrders.selectRow(row_index)
        self.tblProductionOrders.blockSignals(False)

    def _restore_lot_focus(self) -> None:
        selected_lot_ids = {
            _safe_text(lot_id)
            for lot_id in self.page_state["focus"].get("selected_lot_ids", [])
            if _safe_text(lot_id)
        }
        self.tblBatchOrders.blockSignals(True)
        self.tblBatchOrders.clearSelection()
        for row_index, lot in enumerate(self.lot_rows):
            lot_id = _safe_text(lot.get("lot_id"))
            if lot_id and lot_id in selected_lot_ids:
                self.tblBatchOrders.selectRow(row_index)
        self.tblBatchOrders.blockSignals(False)

    def _selected_order_ids(self) -> List[str]:
        selection_model = self.tblProductionOrders.selectionModel()
        if selection_model is None:
            return []
        selected_rows = sorted(index.row() for index in selection_model.selectedRows())
        order_ids: List[str] = []
        seen = set()
        for row in selected_rows:
            if row >= len(self.order_rows):
                continue
            order_id = _safe_text(self.order_rows[row].get("order_id"))
            if order_id and order_id not in seen:
                seen.add(order_id)
                order_ids.append(order_id)
        return order_ids

    def _format_validation_summary(self, summary: Dict[str, Any]) -> str:
        lot_id = _safe_text(summary.get("lot_id"))
        passed = summary.get("passed")
        errors = summary.get("errors", [])
        risk_info = summary.get("risk_info", [])
        message = _safe_text(summary.get("message"))
        return (
            f"- 批次ID：{lot_id or '未命名候选批次'}\n"
            f"  passed: {passed}\n"
            f"  errors: {errors}\n"
            f"  risk_info: {risk_info}\n"
            f"  message: {message}"
        )

    def _build_persisted_lot_row(self, lot: Dict[str, Any]) -> Dict[str, Any]:
        header = lot.get("lot_header")
        lines = lot.get("lot_line")
        if isinstance(header, dict):
            lot_header = dict(header)
            lot_line = _as_list(lines)
        else:
            lot_header = dict(lot)
            lot_line = []
        return {
            "row_kind": "persisted",
            "order_id_display": _persisted_order_id({"lot_header": lot_header}),
            "lot_id": _safe_text(lot_header.get("lot_id")),
            "start_time_ms": lot_header.get("start_time_ms"),
            "production_line_id": _safe_text(lot_header.get("production_line_id")),
            "progress": _display_progress(lot_header.get("progress")),
            "status": _safe_text(lot_header.get("status")),
            "lot_header": lot_header,
            "lot_line": lot_line,
            "validation_summary": {},
        }

    def _build_pending_lot_row(self, candidate: Dict[str, Any]) -> Dict[str, Any]:
        header = candidate.get("lot_header")
        lines = candidate.get("lot_line")
        if not isinstance(header, dict) or not isinstance(lines, list):
            raise BackendError("候选批次单结构无效。")
        lot_id = _safe_text(header.get("lot_id"))
        if not lot_id:
            raise BackendError("候选批次缺少 lot_header.lot_id。")
        if not _safe_text(header.get("production_line_id")):
            raise BackendError(f"候选批次 {lot_id} 缺少 lot_header.production_line_id。")
        if not _candidate_source_order_id(header):
            raise BackendError(f"候选批次 {lot_id} 缺少 lot_header.source_order_id。")
        for line_index, line in enumerate(_as_list(lines), start=1):
            if _safe_text(line.get("lot_id")) != lot_id:
                raise BackendError(f"候选批次 {lot_id} 的第 {line_index} 条 lot_line 缺少或错配 lot_id。")
            if line.get("lot_line_id") is None:
                raise BackendError(f"候选批次 {lot_id} 的第 {line_index} 条 lot_line 缺少 lot_line_id。")
            if _safe_text(line.get("source_order_id")) != _candidate_source_order_id(header):
                raise BackendError(f"候选批次 {lot_id} 的第 {line_index} 条 lot_line 缺少或错配 source_order_id。")
            if line.get("source_order_line_id") is None:
                raise BackendError(f"候选批次 {lot_id} 的第 {line_index} 条 lot_line 缺少 source_order_line_id。")
            for field in ("sku", "color", "size", "quantity_planned", "status"):
                if line.get(field) in (None, ""):
                    raise BackendError(f"候选批次 {lot_id} 的第 {line_index} 条 lot_line 缺少 {field}。")
        validation_summary = self.pending_validation_results.get(lot_id, {})
        status = _normalize_pending_status(header.get("status"), fallback="created")
        return {
            "row_kind": "pending",
            "order_id_display": _candidate_source_order_id(header),
            "lot_id": lot_id,
            "start_time_ms": header.get("start_time_ms"),
            "production_line_id": _safe_text(header.get("production_line_id")),
            "progress": _display_progress(header.get("progress")),
            "status": status,
            "lot_header": header,
            "lot_line": _as_list(lines),
            "validation_summary": validation_summary,
        }

    def rebuild_lot_rows(self) -> None:
        self._sync_view_rows_from_page_state()
        rows: List[Dict[str, Any]] = []
        rows.extend(self._build_persisted_lot_row(lot) for lot in self.persisted_lot_rows if isinstance(lot, dict))
        rows.extend(self._build_pending_lot_row(lot) for lot in self.pending_lot_rows if isinstance(lot, dict))
        self.lot_rows = rows

        table_rows = []
        for lot in self.lot_rows:
            table_rows.append(
                [
                    lot.get("order_id_display", ""),
                    lot.get("lot_id", ""),
                    _ms_to_datetime(lot.get("start_time_ms")),
                    lot.get("production_line_id", ""),
                    lot.get("progress", ""),
                    lot.get("status", ""),
                ]
            )
        _fill_table(self.tblBatchOrders, table_rows)
        self.refresh_lot_list()

    def _render_order_rows(self) -> None:
        rows = []
        for order in self.order_rows:
            rows.append(
                [
                    order.get("order_id", ""),
                    order.get("client_id", ""),
                    _ms_to_datetime(order.get("date_ms")),
                    _ms_to_datetime(order.get("delivery_date_ms")),
                    order.get("progress", ""),
                    order.get("status", ""),
                ]
            )
        _fill_table(self.tblProductionOrders, rows)
        self.refresh_order_list()

    def _normalize_db_orders(
        self, order_items: List[Dict[str, Any]]
    ) -> tuple[List[Dict[str, Any]], List[str], int]:
        result: List[Dict[str, Any]] = []
        unknown_statuses: set[str] = set()
        for item in order_items:
            header = _extract_order_header(item)
            if not header:
                continue
            normalized_status = _normalize_db_status(header.get("status"))
            if normalized_status and normalized_status not in DB_ALLOWED_STATUSES:
                unknown_statuses.add(normalized_status)
            result.append(item)
        return result, sorted(unknown_statuses), len(_as_list(order_items))

    def _normalize_db_lots(
        self, lots: List[Dict[str, Any]]
    ) -> tuple[List[Dict[str, Any]], List[str], int]:
        result: List[Dict[str, Any]] = []
        unknown_statuses: set[str] = set()
        raw_count = 0
        for lot in lots:
            if not isinstance(lot, dict):
                continue
            raw_count += 1
            header = lot.get("lot_header") if isinstance(lot.get("lot_header"), dict) else lot
            normalized_status = _normalize_db_status(header.get("status"))
            if normalized_status and normalized_status not in DB_ALLOWED_STATUSES:
                unknown_statuses.add(normalized_status)
            result.append(lot)
        return result, sorted(unknown_statuses), raw_count

    def _collect_imported_order_line_refs(self) -> set[tuple[str, int]]:
        refs: set[tuple[str, int]] = set()
        for lot in _as_list(self.page_state["data"].get("db_lots")):
            for line in _as_list((lot.get("lot_line") if isinstance(lot, dict) else [])):
                order_id = _safe_text(line.get("order_id"))
                order_line_id = line.get("order_line_id")
                try:
                    if order_id:
                        refs.add((order_id, int(order_line_id)))
                except (TypeError, ValueError):
                    continue
        for lot in _as_list(self.page_state["data"].get("pending_lots")):
            for line in _as_list((lot.get("lot_line") if isinstance(lot, dict) else [])):
                order_id = _safe_text(line.get("source_order_id") or line.get("order_id"))
                order_line_id = line.get("source_order_line_id", line.get("order_line_id"))
                try:
                    if order_id:
                        refs.add((order_id, int(order_line_id)))
                except (TypeError, ValueError):
                    continue
        return refs

    def _build_excluded_order_lines(self, selected_order_ids: List[str]) -> List[Dict[str, Any]]:
        selected = {_safe_text(order_id) for order_id in selected_order_ids if _safe_text(order_id)}
        return [
            {"order_id": order_id, "order_line_id": order_line_id}
            for order_id, order_line_id in sorted(self._collect_imported_order_line_refs())
            if order_id in selected
        ]

    def _pending_lot_related_order_ids(self, candidate: Dict[str, Any]) -> set[str]:
        related_order_ids: set[str] = set()
        for line in _as_list(candidate.get("lot_line")):
            order_id = _safe_text(line.get("source_order_id") or line.get("order_id"))
            if order_id:
                related_order_ids.add(order_id)
        if related_order_ids:
            return related_order_ids

        header = dict(candidate.get("lot_header") or {})
        raw_source_order_id = _safe_text(header.get("source_order_id") or header.get("order_id"))
        for order_id in raw_source_order_id.split(","):
            normalized_order_id = _safe_text(order_id).strip()
            if normalized_order_id:
                related_order_ids.add(normalized_order_id)
        return related_order_ids

    def load_orders_into_state(self) -> tuple[bool, str]:
        try:
            payload = self.imports_api.list_orders()
            order_items = _orders(payload)
            for index, item in enumerate(order_items, start=1):
                if not _extract_order_header(item):
                    raise BackendError(
                        f"订单列表结构无效：production_order_list 第 {index} 项缺少 production_order_header。"
                    )
            normalized_orders, unknown_statuses, raw_count = self._normalize_db_orders(order_items)
            self.page_state["data"]["db_orders"] = normalized_orders
            sync_diagnostics = self.page_state["sync_diagnostics"]
            sync_diagnostics["raw_orders"] = raw_count
            sync_diagnostics["display_orders"] = len(normalized_orders)
            sync_diagnostics["unknown_order_statuses"] = unknown_statuses
        except BackendError as exc:
            return False, str(exc)
        return True, ""

    def load_lots_into_state(self) -> tuple[bool, str]:
        try:
            payload = self.imports_api.list_lots()
            detailed_lots: List[Dict[str, Any]] = []
            lot_detail_failures: List[str] = []
            for lot in _lots(payload):
                if not isinstance(lot, dict):
                    continue
                lot_id = _safe_text(lot.get("lot_id"))
                if not lot_id:
                    continue
                try:
                    detail_payload = self.imports_api.get_lot(lot_id)
                except BackendError:
                    lot_detail_failures.append(lot_id)
                    continue
                lot_header, lot_lines = _parse_lot_detail(detail_payload)
                detailed_lots.append({"lot_header": lot_header, "lot_line": lot_lines})
            normalized_lots, unknown_statuses, raw_count = self._normalize_db_lots(detailed_lots)
            self.page_state["data"]["db_lots"] = normalized_lots
            sync_diagnostics = self.page_state["sync_diagnostics"]
            sync_diagnostics["raw_lots"] = raw_count
            sync_diagnostics["display_lots"] = len(normalized_lots)
            sync_diagnostics["unknown_lot_statuses"] = unknown_statuses
            sync_diagnostics["lot_detail_failures"] = lot_detail_failures
        except BackendError as exc:
            return False, str(exc)
        return True, ""

    def sync_with_erp(self) -> None:
        self._set_loading(True)
        try:
            self.page_state["sync_diagnostics"] = {
                "raw_orders": 0,
                "display_orders": 0,
                "raw_lots": 0,
                "display_lots": 0,
                "unknown_order_statuses": [],
                "unknown_lot_statuses": [],
                "lot_detail_failures": [],
            }
            order_success, order_error = self.load_orders_into_state()
            lot_success, lot_error = self.load_lots_into_state()
            self.refresh_data()
            if order_success and lot_success:
                diagnostics = self.page_state["sync_diagnostics"]
                feedback_lines = [
                    "同步完成（来源：后端数据库）。",
                    f"- backend_url：{getattr(self.controller.backend, 'base_url', '未提供')}",
                    f"- raw_orders：{diagnostics['raw_orders']}",
                    f"- display_orders：{diagnostics['display_orders']}",
                    f"- raw_lots：{diagnostics['raw_lots']}",
                    f"- display_lots：{diagnostics['display_lots']}",
                    f"- pending_orders：{len(self.page_state['data']['pending_orders'])}",
                    f"- pending_lots：{len(self.page_state['data']['pending_lots'])}",
                    f"- unknown_order_statuses：{diagnostics['unknown_order_statuses']}",
                    f"- unknown_lot_statuses：{diagnostics['unknown_lot_statuses']}",
                    f"- lot_detail_failures：{diagnostics['lot_detail_failures']}",
                ]
                if diagnostics["display_orders"] == 0 and diagnostics["display_lots"] == 0:
                    feedback_lines.append("- 提示：当前后端数据库无订单/批次数据，本次操作未执行 ERP 拉取。")
                self.set_feedback("\n".join(feedback_lines))
            else:
                errors = []
                if not order_success:
                    errors.append(f"订单同步失败：{order_error}")
                if not lot_success:
                    errors.append(f"批次同步失败：{lot_error}")
                self.set_feedback("ERP 同步部分失败。\n" + "\n".join(f"- {item}" for item in errors))
        finally:
            self._set_loading(False)

    def _upsert_pending_order(self, pending_order: Dict[str, Any]) -> None:
        order_id = _safe_text(_extract_order_header(pending_order).get("order_id"))
        if not order_id:
            return
        normalized_header = dict(_extract_order_header(pending_order))
        normalized_header["status"] = "validated"
        normalized_lines = []
        for line in _extract_order_lines(pending_order):
            normalized_line = dict(line)
            normalized_line["status"] = "validated"
            normalized_lines.append(normalized_line)
        normalized_order = {
            "production_order_header": normalized_header,
            "production_order_line": normalized_lines,
        }
        pending_orders = [
            item
            for item in self.page_state["data"]["pending_orders"]
            if _safe_text(_extract_order_header(item).get("order_id")) != order_id
        ]
        pending_orders.append(normalized_order)
        self.page_state["data"]["pending_orders"] = pending_orders

    def _upsert_manual_pending_lot(
        self,
        result: Dict[str, Any],
        order_header: Dict[str, Any],
        order_lines: List[Dict[str, Any]],
    ) -> None:
        lot_id = _safe_text(result.get("lot_id"))
        if not lot_id:
            return
        selected_line_ids = {int(line_id) for line_id in result.get("selected_line_ids", []) if str(line_id).isdigit()}
        selected_lines = []
        for line in order_lines:
            try:
                line_id = int(_order_line_id(line))
            except (TypeError, ValueError):
                continue
            if line_id in selected_line_ids:
                selected_lines.append(line)
        if not selected_lines:
            return

        existing_header: Dict[str, Any] = {}
        existing_lines: List[Dict[str, Any]] = []
        for item in self.page_state["data"]["pending_lots"]:
            header = item.get("lot_header")
            if isinstance(header, dict) and _safe_text(header.get("lot_id")) == lot_id:
                existing_header = dict(header)
                existing_lines = _as_list(item.get("lot_line"))
                break

        lot_header = {
            "lot_id": lot_id,
            "source_order_id": _safe_text(order_header.get("order_id")),
            "production_line_id": _safe_text(existing_header.get("production_line_id")),
            "status": _normalize_pending_status(result.get("status"), fallback="created"),
        }

        line_map = {
            _safe_text(line.get("source_order_line_id")): dict(line)
            for line in existing_lines
            if isinstance(line, dict)
        }
        for line in selected_lines:
            source_order_line_id = _order_line_id(line)
            key = _safe_text(source_order_line_id)
            line_map[key] = {
                "lot_id": lot_id,
                "lot_line_id": line_map.get(key, {}).get("lot_line_id") or source_order_line_id,
                "source_order_id": _safe_text(order_header.get("order_id")),
                "source_order_line_id": source_order_line_id,
                "sku": line.get("sku", ""),
                "color": line.get("color", ""),
                "pattern_design_id": line.get("pattern_design_id"),
                "separation_plan_id": line.get("separation_plan_id"),
                "separation_plan_version": line.get("separation_plan_version") or 1,
                "size": line.get("size", ""),
                "quantity_planned": line.get("quantity_planned", ""),
                "status": _normalize_pending_status(result.get("status"), fallback="created"),
            }

        pending_lot = {"lot_header": lot_header, "lot_line": list(line_map.values()), "lot_origin": "manual"}
        pending_lots = []
        for item in self.page_state["data"]["pending_lots"]:
            header = item.get("lot_header")
            if isinstance(header, dict) and _safe_text(header.get("lot_id")) == lot_id:
                continue
            pending_lots.append(item)
        pending_lots.append(pending_lot)
        self.page_state["data"]["pending_lots"] = pending_lots

    def _on_manual_pending_lots_changed(self, pending_lots: List[Dict[str, Any]]) -> None:
        self.page_state["data"]["pending_lots"] = [
            _normalize_pending_candidate(item) for item in pending_lots if isinstance(item, dict)
        ]
        self._set_dirty(True, clear_validation=True)
        self.refresh_data()

    def import_order(self) -> None:
        file_path_text, _ = QFileDialog.getOpenFileName(self, "选择生产订单", "", "XML Files (*.xml)")
        if not file_path_text:
            return

        xml_bytes = Path(file_path_text).read_bytes()

        self._set_loading(True)
        try:
            response = self.imports_api.import_local_order(xml_bytes)
        except BackendError as exc:
            self._set_loading(False)
            self.set_feedback(f"导入订单出现异常：{exc}")
            return

        if response.get("passed") is False:
            self._set_loading(False)
            self.set_feedback(
                f"订单导入未通过。\n错误：{response.get('errors', [])}\n风险：{response.get('risks', [])}"
            )
            return

        parse_error = ""
        try:
            pending_order = _parse_import_order_xml(xml_bytes)
            self._upsert_pending_order(pending_order)
        except BackendError as exc:
            parse_error = str(exc)

        self._set_dirty(True, clear_validation=True)
        self.refresh_data()
        self._set_loading(False)
        feedback = (
            "成功导入生产订单。\n"
            f"- passed：{response.get('passed', True)}\n"
            f"- errors：{response.get('errors', [])}\n"
            f"- risks：{response.get('risks', [])}"
        )
        if parse_error:
            feedback = f"{feedback}\n- 提示：导入成功，但本地待处理订单无法展示：{parse_error}"
        self.set_feedback(feedback)

    def on_order_double_clicked(self, row: int, column: int) -> None:
        del column
        if row >= len(self.order_rows):
            return

        order = self.order_rows[row]
        order_id = _safe_text(order.get("order_id"))
        if not order_id:
            QMessageBox.warning(self, "订单缺失", "当前订单缺少订单ID，无法查询订单行。")
            return

        source_item = order.get("_source_item")
        order_header = _extract_order_header(source_item) if isinstance(source_item, dict) else {}
        order_lines = _extract_order_lines(source_item) if isinstance(source_item, dict) else []
        if not order_lines:
            QMessageBox.information(self, "无可分配订单行", f"订单 {order_id} 当前无可分配订单行。")
            return

        dialog = OrderLineAssignDialog(
            order_header=order_header or order,
            order_lines=order_lines,
            persisted_lots=self.persisted_lot_rows,
            pending_lots=_as_list(self.page_state["data"]["pending_lots"]),
            imported_order_line_refs=self._collect_imported_order_line_refs(),
            imports_api=self.imports_api,
            on_pending_lots_changed=self._on_manual_pending_lots_changed,
            parent=self,
        )
        dialog.exec_()

    def _candidate_to_pending_lot(self, candidate: Dict[str, Any]) -> Dict[str, Any]:
        header = dict(candidate.get("lot_header") or {})
        lines = _as_list(candidate.get("lot_line"))
        return {
            "lot_header": {
                "pending_lot_id": _safe_text(header.get("lot_id")),
                "production_line_id": _safe_text(header.get("production_line_id")),
                "line_spec_id": None,
                "status": _normalize_pending_status(header.get("status"), fallback="validated"),
            },
            "lot_line": [
                {
                    "pending_lot_line_id": line.get("lot_line_id"),
                    "source_order_id": _safe_text(line.get("source_order_id")),
                    "source_order_line_id": line.get("source_order_line_id"),
                    "sku": line.get("sku"),
                    "color": line.get("color"),
                    "separation_plan_id": line.get("separation_plan_id"),
                    "separation_plan_version": line.get("separation_plan_version") or 1,
                    "size": line.get("size"),
                    "quantity_planned": line.get("quantity_planned"),
                }
                for line in lines
            ],
        }

    def _primary_order_id_for_lot(self, lot_header: Dict[str, Any], lot_lines: List[Dict[str, Any]]) -> str:
        for line in lot_lines:
            order_id = _safe_text(line.get("source_order_id") or line.get("order_id"))
            if order_id:
                return order_id
        source_order_id = _safe_text(lot_header.get("source_order_id") or lot_header.get("order_id"))
        if "," in source_order_id:
            return source_order_id.split(",", 1)[0].strip()
        return source_order_id

    def _open_separation_page(
        self,
        lot_payload: Dict[str, Any],
        order_payload: Dict[str, Any],
    ) -> None:
        lot_header, lot_lines = _parse_lot_detail(lot_payload)
        order_header, order_lines = _parse_order_detail(order_payload)
        process_plan_context, load_message = self._load_fixed_process_plan_context()
        lot_context = {"lot_header": lot_header, "lot_line": lot_lines}
        order_context = {"order_header": order_header, "order_line": order_lines}
        self.controller.context["lot_context"] = lot_context
        self.controller.context["order_context"] = order_context
        self.controller.context["process_plan_context"] = process_plan_context
        self.controller.context["process_plan_load_message"] = load_message
        self.controller.context.setdefault("process_route_context", {})
        self.controller.context.setdefault("constraint_context", {})
        print(self.controller.context)
        self.controller.show_page("separation_page")

    def _load_fixed_process_plan_context(self) -> tuple[Dict[str, Any], str]:
        try:
            detail = self.controller.backend.process_plans.detail(
                FIXED_PROCESS_PLAN_ID,
                FIXED_PROCESS_PLAN_VERSION,
            )
        except BackendError as exc:
            return {}, f"固定工艺方案加载失败：{exc}，已进入草稿模式。"

        header = detail.get("process_plan_header")
        lines = detail.get("process_plan_line")
        if not isinstance(header, dict) or not isinstance(lines, list):
            return {}, "固定工艺方案加载失败：后端返回的方案详情结构无效，已进入草稿模式。"
        return (
            {
                "process_plan_header": dict(header),
                "process_plan_line": [dict(item) for item in lines if isinstance(item, dict)],
            },
            f"已加载固定工艺方案 {FIXED_PROCESS_PLAN_ID} V{FIXED_PROCESS_PLAN_VERSION}",
        )

    def _commit_pending_lot_and_open_separation(self, candidate_row: Dict[str, Any]) -> None:
        candidate_header = dict(candidate_row.get("lot_header") or {})
        candidate_lines = _as_list(candidate_row.get("lot_line"))
        if not _safe_text(candidate_header.get("lot_id")).startswith("TMP-LOT-"):
            self.set_feedback("候选批次提交失败：仅支持提交自动生成的临时批次。")
            return
        pending_lot = self._candidate_to_pending_lot(
            {"lot_header": candidate_header, "lot_line": candidate_lines}
        )

        try:
            commit_response = self.imports_api.commit_lot(pending_lot)
        except BackendError as exc:
            self.set_feedback(f"候选批次提交失败：{exc}")
            return

        if not commit_response.get("passed", False):
            self.set_feedback(
                "候选批次提交失败：\n"
                f"- errors：{commit_response.get('error_info', [])}\n"
                f"- risks：{commit_response.get('risk_info', [])}"
            )
            return

        formal_lot_id = _safe_text(commit_response.get("lot_id"))
        if not formal_lot_id:
            self.set_feedback("候选批次提交失败：后端未返回正式 LOT ID。")
            return

        try:
            lot_payload = self.imports_api.get_lot(formal_lot_id)
        except BackendError as exc:
            self.set_feedback(f"正式批次已提交，但获取详情失败：{exc}")
            return

        lot_header, lot_lines = _parse_lot_detail(lot_payload)
        source_order_id = self._primary_order_id_for_lot(candidate_header, candidate_lines)
        if not source_order_id:
            self.set_feedback("正式批次已提交，但未能解析关联订单。")
            return

        try:
            order_payload = self.imports_api.get_order(source_order_id)
        except BackendError as exc:
            self.set_feedback(f"正式批次已提交，但获取关联订单失败：{exc}")
            return

        tmp_lot_id = _safe_text(candidate_header.get("lot_id"))
        self.page_state["data"]["pending_lots"] = [
            item
            for item in self.page_state["data"]["pending_lots"]
            if _safe_text((item.get("lot_header") or {}).get("lot_id")) != tmp_lot_id
        ]
        db_lots = [
            item
            for item in self.page_state["data"]["db_lots"]
            if _safe_text((item.get("lot_header") or item).get("lot_id")) != formal_lot_id
        ]
        db_lots.append({"lot_header": dict(lot_header), "lot_line": lot_lines})
        self.page_state["data"]["db_lots"] = db_lots
        self.pending_validation_results.pop(tmp_lot_id, None)
        self.refresh_data()
        self._open_separation_page(lot_payload, order_payload)

    def on_lot_double_clicked(self, row: int, column: int) -> None:
        del column
        if row >= len(self.lot_rows):
            return

        lot_summary = self.lot_rows[row]
        row_kind = lot_summary.get("row_kind")
        lot_id = _safe_text(lot_summary.get("lot_id"))
        if not lot_id:
            QMessageBox.warning(self, "批次缺失", "当前批次缺少批次ID，无法查询批次详情。")
            return

        if row_kind == "pending":
            dialog = LotDetailDialog(
                lot_summary=lot_summary,
                lot_header=lot_summary.get("lot_header", {}),
                lot_lines=lot_summary.get("lot_line", []),
                allow_next_step=_lot_can_start_separation(lot_summary.get("status")),
                parent=self.controller,
            )
            if dialog.exec_() != QtWidgets.QDialog.Accepted or not dialog.next_request:
                return
            self._commit_pending_lot_and_open_separation(lot_summary)
            return

        try:
            lot_payload = self.imports_api.get_lot(lot_id)
        except BackendError as exc:
            QMessageBox.critical(self, "获取批次详情失败", str(exc))
            return

        lot_header, lot_lines = _parse_lot_detail(lot_payload)
        dialog = LotDetailDialog(
            lot_summary=lot_summary,
            lot_header=lot_header,
            lot_lines=lot_lines,
            allow_next_step=_lot_can_start_separation(lot_header.get("status") or lot_summary.get("status")),
            parent=self.controller,
        )
        if dialog.exec_() != QtWidgets.QDialog.Accepted or not dialog.next_request:
            return

        order_id = _safe_text(dialog.next_request.get("order_id"))
        if not order_id:
            self.set_feedback("无法进入下一步：当前批次缺少关联订单ID。")
            return

        try:
            order_payload = self.imports_api.get_order(order_id)
        except BackendError as exc:
            self.set_feedback(f"获取关联订单失败：{exc}")
            return

        self._open_separation_page(lot_payload, order_payload)

    def ai_optimize_lots(self) -> None:
        order_ids = self._selected_order_ids()
        if not order_ids:
            self.set_feedback("请先在生产订单表中选择至少一条生产订单。")
            return
        excluded_order_lines = self._build_excluded_order_lines(order_ids)

        thinking_dialog = ThinkingDialog(self)
        self._set_loading(True)
        try:
            thinking_dialog.show()
            thinking_dialog.raise_()
            thinking_dialog.activateWindow()
            QtWidgets.QApplication.processEvents()
            response = self.imports_api.generate_lots(
                selected_orders=order_ids,
                excluded_order_lines=excluded_order_lines,
            )
        except BackendError as exc:
            self.set_feedback(f"候选批次单生成失败：{exc}")
            return
        finally:
            thinking_dialog.done(QtWidgets.QDialog.Accepted)
            thinking_dialog.deleteLater()
            self._set_loading(False)

        lots = _as_list(response.get("lots"))
        for candidate in lots:
            header = candidate.get("lot_header")
            if isinstance(header, dict):
                header.setdefault("status", "validated")
                header.setdefault("progress", 0.0)
            for line in _as_list(candidate.get("lot_line")):
                if isinstance(line, dict):
                    line.setdefault("status", "validated")
            candidate["lot_origin"] = "auto"

        selected_order_ids = {_safe_text(order_id) for order_id in order_ids if _safe_text(order_id)}
        kept_pending_lots: List[Dict[str, Any]] = []
        for item in _as_list(self.page_state["data"]["pending_lots"]):
            candidate = _normalize_pending_candidate(item)
            lot_origin = _normalize_lot_origin(candidate.get("lot_origin"), fallback="manual")
            if lot_origin == "manual":
                kept_pending_lots.append(candidate)
                continue
            related_order_ids = self._pending_lot_related_order_ids(candidate)
            if related_order_ids.isdisjoint(selected_order_ids):
                kept_pending_lots.append(candidate)

        normalized_auto_lots = [
            _normalize_pending_candidate(candidate) for candidate in lots if isinstance(candidate, dict)
        ]
        self.page_state["data"]["pending_lots"] = kept_pending_lots + normalized_auto_lots
        self.pending_validation_results = {}
        self._clear_validation_summary()
        self._set_dirty(True)
        self.refresh_data()

        summary_lines = [
            "候选批次单生成完成：",
            f"- 订单ID：{order_ids}",
            f"- passed：{response.get('passed')}",
            f"- message：{response.get('message', '')}",
            f"- 新增自动候选批次数量：{len(normalized_auto_lots)}",
            f"- 当前候选批次总数：{len(self.page_state['data']['pending_lots'])}",
        ]
        for candidate in normalized_auto_lots:
            header = candidate.get("lot_header", {})
            lines = _as_list(candidate.get("lot_line"))
            summary_lines.append(
                (
                    f"- lot_id：{_safe_text(header.get('lot_id')) or '未命名候选批次'}，"
                    f" source_order_id：{_candidate_source_order_id(header)}，"
                    f" line_count：{len(lines)}"
                )
            )
        self.set_feedback("\n".join(summary_lines))

    def ai_validate_lots(self) -> None:
        raw_pending_lots = [
            _normalize_pending_candidate(item)
            for item in _as_list(self.page_state["data"]["pending_lots"])
            if isinstance(item, dict)
        ]
        self.page_state["data"]["pending_lots"] = raw_pending_lots
        self._sync_view_rows_from_page_state()
        if not self.pending_lot_rows:
            self.set_feedback("当前无候选批次单可校验。")
            return

        pending_lots = []
        for candidate in raw_pending_lots:
            header = candidate.get("lot_header")
            lines = candidate.get("lot_line")
            if not isinstance(header, dict) or not isinstance(lines, list):
                self.set_feedback("候选批次单结构无效，无法发起校验。")
                return
            pending_lots.append({"lot_header": header, "lot_line": _as_list(lines)})

        self._set_loading(True)
        try:
            response = self.imports_api.validate_lots(pending_lots=pending_lots)
        except BackendError as exc:
            self._set_loading(False)
            self.set_feedback(f"候选批次单校验失败：{exc}")
            return

        results = _as_list(response.get("validation_results"))
        if not results:
            self._set_loading(False)
            self.set_feedback("候选批次单校验失败：后端返回的 validation_results 为空。")
            return
        self.pending_validation_results = {
            _safe_text(item.get("lot_id")): item for item in results if _safe_text(item.get("lot_id"))
        }
        for candidate in self.page_state["data"]["pending_lots"]:
            header = candidate.get("lot_header")
            if not isinstance(header, dict):
                continue
            lot_id = _safe_text(header.get("lot_id"))
            result = self.pending_validation_results.get(lot_id, {})
            header["status"] = "validated" if result.get("passed") else "created"
            if "status" in candidate:
                candidate["status"] = header["status"]
        aggregated_errors: List[str] = []
        aggregated_risks: List[str] = []
        for item in results:
            aggregated_errors.extend(_safe_text(error) for error in item.get("errors", []) if _safe_text(error))
            aggregated_risks.extend(_safe_text(risk) for risk in item.get("risk_info", []) if _safe_text(risk))
        self._update_validation_summary(
            passed=all(bool(item.get("passed")) for item in results),
            errors=aggregated_errors,
            risks=aggregated_risks,
            message=_safe_text(response.get("message") or "候选批次单校验完成"),
        )
        self._set_dirty(False)
        self.refresh_data()
        self._set_loading(False)

        passed_count = sum(1 for item in results if item.get("passed"))
        failed_count = len(results) - passed_count
        feedback_lines = [
            "候选批次单校验完成：",
            f"- 校验总数：{len(results)}",
            f"- 通过数量：{passed_count}",
            f"- 失败数量：{failed_count}",
        ]
        if response.get("message"):
            feedback_lines.append(f"- message：{response.get('message')}")
        for item in results:
            feedback_lines.append(self._format_validation_summary(item))
        self.set_feedback("\n".join(feedback_lines))

    def refresh_order_list(self) -> None:
        _filter_table(self.tblProductionOrders, self.txtSearch.text())
        self._sync_focus_from_tables()

    def refresh_lot_list(self) -> None:
        _filter_table(self.tblBatchOrders, self.txtSearch.text())
        self._sync_focus_from_tables()
