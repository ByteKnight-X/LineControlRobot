import os
import unittest
from unittest.mock import Mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5 import QtWidgets

from separation_page import (
    SeparationPage,
    _build_svg_html,
    _looks_like_svg_content,
    _normalize_svg_markup,
)
from utilities.backend_client import BackendClient, BackendError, ProcessPlanRoutes


class ProcessPlanBackendClientContractTest(unittest.TestCase):
    def test_process_plan_list_normalizes_sizes(self) -> None:
        client = BackendClient("http://127.0.0.1:18000")
        client._get_json = Mock(
            return_value={
                "process_plans": [
                    {
                        "process_plan_id": "PP-1",
                        "process_plan_version": 3,
                        "sku": "SKU-1",
                        "sizes": [42, 43],
                        "color": "Orange",
                        "validated_by": "tester",
                        "status": "validated",
                    }
                ]
            }
        )

        result = client.process_plans.list()

        self.assertEqual(result[0]["sizes"], [42, 43])
        client._get_json.assert_called_once_with(ProcessPlanRoutes.LIST)

    def test_process_plan_validate_normalizes_validation_issues(self) -> None:
        client = BackendClient("http://127.0.0.1:18000")
        client._post_json = Mock(
            return_value={
                "passed": False,
                "errors": [{"field": "sizes", "message": "required"}],
                "risks": [{"field": "pattern_design", "message": "missing preview"}],
                "status": "created",
            }
        )

        result = client.process_plans.validate({"process_plan_header": {}, "process_plan_line": []})

        self.assertEqual(result["errors"], ["sizes: required"])
        self.assertEqual(result["risks"], ["pattern_design: missing preview"])

    def test_process_plan_approve_requires_expected_fields(self) -> None:
        client = BackendClient("http://127.0.0.1:18000")
        client._post_json = Mock(return_value={"approved": True})

        with self.assertRaises(BackendError):
            client.process_plans.approve({"process_plan_header": {}, "process_plan_line": []})


class _FakeProcessPlanApi:
    def list(self):
        return []

    def detail(self, process_plan_id, process_plan_version):
        del process_plan_id, process_plan_version
        return {}

    def validate(self, payload):
        del payload
        return {"passed": True, "errors": [], "risks": [], "status": "validated"}

    def approve(self, payload):
        del payload
        return {
            "approved": True,
            "process_plan_id": "PP-1",
            "process_plan_version": 1,
            "errors": [],
            "risks": [],
            "status": "validated",
        }


class _FakeController(QtWidgets.QWidget):
    def __init__(self, context=None):
        super().__init__()
        self.context = context or {}
        self.backend = type("Backend", (), {"process_plans": _FakeProcessPlanApi()})()
        self.last_page = None

    def show_page(self, page_name):
        self.last_page = page_name


class SeparationPageContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def test_refresh_data_uses_sizes_and_marks_persisted_plan_frozen(self) -> None:
        controller = _FakeController(
            {
                "process_plan_context": {
                    "process_plan_header": {
                        "process_plan_id": "PP-1",
                        "process_plan_version": 3,
                        "sku": "SKU-1",
                        "sizes": [42, 43],
                        "color": "Orange",
                        "validated_by": "tester",
                        "status": "validated",
                    },
                    "process_plan_line": [],
                }
            }
        )

        page = SeparationPage(controller)

        self.assertEqual(page.txtCodeRange.text(), "42,43")
        self.assertEqual(page.txtColorway.text(), "Orange")
        self.assertEqual(page.page_state["page_status"], "Frozen")

    def test_build_payload_uses_sizes_not_legacy_size(self) -> None:
        controller = _FakeController(
            {
                "process_plan_context": {
                    "process_plan_header": {
                        "sku": "SKU-1",
                        "sizes": [42, 43],
                        "color": "Orange",
                        "validated_by": "tester",
                        "status": "draft",
                    },
                    "process_plan_line": [
                        {
                            "mesh_index": 1,
                            "pattern_design": "demo.svg",
                            "material": "PET",
                            "mesh_model": "N-120",
                            "diameter": "120",
                            "stretching": "直拉",
                            "stretching_degree": 0,
                            "tpi": 180,
                            "tension": 180,
                            "frame_specification": "420 x 520",
                            "operation": "SOP",
                        }
                    ],
                }
            }
        )

        page = SeparationPage(controller)
        payload = page._build_payload()

        self.assertEqual(payload["process_plan_header"]["sizes"], [42, 43])
        self.assertNotIn("size", payload["process_plan_header"])
        self.assertEqual(payload["process_plan_line"][0]["sizes"], "42,43")

    def test_svg_content_detection_accepts_inline_svg(self) -> None:
        self.assertTrue(_looks_like_svg_content("<?xml version='1.0'?><svg></svg>"))
        self.assertTrue(_looks_like_svg_content("<svg viewBox='0 0 10 10'></svg>"))
        self.assertFalse(_looks_like_svg_content("resource/layers/demo.svg"))

    def test_build_svg_html_wraps_content_with_expected_shell(self) -> None:
        html = _build_svg_html("<svg viewBox='0 0 10 10'></svg>")
        self.assertIn("<div class=\"svg-host\">", html)
        self.assertIn("background: #fafafa;", html)
        self.assertIn("<svg viewBox='0 0 10 10'></svg>", html)

    def test_normalize_svg_markup_strips_xml_header(self) -> None:
        normalized = _normalize_svg_markup(
            "<?xml version='1.0' encoding='utf-8'?>\n<svg viewBox='0 0 10 10'></svg>"
        )
        self.assertEqual(normalized, "<svg viewBox='0 0 10 10'></svg>")

    def test_normalize_svg_markup_rejects_invalid_svg(self) -> None:
        self.assertEqual(_normalize_svg_markup("<?xml version='1.0'?>"), "")


if __name__ == "__main__":
    unittest.main()
