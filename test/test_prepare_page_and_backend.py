import unittest

from utilities.prep_utils import (
    build_empty_prep_instruction_context,
    build_validation_feedback,
    normalize_prep_instruction_context,
    parse_instruction_text,
    status_to_text,
    summarize_risk_text,
)
from utilities.backend_client import BackendClient, BackendError


def apply_validation_regression_rule(
    page_status: str,
    existing_line: dict,
    parsed_line: dict,
    dirty: bool = False,
):
    """Mirror prepare_page._save_current_editor state transition."""
    if parsed_line != existing_line:
        dirty = True
        if page_status in {"validated", "released"}:
            page_status = "created"
    return page_status, dirty


class PrepInstructionApiUnitTest(unittest.TestCase):
    def setUp(self) -> None:
        self.client = BackendClient(base_url="http://127.0.0.1:18000")
        self.api = self.client.prep_instructions

    def test_list_accepts_plain_list(self) -> None:
        self.client._get_data = lambda _path: [{"prep_instruction_id": "P1"}]
        result = self.api.list()
        self.assertEqual(result, [{"prep_instruction_id": "P1"}])

    def test_list_accepts_wrapped_list(self) -> None:
        self.client._get_data = lambda _path: {"prep_instructions": [{"prep_instruction_id": "P2"}]}
        result = self.api.list()
        self.assertEqual(result, [{"prep_instruction_id": "P2"}])

    def test_detail_normalizes_structure(self) -> None:
        self.client._get_json = lambda _path: {
            "prep_instruction_header": {"prep_instruction_id": "P1", "status": "created"},
            "mesh_prep_instruction_line": [{"screen_id": "S1"}],
            "ink_prep_instruction_line": [{"ink_id": "I1"}],
            "material_prep_instruction_line": [{"material_id": "M1"}],
            "equipment_prep_instruction_line": [{"equipment_id": "E1"}],
        }
        result = self.api.detail("P1", 1)
        self.assertEqual(result["prep_instruction_header"]["prep_instruction_id"], "P1")
        self.assertEqual(result["mesh_prep_instruction_line"][0]["screen_id"], "S1")

    def test_validate_requires_required_keys(self) -> None:
        self.client._post_json = lambda _path, _payload=None: {"passed": True}
        with self.assertRaises(BackendError):
            self.api.validate({})

    def test_distribute_defaults_status(self) -> None:
        self.client._post_json = lambda _path, _payload=None: {
            "passed": True,
            "errors": [],
            "risks": [],
            "prep_instruction_id": "P9",
            "prep_instruction_version": 3,
        }
        result = self.api.distribute({})
        self.assertEqual(result["status"], "released")


class PreparePageHelperUnitTest(unittest.TestCase):
    def test_build_empty_context_uses_upstream_context(self) -> None:
        context = build_empty_prep_instruction_context(
            {
                "lot_context": {"lot_header": {"lot_id": "LOT-1"}},
                "process_route_context": {
                    "process_route_header": {
                        "process_route_id": "ROUTE-1",
                        "process_route_version": 2,
                        "line_spec_id": "LINE-1",
                    }
                },
            }
        )
        header = context["prep_instruction_header"]
        self.assertEqual(header["lot_id"], "LOT-1")
        self.assertEqual(header["process_route_id"], "ROUTE-1")
        self.assertEqual(header["process_route_version"], 2)
        self.assertEqual(header["production_line_id"], "LINE-1")

    def test_normalize_prep_instruction_context_fills_defaults(self) -> None:
        result = normalize_prep_instruction_context({"prep_instruction_header": {"status": "validated"}})
        self.assertEqual(result["prep_instruction_header"]["status"], "validated")
        self.assertEqual(result["mesh_prep_instruction_line"], [])
        self.assertEqual(result["prep_instruction_header"]["prep_instruction_version"], 0)

    def test_parse_instruction_text_requires_json_object(self) -> None:
        parsed = parse_instruction_text('{"equipment_id": "EQ-1"}')
        self.assertEqual(parsed["equipment_id"], "EQ-1")
        with self.assertRaises(ValueError):
            parse_instruction_text("[1, 2, 3]")

    def test_status_and_risk_helpers(self) -> None:
        self.assertEqual(status_to_text("released"), "已下发")
        self.assertEqual(summarize_risk_text({"risks": ["a", "b"]}), "风险：2")

    def test_validation_feedback_contains_errors_and_risks(self) -> None:
        feedback = build_validation_feedback(
            {"passed": False, "errors": ["字段缺失"], "risks": ["设备冲突"]}
        )
        self.assertIn("未通过", feedback)
        self.assertIn("字段缺失", feedback)
        self.assertIn("设备冲突", feedback)

    def test_validated_status_stays_when_editor_content_unchanged(self) -> None:
        status, dirty = apply_validation_regression_rule(
            "validated",
            {"equipment_id": "EQ-1", "step": 1},
            {"equipment_id": "EQ-1", "step": 1},
        )
        self.assertEqual(status, "validated")
        self.assertFalse(dirty)

    def test_validated_status_resets_when_editor_content_changes(self) -> None:
        status, dirty = apply_validation_regression_rule(
            "validated",
            {"equipment_id": "EQ-1", "step": 1},
            {"equipment_id": "EQ-1", "step": 2},
        )
        self.assertEqual(status, "created")
        self.assertTrue(dirty)


if __name__ == "__main__":
    unittest.main()
