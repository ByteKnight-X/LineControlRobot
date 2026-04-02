import os
import unittest
from pathlib import Path
from unittest.mock import Mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5 import QtWidgets

import import_page as import_page_module
from import_page import ImportPage
from utilities.backend_client import BackendClient, BackendError, ImportRoutes


class _FakeImportsApi:
    def __init__(self) -> None:
        self.generate_response = {
            "passed": True,
            "message": "ok",
            "lots": [],
        }
        self.validate_response = {
            "validation_results": [],
        }
        self.raise_list_orders = False
        self.raise_list_lots = False
        self.raise_get_lot_ids = set()
        self.order_status = "created"
        self.lot_status = "released"
        self.lot_source_order_id = ["PO-OLD"]
        self.list_orders_calls = 0
        self.list_lots_calls = 0
        self.get_order_calls = 0

    def list_orders(self):
        self.list_orders_calls += 1
        if self.raise_list_orders:
            raise BackendError("orders unavailable")
        return {
            "production_order_list": [
                {
                    "production_order_header": {
                        "order_id": "PO-1",
                        "client_id": "C1",
                        "date_ms": 1711267200000,
                        "delivery_date_ms": 1711353600000,
                        "progress": 0,
                        "status": self.order_status,
                    },
                    "production_order_line": [
                        {
                            "order_line_id": 1,
                            "order_id": "PO-1",
                            "sku": "SKU-1",
                            "size": "43",
                            "color": "Orange",
                            "quantity_planned": 10,
                            "status": "created",
                        }
                    ],
                }
            ]
        }

    def list_lots(self):
        self.list_lots_calls += 1
        if self.raise_list_lots:
            raise BackendError("lots unavailable")
        return {
            "lots": [
                {
                    "order_id": "PO-OLD",
                    "lot_id": "LOT-OLD",
                    "start_time_ms": 1711267200000,
                    "production_line_id": "F01-SP01",
                    "progress": 50,
                    "status": self.lot_status,
                }
            ]
        }

    def get_order(self, order_id):
        self.get_order_calls += 1
        return {"header": {"order_id": order_id}, "lines": []}

    def get_lot(self, lot_id):
        if lot_id in self.raise_get_lot_ids:
            raise BackendError(f"lot detail unavailable: {lot_id}")
        return {
            "header": {
                "lot_id": lot_id,
                "source_order_id": self.lot_source_order_id,
                "production_line_id": "F01-SP01",
                "progress": 50,
                "status": self.lot_status,
            },
            "lines": [],
        }

    def import_local_order(self, xml_bytes):
        del xml_bytes
        return {"passed": True, "errors": [], "risks": []}

    def import_lines_to_lot(self, order_id, selected_order_line_ids, lot_id=None):
        raise AssertionError("not used")

    def generate_lots(self, selected_orders, excluded_order_lines=None):
        self.last_generate_orders = list(selected_orders)
        self.last_excluded_order_lines = list(excluded_order_lines or [])
        return self.generate_response

    def validate_lots(self, pending_lots):
        self.last_validate_payload = pending_lots
        return self.validate_response


class _FakeController(QtWidgets.QWidget):
    def __init__(self, imports_api):
        super().__init__()
        self.context = {}
        self.backend = type(
            "Backend",
            (),
            {"imports": imports_api, "base_url": "http://127.0.0.1:18000"},
        )()
        self.last_page = None

    def show_page(self, page_name):
        self.last_page = page_name


