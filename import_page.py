from pathlib import Path
from typing import Any, Dict, List, Optional

from datetime import datetime, timezone

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


def _orders(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    return _as_list(payload.get("orders") or payload.get("items"))


def _lots(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    return _as_list(payload.get("lots") or payload.get("items"))


def _parse_order_detail(payload: Dict[str, Any]) -> tuple[Dict[str, Any], List[Dict[str, Any]]]:
    header = payload.get("production_order_header") or payload.get("header")
    lines = payload.get("production_order_line") or payload.get("lines") or payload.get("order_lines")
    if not isinstance(header, dict):
        header = {}
    return header, _as_list(lines)


def _parse_lot_detail(payload: Dict[str, Any]) -> tuple[Dict[str, Any], List[Dict[str, Any]]]:
    header = payload.get("lot_header") or payload.get("header")
    lines = payload.get("lot_line") or payload.get("lines")
    if not isinstance(header, dict):
        header = {}
    return header, _as_list(lines)


def _display_order_id(value: Any) -> str:
    if isinstance(value, list):
        return ", ".join(_safe_text(item) for item in value if _safe_text(item))
    return _safe_text(value)


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
    LINE_HEADERS = ["订单行ID", "SKU", "尺码", "颜色", "计划数量", "状态"]
    LOT_HEADERS = ["关联订单ID", "批次ID", "开始时间", "产线编号", "进度", "状态"]

    def __init__(
        self,
        order_header: Dict[str, Any],
        order_lines: List[Dict[str, Any]],
        lots: List[Dict[str, Any]],
        imports_api: Any,
        parent: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.imports_api = imports_api
        self.order_id = _safe_text(order_header.get("order_id"))
        self.order_lines = [line for line in order_lines if isinstance(line, dict)]
        self.lots = [lot for lot in lots if isinstance(lot, dict)]
        self.selected_lot_id = ""
        self.result_data: Optional[Dict[str, Any]] = None

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

        btn_close = QtWidgets.QPushButton("取消")
        btn_close.setStyleSheet(SECONDARY_BUTTON_STYLE)
        btn_close.clicked.connect(self.reject)
        header_layout.addWidget(btn_close)
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
        return [
            _order_line_id(line),
            line.get("sku", ""),
            line.get("size", ""),
            line.get("color", ""),
            line.get("quantity_planned", ""),
            line.get("status", ""),
        ]

    def _lot_row(self, lot: Dict[str, Any]) -> List[Any]:
        return [
            lot.get("order_id", ""),
            lot.get("lot_id", ""),
            _ms_to_datetime(lot.get("start_time_ms")),
            lot.get("production_line_id", ""),
            lot.get("progress", ""),
            lot.get("status", ""),
        ]

    def _load_order_lines(self) -> None:
        _fill_table(self.tblOrderLines, [self._line_row(line) for line in self.order_lines])

    def _load_lots(self) -> None:
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
        lot_id = ""
        lot_order_id = ""
        if selected_lot:
            lot_id = _safe_text(selected_lot.get("lot_id"))
            lot_order_id = _safe_text(selected_lot.get("order_id"))
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

        try:
            response = self.imports_api.import_lines_to_lot(
                self.order_id,
                line_ids,
                lot_id=lot_id or None,
            )
        except BackendError as exc:
            self._set_status(f"导入失败：{exc}", is_error=True)
            return

        resolved_lot_id = _safe_text(response.get("lot_id") or response.get("id"))
        self.result_data = {
            "order_id": self.order_id,
            "selected_line_ids": line_ids,
            "lot_id": resolved_lot_id or lot_id,
            "created_new": not bool(lot_id),
        }
        self.accept()


class LotDetailDialog(QtWidgets.QDialog):
    LINE_HEADERS = ["订单行ID", "SKU", "尺码", "颜色", "计划数量", "状态"]

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

        self.lot_id = _safe_text(lot_header.get("lot_id") or lot_summary.get("lot_id"))
        self.order_id = _display_order_id(
            lot_header.get("source_order_id")
            or lot_header.get("order_id")
            or lot_summary.get("source_order_id")
            or lot_summary.get("order_id")
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
        self.btnNext.setStyleSheet(PRIMARY_BUTTON_STYLE)
        self.btnNext.clicked.connect(self.start_separation)
        button_row.addWidget(self.btnNext)
        if not self.allow_next_step:
            self.btnNext.hide()

        root.addLayout(button_row)

    def _load_summary(self) -> None:
        header = self.lot_header if isinstance(self.lot_header, dict) else {}
        summary = self.lot_summary if isinstance(self.lot_summary, dict) else {}

        self.lblLotId.setText(_safe_text(header.get("lot_id") or summary.get("lot_id")))
        self.lblOrderId.setText(
            _display_order_id(
                header.get("source_order_id")
                or header.get("order_id")
                or summary.get("source_order_id")
                or summary.get("order_id")
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
                    _order_line_id(line),
                    line.get("sku", ""),
                    line.get("size", ""),
                    line.get("color", ""),
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
            self.lblFeedback.setText(f"{self.lblFeedback.text()}\n候选批次单仅支持查看详情与校验结果。")

    def start_separation(self) -> None:
        if not self.allow_next_step:
            self.lblFeedback.setText("候选批次单不可进入下游页面。")
            return
        if not self.order_id:
            self.lblFeedback.setText("当前批次缺少关联订单ID。")
            return
        
        

        self.next_request = {
            "lot_id": self.lot_id,
            "order_id": self.order_id,
        }
        self.accept()


class ImportPage(QtWidgets.QWidget):
    ORDER_HEADERS = ["订单ID", "客户ID", "下单日期", "交付日期", "进度", "状态"]
    LOT_HEADERS = ["关联订单ID", "批次ID", "开始时间", "产线编号", "进度", "状态"]

    def __init__(self, controller):
        super().__init__()
        uic.loadUi(str(Path(__file__).resolve().parent / "forms" / "import_page.ui"), self)

        self.controller = controller
        self.imports_api = controller.backend.imports
        self.order_rows: List[Dict[str, Any]] = []
        self.lot_rows: List[Dict[str, Any]] = []
        self.persisted_lot_rows: List[Dict[str, Any]] = []
        self.pending_lot_rows: List[Dict[str, Any]] = []
        self.pending_validation_results: Dict[str, Dict[str, Any]] = {}
        self.last_feedback_text = "请先通过“本地导入”读取生产订单。"

        self._setup_ui()
        self.refresh_data()

    def _setup_ui(self) -> None:
        _setup_table(self.tblProductionOrders, self.ORDER_HEADERS)
        _setup_table(self.tblBatchOrders, self.LOT_HEADERS)

        self.tblProductionOrders.cellDoubleClicked.connect(self.on_order_double_clicked)
        self.tblBatchOrders.cellDoubleClicked.connect(self.on_lot_double_clicked)

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

    def refresh_data(self) -> None:
        self.load_orders()
        self.load_lots()

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

    def _row_order_display(self, lot: Dict[str, Any]) -> str:
        return _display_order_id(lot.get("source_order_id") or lot.get("order_id"))

    def _format_validation_summary(self, summary: Dict[str, Any]) -> str:
        lot_id = _safe_text(summary.get("lot_id"))
        passed = summary.get("passed")
        errors = summary.get("errors", [])
        risk_info = summary.get("risk_info", [])
        return (
            f"- 批次ID：{lot_id or '未命名候选批次'}\n"
            f"  passed: {passed}\n"
            f"  errors: {errors}\n"
            f"  risk_info: {risk_info}"
        )

    def _build_persisted_lot_row(self, lot: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "row_kind": "persisted",
            "order_id_display": self._row_order_display(lot),
            "lot_id": _safe_text(lot.get("lot_id")),
            "start_time_ms": lot.get("start_time_ms"),
            "production_line_id": _safe_text(lot.get("production_line_id")),
            "progress": lot.get("progress", ""),
            "status": _safe_text(lot.get("status")),
            "lot_header": dict(lot),
            "lot_line": [],
            "validation_summary": {},
        }

    def _build_pending_lot_row(self, candidate: Dict[str, Any]) -> Dict[str, Any]:
        header = candidate.get("lot_header")
        lines = candidate.get("lot_line")
        if not isinstance(header, dict) or not isinstance(lines, list):
            raise BackendError("候选批次单结构无效。")
        lot_id = _safe_text(header.get("lot_id"))
        validation_summary = self.pending_validation_results.get(lot_id, {})
        status = "candidate"
        if validation_summary:
            status = "candidate | validated" if validation_summary.get("passed") else "candidate | invalid"
        return {
            "row_kind": "pending",
            "order_id_display": _display_order_id(header.get("source_order_id") or header.get("order_id")),
            "lot_id": lot_id,
            "start_time_ms": header.get("start_time_ms"),
            "production_line_id": _safe_text(header.get("production_line_id")),
            "progress": header.get("progress", ""),
            "status": status,
            "lot_header": header,
            "lot_line": _as_list(lines),
            "validation_summary": validation_summary,
        }

    def rebuild_lot_rows(self) -> None:
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

    def load_orders(self) -> None:
        try:
            payload = self.imports_api.list_orders()
            self.order_rows = _orders(payload)
        except BackendError as exc:
            self.order_rows = []
            self.tblProductionOrders.setRowCount(0)
            if "请先通过" not in self.last_feedback_text:
                self.set_feedback(f"{self.last_feedback_text}\n\n订单列表刷新失败：{exc}")
            return

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

    def load_lots(self) -> None:
        try:
            payload = self.imports_api.list_lots()
            self.persisted_lot_rows = _lots(payload)
        except BackendError as exc:
            self.persisted_lot_rows = []
            self.lot_rows = []
            self.tblBatchOrders.setRowCount(0)
            if "请先通过" not in self.last_feedback_text:
                self.set_feedback(f"{self.last_feedback_text}\n\n批次列表刷新失败：{exc}")
            return
        self.rebuild_lot_rows()

    def sync_with_erp(self) -> None:
        self.set_feedback("ERP 暂未接入，当前仅支持本地导入。")

    def import_order(self) -> None:
        file_path_text, _ = QFileDialog.getOpenFileName(self, "选择生产订单", "", "XML Files (*.xml)")
        if not file_path_text:
            return

        xml_bytes = Path(file_path_text).read_bytes()

        try:
            response = self.imports_api.import_local_order(xml_bytes)
        except BackendError as exc:
            self.set_feedback(f"导入订单出现异常：{exc}")
            return

        if response.get("passed") is False:
            self.set_feedback(
                f"订单导入未通过。\n错误：{response.get('errors', [])}\n风险：{response.get('risks', [])}"
            )
            return

        self.set_feedback("成功导入生产订单。")
        self.refresh_data()

    def on_order_double_clicked(self, row: int, column: int) -> None:
        del column
        if row >= len(self.order_rows):
            return

        order = self.order_rows[row]
        order_id = _safe_text(order.get("order_id"))
        if not order_id:
            QMessageBox.warning(self, "订单缺失", "当前订单缺少订单ID，无法查询订单行。")
            return

        try:
            payload = self.imports_api.get_order(order_id)
        except BackendError as exc:
            QMessageBox.critical(self, "获取订单详情失败", str(exc))
            return

        _, order_lines = _parse_order_detail(payload)
        if not order_lines:
            QMessageBox.information(self, "无可分配订单行", f"订单 {order_id} 当前无可分配订单行。")
            return

        if not self.persisted_lot_rows:
            self.load_lots()

        dialog = OrderLineAssignDialog(
            order_header=order,
            order_lines=order_lines,
            lots=self.persisted_lot_rows,
            imports_api=self.imports_api,
            parent=self,
        )
        if dialog.exec_() != QtWidgets.QDialog.Accepted or not dialog.result_data:
            return

        result = dialog.result_data
        self.refresh_data()
        action_text = "新建批次" if result.get("created_new") else "导入已有批次"
        self.set_feedback(
            "订单行导入完成：\n"
            f"- 订单ID：{result.get('order_id', '')}\n"
            f"- 订单行ID：{result.get('selected_line_ids', [])}\n"
            f"- 目标批次：{result.get('lot_id', '')}\n"
            f"- 操作类型：{action_text}"
        )

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
                allow_next_step=False,
                parent=self.controller,
            )
            dialog.exec_()
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
            allow_next_step=True,
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

        order_header, order_lines = _parse_order_detail(order_payload)
        lot_context = {"lot_header": lot_header, "lot_line": lot_lines}
        order_context = {"order_header": order_header, "order_line": order_lines}
        self.controller.context["current_lot"] = lot_payload
        self.controller.context["current_order"] = order_payload
        self.controller.context["current_lot_id"] = _safe_text(dialog.next_request.get("lot_id"))
        self.controller.context["current_order_id"] = order_id
        self.controller.context["lot_context"] = lot_context
        self.controller.context["order_context"] = order_context
        self.controller.context.setdefault("process_plan_context", {})
        self.controller.context.setdefault("process_route_context", {})
        self.controller.context.setdefault("constraint_context", {})
        self.controller.show_page("separation_page")

    def ai_optimize_lots(self) -> None:
        order_ids = self._selected_order_ids()
        if not order_ids:
            self.set_feedback("请先在生产订单表中选择至少一条生产订单。")
            return

        try:
            response = self.imports_api.generate_lots(selected_orders=order_ids)
        except BackendError as exc:
            self.set_feedback(f"候选批次单生成失败：{exc}")
            return

        lots = _as_list(response.get("lots"))
        self.pending_lot_rows = lots
        self.pending_validation_results = {}
        self.rebuild_lot_rows()

        summary_lines = [
            "候选批次单生成完成：",
            f"- 订单ID：{order_ids}",
            f"- passed：{response.get('passed')}",
            f"- message：{response.get('message', '')}",
            f"- 候选批次数量：{len(lots)}",
        ]
        for candidate in lots:
            header = candidate.get("lot_header", {})
            lines = _as_list(candidate.get("lot_line"))
            summary_lines.append(
                (
                    f"- lot_id：{_safe_text(header.get('lot_id')) or '未命名候选批次'}，"
                    f" source_order_id：{_display_order_id(header.get('source_order_id') or header.get('order_id'))}，"
                    f" line_count：{len(lines)}"
                )
            )
        self.set_feedback("\n".join(summary_lines))

    def ai_validate_lots(self) -> None:
        if not self.pending_lot_rows:
            self.set_feedback("当前无候选批次单可校验。")
            return

        pending_lots = []
        for candidate in self.pending_lot_rows:
            header = candidate.get("lot_header")
            lines = candidate.get("lot_line")
            if not isinstance(header, dict) or not isinstance(lines, list):
                self.set_feedback("候选批次单结构无效，无法发起校验。")
                return
            pending_lots.append({"lot_header": header, "lot_line": _as_list(lines)})

        try:
            response = self.imports_api.validate_lots(pending_lots=pending_lots)
        except BackendError as exc:
            self.set_feedback(f"候选批次单校验失败：{exc}")
            return

        results = _as_list(response.get("validation_results"))
        self.pending_validation_results = {
            _safe_text(item.get("lot_id")): item for item in results if _safe_text(item.get("lot_id"))
        }
        self.rebuild_lot_rows()

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

    def refresh_lot_list(self) -> None:
        _filter_table(self.tblBatchOrders, self.txtSearch.text())
