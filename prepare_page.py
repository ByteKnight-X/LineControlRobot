import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from PyQt5 import QtCore, QtWidgets, uic
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QMessageBox, QTableWidgetItem

from utilities.backend_client import BackendError
from utilities.prep_utils import (
    TAB_KEY_TO_FIELD,
    TAB_KEY_TO_TITLE,
    build_empty_prep_instruction_context,
    build_validation_feedback,
    identify_instruction_target,
    normalize_prep_instruction_context,
    parse_instruction_text,
    safe_int as _safe_int,
    safe_text as _safe_text,
    status_to_text,
    summarize_risk_text,
    to_pretty_json,
)


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
        self._last_selected_row: Optional[int] = None
        self.page_state = self._build_initial_page_state()
        self._bind_events()
        self._restore_or_create_context()
        self._render_page()

    def refresh_data(self) -> None:
        self._restore_or_create_context()
        self._render_page()

    def _build_initial_page_state(self) -> Dict[str, Any]:
        return {
            "page_status": "created",
            "loading": False,
            "dirty": False,
            "active_tab": "mesh_prep",
            "active_target_id": "",
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
        self.txtSearchObject.textChanged.connect(self._filter_object_list)
        self.lblViewRisk.setCursor(Qt.PointingHandCursor)
        self.lblViewRisk.mousePressEvent = self._show_risks  # type: ignore[assignment]

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
        self.page_state["validation_summary"] = self.page_state.get("validation_summary") or {
            "passed": False,
            "errors": [],
            "risks": [],
        }

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
        item = self.listObjects.currentItem()
        if item is None:
            return -1
        index = item.data(Qt.UserRole)
        return index if isinstance(index, int) else -1

    def _save_current_editor(self) -> bool:
        index = self._selected_line_index()
        if index < 0:
            return True
        lines = self._current_lines()
        if index >= len(lines):
            return True
        text = self.txtInstructionContent.toPlainText().strip()
        if not text:
            return True
        try:
            parsed = parse_instruction_text(text)
        except (ValueError, json.JSONDecodeError) as exc:
            QMessageBox.warning(self, "指令内容", f"当前指令内容不是合法 JSON，请修正后再继续。\n{exc}")
            self.txtInstructionContent.setFocus()
            return False
        self.page_state["active_target_id"] = identify_instruction_target(parsed, index)
        existing_line = lines[index]
        if parsed != existing_line:
            lines[index] = parsed
            self.page_state["dirty"] = True
            if self.page_state["page_status"] in {"validated", "released"}:
                self.page_state["page_status"] = "created"
                self.page_state["current_instruction_set"]["prep_instruction_header"]["status"] = "created"
            self._sync_context()
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
            self.listObjects.setCurrentRow(visible_row)

    def _on_object_changed(self, row: int) -> None:
        if self._updating_widgets:
            return
        if row == self._last_selected_row:
            return
        if self._last_selected_row is not None and not self._save_current_editor():
            self._updating_widgets = True
            self.listObjects.setCurrentRow(self._last_selected_row)
            self._updating_widgets = False
            return
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
        self.listObjects.clear()
        for index, line in enumerate(lines):
            target_id = identify_instruction_target(line, index)
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
                self.page_state["active_target_id"] = identify_instruction_target(lines[0], 0)
        else:
            self.page_state["active_target_id"] = ""
        self._last_selected_row = selected_row if selected_row >= 0 else None
        if selected_row >= 0:
            self.listObjects.setCurrentRow(selected_row)
        self._filter_object_list()

    def _render_instruction_editor(self) -> None:
        lines = self._current_lines()
        index = self._selected_line_index()
        if index < 0 or index >= len(lines):
            title = f"对象：暂无{TAB_KEY_TO_TITLE[self.page_state['active_tab']]}"
            if not lines:
                title = f"对象：暂无对象，可先从版本库导入或直接提交空草稿。"
            self.lblInstructionTarget.setText(title)
            self.txtInstructionContent.setPlainText("")
            self.txtInstructionContent.setPlaceholderText("当前没有可编辑对象。")
            return
        current_line = lines[index]
        target_id = identify_instruction_target(current_line, index)
        self.page_state["active_target_id"] = target_id
        self.lblInstructionTarget.setText(f"对象：{target_id}")
        self.txtInstructionContent.setPlaceholderText("请使用合法 JSON 编辑当前对象。")
        self.txtInstructionContent.setPlainText(to_pretty_json(current_line))

    def _render_validation_panel(self) -> None:
        self.lblValidationFeedback.setText(build_validation_feedback(self.page_state["validation_summary"]))