class BackendClientContractTest(unittest.TestCase):
    def test_generate_lots_uses_new_route_and_payload(self):
        client = BackendClient("http://127.0.0.1:18000")
        client._post_json = Mock(
            return_value={
                "passed": True,
                "message": "ok",
                "lots": [
                    {
                        "lot_header": {
                            "lot_id": "LOT-1",
                            "source_order_id": "PO-1",
                            "production_line_id": "F01-SP01",
                            "status": "created",
                        },
                        "lot_line": [
                            {
                                "lot_id": "LOT-1",
                                "lot_line_id": 1,
                                "source_order_id": "PO-1",
                                "source_order_line_id": 1,
                                "sku": "SKU-1",
                                "color": "Orange",
                                "size": "43",
                                "quantity_planned": 10,
                                "status": "created",
                            }
                        ],
                    }
                ],
            }
        )

        result = client.imports.generate_lots(["PO-1"])

        self.assertTrue(result["passed"])
        client._post_json.assert_called_once_with(
            ImportRoutes.AI_GENERATE_LOTS,
            {"selected_orders": ["PO-1"]},
        )

    def test_validate_lots_uses_new_route_and_payload(self):
        client = BackendClient("http://127.0.0.1:18000")
        client._post_json = Mock(
            return_value={
                "validation_results": [
                    {"lot_id": "LOT-1", "passed": True, "errors": [], "risk_info": []}
                ]
            }
        )

        payload = [{"lot_header": {"lot_id": "LOT-1"}, "lot_line": []}]
        result = client.imports.validate_lots(payload)

        self.assertEqual(result["validation_results"][0]["lot_id"], "LOT-1")
        client._post_json.assert_called_once_with(
            ImportRoutes.AI_VALIDATE_LOTS,
            {"pending_lots": payload},
        )

    def test_generate_lots_rejects_invalid_structure(self):
        client = BackendClient("http://127.0.0.1:18000")
        client._post_json = Mock(return_value={"lots": [{"header": {}}]})

        with self.assertRaises(BackendError):
            client.imports.generate_lots(["PO-1"])


class ImportPageAiFlowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        cls.xml_path = Path(__file__).resolve().parents[1] / "resource" / "order_valid.xml"

    def setUp(self):
        self.imports_api = _FakeImportsApi()
        self.controller = _FakeController(self.imports_api)
        self.page = ImportPage(self.controller)

    def test_page_state_starts_empty_until_erp_sync(self):
        self.assertEqual(self.page.page_state["data"]["db_orders"], [])
        self.assertEqual(self.page.page_state["data"]["db_lots"], [])
        self.assertEqual(self.page.order_rows, [])
        self.assertEqual(self.page.lot_rows, [])
        self.assertFalse(self.page.page_state["dirty"])
        self.assertEqual(self.page.page_state["validation_summary"]["errors"], [])

    def test_refresh_data_rebuilds_tables_from_page_state_only(self):
        self.page.page_state["data"]["db_orders"] = self.imports_api.list_orders()["production_order_list"]
        self.page.page_state["data"]["db_lots"] = self.imports_api.list_lots()["lots"]
        before_order_calls = self.imports_api.list_orders_calls
        before_lot_calls = self.imports_api.list_lots_calls

        self.page.refresh_data()

        self.assertEqual(self.page.order_rows[0]["order_id"], "PO-1")
        self.assertEqual(self.page.lot_rows[0]["lot_id"], "LOT-OLD")
        self.assertEqual(self.imports_api.list_orders_calls, before_order_calls)
        self.assertEqual(self.imports_api.list_lots_calls, before_lot_calls)

    def test_sync_with_erp_updates_page_state_and_feedback(self):
        self.page.sync_with_erp()

        self.assertEqual(
            self.page.page_state["data"]["db_orders"][0]["production_order_header"]["order_id"],
            "PO-1",
        )
        self.assertEqual(self.page.page_state["data"]["db_lots"][0]["lot_header"]["lot_id"], "LOT-OLD")
        self.assertEqual(self.page.order_rows[0]["order_id"], "PO-1")
        self.assertEqual(self.page.lot_rows[0]["order_id_display"], "PO-OLD")
        self.assertIn("同步完成（来源：后端数据库）", self.page.last_feedback_text)
        self.assertIn("raw_orders：1", self.page.last_feedback_text)
        self.assertIn("display_lots：1", self.page.last_feedback_text)
        self.assertFalse(self.page.page_state["loading"])

    def test_sync_with_erp_partial_failure_keeps_existing_rows(self):
        self.page.sync_with_erp()
        self.imports_api.raise_list_orders = True
        original_orders = list(self.page.page_state["data"]["db_orders"])
        original_lots = list(self.page.page_state["data"]["db_lots"])

        self.page.sync_with_erp()

        self.assertEqual(self.page.page_state["data"]["db_orders"], original_orders)
        self.assertEqual(self.page.page_state["data"]["db_lots"], original_lots)
        self.assertIn("ERP 同步部分失败", self.page.last_feedback_text)
        self.assertIn("订单同步失败", self.page.last_feedback_text)
        self.assertFalse(self.page.page_state["loading"])

    def test_sync_with_erp_lot_failure_keeps_existing_rows(self):
        self.page.sync_with_erp()
        self.imports_api.raise_list_lots = True
        original_orders = list(self.page.page_state["data"]["db_orders"])
        original_lots = list(self.page.page_state["data"]["db_lots"])

        self.page.sync_with_erp()

        self.assertEqual(self.page.page_state["data"]["db_orders"], original_orders)
        self.assertEqual(self.page.page_state["data"]["db_lots"], original_lots)
        self.assertIn("批次同步失败", self.page.last_feedback_text)
        self.assertFalse(self.page.page_state["loading"])

    def test_sync_with_erp_keeps_unknown_status_rows_and_reports_them(self):
        self.imports_api.order_status = "draft"
        self.imports_api.lot_status = "pending"

        self.page.sync_with_erp()

        self.assertEqual(self.page.order_rows[0]["status"], "draft")
        self.assertEqual(self.page.lot_rows[0]["status"], "pending")
        self.assertIn("unknown_order_statuses：['draft']", self.page.last_feedback_text)
        self.assertIn("unknown_lot_statuses：['pending']", self.page.last_feedback_text)

    def test_sync_with_erp_reports_empty_database(self):
        self.imports_api.list_orders = lambda: {"production_order_list": []}
        self.imports_api.list_lots = lambda: {"lots": []}

        self.page.sync_with_erp()

        self.assertEqual(self.page.order_rows, [])
        self.assertEqual(self.page.lot_rows, [])
        self.assertIn("当前后端数据库无订单/批次数据", self.page.last_feedback_text)

    def test_sync_with_erp_reports_lot_detail_failures_without_dropping_other_lots(self):
        def _list_lots():
            return {
                "lots": [
                    {"lot_id": "LOT-OK", "status": "released"},
                    {"lot_id": "LOT-BAD", "status": "released"},
                ]
            }

        self.imports_api.list_lots = _list_lots
        self.imports_api.raise_get_lot_ids = {"LOT-BAD"}

        self.page.sync_with_erp()

        self.assertEqual([row["lot_id"] for row in self.page.lot_rows], ["LOT-OK"])
        self.assertIn("lot_detail_failures：['LOT-BAD']", self.page.last_feedback_text)

    def test_ai_optimize_lots_updates_pending_and_combined_rows(self):
        self.page.sync_with_erp()
        self.imports_api.generate_response = {
            "passed": True,
            "message": "generated",
            "lots": [
                {
                    "lot_header": {
                        "lot_id": "LOT-C1",
                        "source_order_id": "PO-1",
                        "production_line_id": "F01-SP01",
                        "status": "created",
                    },
                    "lot_line": [
                        {
                            "lot_id": "LOT-C1",
                            "lot_line_id": 1,
                            "source_order_id": "PO-1",
                            "source_order_line_id": 1,
                            "sku": "SKU-1",
                            "color": "Orange",
                            "size": "43",
                            "quantity_planned": 10,
                            "status": "created",
                        }
                    ],
                }
            ],
        }
        self.page.tblProductionOrders.selectRow(0)

        self.page.ai_optimize_lots()

        self.assertEqual(self.imports_api.last_generate_orders, ["PO-1"])
        self.assertEqual(len(self.page.pending_lot_rows), 1)
        self.assertEqual(len(self.page.lot_rows), 2)
        self.assertEqual(self.page.lot_rows[1]["row_kind"], "pending")
        self.assertEqual(len(self.page.page_state["data"]["pending_lots"]), 1)
        self.assertTrue(self.page.page_state["dirty"])
        self.assertIn("候选批次单生成完成", self.page.last_feedback_text)

    def test_ai_validate_lots_updates_pending_validation_results(self):
        self.page.sync_with_erp()
        self.imports_api.generate_response = {
            "passed": True,
            "message": "generated",
            "lots": [
                {
                    "lot_header": {
                        "lot_id": "LOT-C1",
                        "source_order_id": "PO-1",
                        "production_line_id": "F01-SP01",
                        "status": "created",
                    },
                    "lot_line": [
                        {
                            "lot_id": "LOT-C1",
                            "lot_line_id": 1,
                            "source_order_id": "PO-1",
                            "source_order_line_id": 1,
                            "sku": "SKU-1",
                            "color": "Orange",
                            "size": "43",
                            "quantity_planned": 10,
                            "status": "created",
                        }
                    ],
                }
            ],
        }
        self.imports_api.validate_response = {
            "validation_results": [
                {
                    "lot_id": "LOT-C1",
                    "passed": False,
                    "errors": ["line conflict"],
                    "risk_info": ["line load high"],
                }
            ]
        }
        self.page.tblProductionOrders.selectRow(0)
        self.page.ai_optimize_lots()

        self.page.ai_validate_lots()

        self.assertIn("LOT-C1", self.page.pending_validation_results)
        self.assertEqual(self.page.lot_rows[1]["status"], "created")
        self.assertIn("risk_info", self.page.last_feedback_text)
        self.assertFalse(self.page.page_state["dirty"])
        self.assertFalse(self.page.page_state["validation_summary"]["passed"])
        self.assertEqual(self.page.page_state["validation_summary"]["errors"], ["line conflict"])
        self.assertEqual(self.page.page_state["validation_summary"]["risks"], ["line load high"])

    def test_ai_validate_lots_rejects_empty_results(self):
        self.page.sync_with_erp()
        self.imports_api.generate_response = {
            "passed": True,
            "message": "generated",
            "lots": [
                {
                    "lot_header": {
                        "lot_id": "LOT-C1",
                        "source_order_id": "PO-1",
                        "production_line_id": "F01-SP01",
                        "status": "created",
                    },
                    "lot_line": [
                        {
                            "lot_id": "LOT-C1",
                            "lot_line_id": 1,
                            "source_order_id": "PO-1",
                            "source_order_line_id": 1,
                            "sku": "SKU-1",
                            "color": "Orange",
                            "size": "43",
                            "quantity_planned": 10,
                            "status": "created",
                        }
                    ],
                }
            ],
        }
        self.imports_api.validate_response = {"validation_results": []}
        self.page.tblProductionOrders.selectRow(0)
        self.page.ai_optimize_lots()

        self.page.ai_validate_lots()

        self.assertIn("validation_results 为空", self.page.last_feedback_text)

    def test_generate_lots_invalid_structure_is_explicit(self):
        self.page.sync_with_erp()
        self.imports_api.generate_response = {
            "passed": True,
            "message": "generated",
            "lots": [{"lot_header": {"lot_id": "LOT-C1"}, "lot_line": []}],
        }
        self.page.tblProductionOrders.selectRow(0)

        self.page.ai_optimize_lots()

        self.assertIn("production_line_id", self.page.last_feedback_text)

    def test_manual_assign_clears_pending_candidate_state(self):
        original_dialog = import_page_module.OrderLineAssignDialog

        class _DialogStub:
            def __init__(self, *args, **kwargs):
                del args, kwargs
                self.result_data = {
                    "order_id": "PO-1",
                    "selected_line_ids": [1, 2],
                    "lot_id": "LOT-NEW",
                    "created_new_lot": True,
                    "status": "created",
                    "line_count": 2,
                }

            def exec_(self):
                return QtWidgets.QDialog.Accepted

        try:
            import_page_module.OrderLineAssignDialog = _DialogStub
            self.page.sync_with_erp()
            self.page.page_state["data"]["pending_lots"] = [
                {
                    "lot_header": {
                        "lot_id": "LOT-C1",
                        "source_order_id": "PO-1",
                        "production_line_id": "F01-SP01",
                        "status": "created",
                    },
                    "lot_line": [
                        {
                            "lot_id": "LOT-C1",
                            "lot_line_id": 1,
                            "source_order_id": "PO-1",
                            "source_order_line_id": 1,
                            "sku": "SKU-1",
                            "color": "Orange",
                            "size": "43",
                            "quantity_planned": 10,
                            "status": "created",
                        }
                    ],
                }
            ]
            self.page.refresh_data()
            self.page.tblProductionOrders.selectRow(0)
            self.page.pending_validation_results = {"LOT-C1": {"passed": True}}

            self.page.on_order_double_clicked(0, 0)

            self.assertEqual(len(self.page.pending_lot_rows), 1)
            self.assertEqual(self.page.pending_validation_results, {})
            self.assertTrue(self.page.page_state["dirty"])
            self.assertEqual(self.page.page_state["focus"]["selected_order_lines"], [1, 2])
            self.assertIn("状态：created", self.page.last_feedback_text)
            self.assertIn("批次行数量：2", self.page.last_feedback_text)
        finally:
            import_page_module.OrderLineAssignDialog = original_dialog

    def test_import_order_writes_pending_orders_without_refreshing_db(self):
        original_get_open_file_name = import_page_module.QFileDialog.getOpenFileName
        try:
            import_page_module.QFileDialog.getOpenFileName = (
                lambda *args, **kwargs: (str(self.xml_path), "")
            )
            self.page.sync_with_erp()
            before_order_calls = self.imports_api.list_orders_calls
            before_lot_calls = self.imports_api.list_lots_calls

            self.page.import_order()

            self.assertEqual(len(self.page.page_state["data"]["pending_orders"]), 1)
            self.assertEqual(self.page.pending_order_rows[0]["order_id"], "PO-20260206-01")
            self.assertEqual(self.imports_api.list_orders_calls, before_order_calls)
            self.assertEqual(self.imports_api.list_lots_calls, before_lot_calls)
            self.assertTrue(self.page.page_state["dirty"])
            self.assertIn("已写入本地待处理订单", self.page.last_feedback_text)
            self.assertIn("passed：True", self.page.last_feedback_text)
            self.assertIn("errors：[]", self.page.last_feedback_text)
            self.assertIn("risks：[]", self.page.last_feedback_text)
            self.assertNotIn("order_id", self.page.last_feedback_text)
            self.assertNotIn("status", self.page.last_feedback_text)
        finally:
            import_page_module.QFileDialog.getOpenFileName = original_get_open_file_name

    def test_order_double_click_reads_detail_from_page_state(self):
        original_dialog = import_page_module.OrderLineAssignDialog

        class _DialogProbe:
            def __init__(self, order_header, order_lines, lots, imports_api, parent=None):
                del imports_api, parent
                self.order_header = order_header
                self.order_lines = order_lines
                self.lots = lots
                self.result_data = None

            def exec_(self):
                return QtWidgets.QDialog.Rejected

        try:
            import_page_module.OrderLineAssignDialog = _DialogProbe
            self.page.sync_with_erp()

            self.page.on_order_double_clicked(0, 0)

            self.assertEqual(self.imports_api.get_order_calls, 0)
        finally:
            import_page_module.OrderLineAssignDialog = original_dialog


if __name__ == "__main__":
    unittest.main()
