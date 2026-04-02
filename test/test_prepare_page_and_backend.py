import unittest
from unittest.mock import Mock, patch

from prepare_page import (
    EQUIPMENT_PARAM_LABELS,
    MESH_PARAM_FIELDS,
    MESH_PARAM_LABELS,
    MATERIAL_PARAM_LABELS,
    INK_PARAM_LABELS,
    build_mesh_list_item_text,
    build_non_mesh_list_item_text,
    preprocess_svg,
    svg_to_data_url,
    coerce_mesh_field_value,
    looks_like_svg_content,
    normalize_svg_markup,
    PreparePage,
    validate_svg_xml,
)
from routine_page import ProcessRoutePage
from utilities.prep_utils import (
    build_constraint_context,
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

    def test_build_empty_context_tolerates_string_constraint_context(self) -> None:
        context = build_empty_prep_instruction_context(
            {
                "process_route_context": {
                    "process_route_header": {
                        "process_route_id": "ROUTE-1",
                        "process_route_version": 2,
                        "production_line_id": "LINE-ROUTE",
                    }
                },
                "constraint_context": "legacy free-form text",
            }
        )
        header = context["prep_instruction_header"]
        self.assertEqual(header["process_route_id"], "ROUTE-1")
        self.assertEqual(header["production_line_id"], "LINE-ROUTE")

    def test_build_empty_context_prefers_constraint_context_production_line(self) -> None:
        context = build_empty_prep_instruction_context(
            {
                "process_route_context": {
                    "process_route_header": {
                        "process_route_id": "ROUTE-1",
                        "process_route_version": 2,
                        "production_line_id": "LINE-ROUTE",
                    }
                },
                "constraint_context": {
                    "raw_text": "line locked",
                    "production_line_id": "LINE-CONSTRAINT",
                },
            }
        )
        header = context["prep_instruction_header"]
        self.assertEqual(header["production_line_id"], "LINE-CONSTRAINT")

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

    def test_build_constraint_context_returns_dict_schema(self) -> None:
        result = build_constraint_context(
            {"production_line_id": "LINE-1"},
            " keep line locked ",
        )
        self.assertEqual(
            result,
            {
                "raw_text": "keep line locked",
                "production_line_id": "LINE-1",
            },
        )

    def test_mesh_param_labels_cover_expected_fields(self) -> None:
        self.assertEqual(MESH_PARAM_LABELS["mesh_prep_line_id"], "网版准备行ID")
        self.assertEqual(MESH_PARAM_LABELS["tension"], "张力")
        self.assertNotIn("pattern_design", MESH_PARAM_LABELS)
        self.assertNotIn("pattern_design", MESH_PARAM_FIELDS)

    def test_generic_param_labels_are_all_chinese(self) -> None:
        self.assertEqual(MATERIAL_PARAM_LABELS["material_prep_instruction_line_id"], "物料准备行ID")
        self.assertEqual(INK_PARAM_LABELS["recipe"], "配方")
        self.assertEqual(EQUIPMENT_PARAM_LABELS["node_id"], "节点ID")

    def test_build_mesh_list_item_text_prefers_mesh_id_then_process_plan_id(self) -> None:
        self.assertEqual(
            build_mesh_list_item_text({"mesh_prep_line_id": "MESH-LINE-1", "process_plan_id": "PLAN-1"}, 0),
            "MESH-LINE-1",
        )
        self.assertEqual(
            build_mesh_list_item_text({"process_plan_id": "PLAN-2"}, 1),
            "PLAN-2",
        )

    def test_build_non_mesh_list_item_text_uses_expected_priority(self) -> None:
        self.assertEqual(
            build_non_mesh_list_item_text("equipment_prep", {"node_id": "NODE-1", "equipment_prep_instruction_line_id": "EQ-1"}, 0),
            "NODE-1",
        )
        self.assertEqual(
            build_non_mesh_list_item_text("material_prep", {"sku": "SKU-1"}, 0),
            "SKU-1",
        )
        self.assertEqual(
            build_non_mesh_list_item_text("ink_prep", {"material_name": "白墨"}, 0),
            "白墨",
        )

    def test_coerce_mesh_field_value_converts_numeric_fields(self) -> None:
        self.assertEqual(coerce_mesh_field_value("mesh_count", "12"), 12)
        self.assertEqual(coerce_mesh_field_value("tension", "12.5"), 12.5)
        self.assertEqual(coerce_mesh_field_value("mesh_count", "12x"), "12x")
        self.assertEqual(coerce_mesh_field_value("material", " 尼龙 "), "尼龙")

    def test_svg_helper_detects_and_normalizes_svg_markup(self) -> None:
        raw_svg = '<?xml version="1.0"?><svg width="10" height="10"></svg>'
        self.assertTrue(looks_like_svg_content(raw_svg))
        self.assertEqual(normalize_svg_markup(raw_svg), '<svg width="10" height="10"></svg>')
        self.assertFalse(looks_like_svg_content("not-svg"))
        self.assertEqual(normalize_svg_markup("not-svg"), "")

    def test_preprocess_svg_normalizes_references_and_ids(self) -> None:
        raw_svg = (
            '<?xml version="1.0"?>'
            '<svg xmlns:xlink="http://www.w3.org/1999/xlink">'
            '<defs><linearGradient id="grad" /></defs>'
            '<rect fill="url(#grad)" xlink:href="#grad" />'
            "</svg>"
        )
        processed = preprocess_svg(raw_svg, "prefix_")
        self.assertIn('id="prefix_grad"', processed)
        self.assertIn("url(#prefix_grad)", processed)
        self.assertIn('href="#prefix_grad"', processed)

    def test_validate_svg_xml_reports_invalid_svg(self) -> None:
        self.assertIsNone(validate_svg_xml('<svg width="10"></svg>'))
        self.assertIsNotNone(validate_svg_xml('<svg width="10">'))

    def test_svg_to_data_url_builds_embedded_source(self) -> None:
        result = svg_to_data_url('<svg width="10"></svg>')
        self.assertTrue(result.startswith("data:image/svg+xml;base64,"))

    def test_reset_validation_state_after_edit_resets_status_and_summary(self) -> None:
        page = PreparePage.__new__(PreparePage)
        page.page_state = {
            "dirty": False,
            "page_status": "validated",
            "validation_summary": {"passed": True, "errors": ["x"], "risks": ["y"]},
            "current_instruction_set": {"prep_instruction_header": {"status": "validated"}},
        }
        page._reset_validation_state_after_edit()
        self.assertTrue(page.page_state["dirty"])
        self.assertEqual(page.page_state["page_status"], "created")
        self.assertEqual(page.page_state["current_instruction_set"]["prep_instruction_header"]["status"], "created")
        self.assertEqual(
            page.page_state["validation_summary"],
            {"passed": False, "errors": [], "risks": []},
        )

    def test_selected_line_index_prefers_page_state_row(self) -> None:
        class DummyList:
            def currentRow(self) -> int:
                return -1

        page = PreparePage.__new__(PreparePage)
        page.page_state = {
            "active_tab": "mesh_prep",
            "selected_object_row": 0,
            "current_instruction_set": {"mesh_prep_instruction_line": [{}, {}, {}, {}]},
        }
        page.listObjects = DummyList()
        self.assertEqual(page._selected_line_index(), 0)

    def test_selected_line_index_returns_invalid_when_row_out_of_range(self) -> None:
        class DummyList:
            def currentRow(self) -> int:
                return 2

        page = PreparePage.__new__(PreparePage)
        page.page_state = {
            "active_tab": "mesh_prep",
            "selected_object_row": 5,
            "current_instruction_set": {"mesh_prep_instruction_line": [{}, {}]},
        }
        page.listObjects = DummyList()
        self.assertEqual(page._selected_line_index(), 0)

    def test_force_render_current_object_updates_selected_row(self) -> None:
        class DummyList:
            def currentRow(self) -> int:
                return 1

        page = PreparePage.__new__(PreparePage)
        page.page_state = {"selected_object_row": None}
        page.listObjects = DummyList()
        page._updating_widgets = False
        page._last_selected_row = None
        called = {"rendered": False}
        page._render_instruction_editor = lambda: called.__setitem__("rendered", True)
        page._force_render_current_object()
        self.assertEqual(page.page_state["selected_object_row"], 1)
        self.assertEqual(page._last_selected_row, 1)
        self.assertTrue(called["rendered"])

    def test_selected_line_index_non_mesh_tab_keeps_invalid_row(self) -> None:
        class DummyList:
            def currentRow(self) -> int:
                return -1

        page = PreparePage.__new__(PreparePage)
        page.page_state = {
            "active_tab": "equipment_prep",
            "selected_object_row": 5,
            "current_instruction_set": {"equipment_prep_instruction_line": [{}, {}]},
        }
        page.listObjects = DummyList()
        self.assertEqual(page._selected_line_index(), -1)

    def test_coerce_generic_field_value_handles_numeric_and_recipe_json(self) -> None:
        page = PreparePage.__new__(PreparePage)
        page.page_state = {"active_tab": "material_prep"}
        self.assertEqual(page._coerce_generic_field_value("quantity", "12"), 12)
        page.page_state = {"active_tab": "ink_prep"}
        page._current_lines = lambda: [{"recipe": {"配比": {"A": 90}, "关联loop_id": ["L03"]}}]
        page._selected_line_index = lambda: 0
        self.assertEqual(page._coerce_generic_field_value("quantity", "12.5"), 12.5)
        self.assertEqual(
            page._coerce_generic_field_value("recipe", '{"A": 1}'),
            {"配比": {"A": 1}, "关联loop_id": ["L03"]},
        )
        page.page_state = {"active_tab": "equipment_prep"}
        self.assertEqual(page._coerce_generic_field_value("mesh_index", "3"), 3)

    def test_render_mesh_editor_falls_back_to_first_row_when_lines_exist(self) -> None:
        class DummyList:
            def __init__(self) -> None:
                self._row = -1

            def count(self) -> int:
                return 1

            def currentRow(self) -> int:
                return self._row

            def setCurrentRow(self, row: int) -> None:
                self._row = row

        page = PreparePage.__new__(PreparePage)
        page.page_state = {
            "active_tab": "mesh_prep",
            "active_target_id": "",
            "selected_object_row": None,
            "current_instruction_set": {
                "mesh_prep_instruction_line": [{"mesh_prep_line_id": "MESH-001", "pattern_design": "<svg></svg>"}]
            },
        }
        page.listObjects = DummyList()
        page._last_selected_row = None
        page._updating_widgets = False
        page.lblInstructionTarget = type("Label", (), {"setText": lambda self, text: setattr(self, "text", text)})()
        called = {"preview": None, "table": None}
        page._render_mesh_preview = lambda line: called.__setitem__("preview", line)
        page._render_mesh_param_table = lambda line: called.__setitem__("table", line)
        page._render_mesh_editor()
        self.assertEqual(page.page_state["selected_object_row"], 0)
        self.assertEqual(page._last_selected_row, 0)
        self.assertEqual(called["preview"]["mesh_prep_line_id"], "MESH-001")

    def test_format_ink_recipe_for_display_shows_only_ratio_for_chinese_ratio_key(self) -> None:
        page = PreparePage.__new__(PreparePage)
        rendered = page._format_ink_recipe_for_display(
            {
                "用途": "打底",
                "配比": {"临昊666打底浆": 91, "硬化剂": 4, "水": 5},
                "关联loop_id": ["L03"],
                "循环次数": {"L03": 4},
            }
        )
        self.assertIn("临昊666打底浆", rendered)
        self.assertNotIn("关联loop_id", rendered)
        self.assertNotIn("循环次数", rendered)
        self.assertNotIn("用途", rendered)

    def test_format_ink_recipe_for_display_shows_only_ratio_for_english_component_keys(self) -> None:
        page = PreparePage.__new__(PreparePage)
        rendered = page._format_ink_recipe_for_display(
            {"components": [{"name": "白墨", "ratio": 60}], "loop_id": ["L01"]}
        )
        self.assertIn('"name": "白墨"', rendered)
        self.assertNotIn("loop_id", rendered)

    def test_format_ink_recipe_for_display_keeps_non_ratio_payloads_compatible(self) -> None:
        page = PreparePage.__new__(PreparePage)
        rendered = page._format_ink_recipe_for_display({"viscosity": "medium", "temperature": "25C"})
        self.assertIn('"viscosity"', rendered)
        self.assertIn('"temperature"', rendered)
        self.assertEqual(page._format_ink_recipe_for_display("raw"), "raw")
        self.assertEqual(page._format_ink_recipe_for_display(""), "")

    def test_merge_ink_recipe_ratio_edit_updates_only_ratio_substructure(self) -> None:
        page = PreparePage.__new__(PreparePage)
        merged = page._merge_ink_recipe_ratio_edit(
            {"用途": "打底", "配比": {"A": 90, "B": 10}, "关联loop_id": ["L03"]},
            '{"A": 80, "B": 20}',
        )
        self.assertEqual(merged["配比"], {"A": 80, "B": 20})
        self.assertEqual(merged["关联loop_id"], ["L03"])

    def test_invalid_ink_recipe_edit_restores_ratio_only_display(self) -> None:
        class DummyItem:
            def __init__(self) -> None:
                self._text = "{bad json"

            def column(self) -> int:
                return 1

            def data(self, role) -> str:
                del role
                return "recipe"

            def text(self) -> str:
                return self._text

            def setText(self, text: str) -> None:
                self._text = text

        page = PreparePage.__new__(PreparePage)
        page.page_state = {
            "active_tab": "ink_prep",
            "current_instruction_set": {
                "ink_prep_instruction_line": [
                    {
                        "recipe": {
                            "用途": "打底",
                            "配比": {"白墨": 60, "硬化剂": 40},
                            "关联loop_id": ["L03"],
                        }
                    }
                ]
            },
        }
        page._updating_generic_param_table = False
        page._updating_widgets = False
        page._generic_labels_for_active_tab = lambda: {"recipe": "配方"}
        page._current_lines = lambda: page.page_state["current_instruction_set"]["ink_prep_instruction_line"]
        page._selected_line_index = lambda: 0
        item = DummyItem()

        with patch("prepare_page.QMessageBox.warning") as warning_mock:
            page._on_generic_param_item_changed(item)

        warning_mock.assert_called_once()
        self.assertIn("白墨", item.text())
        self.assertNotIn("关联loop_id", item.text())

    def test_apply_loaded_instruction_detail_updates_page_state_and_context(self) -> None:
        page = PreparePage.__new__(PreparePage)
        page.controller = type("Controller", (), {"context": {}})()
        page.page_state = {
            "current_instruction_set": {},
            "selected_instruction_id": "",
            "selected_instruction_version": 0,
            "page_status": "created",
            "dirty": True,
            "active_target_id": "old",
            "selected_object_row": 3,
            "validation_summary": {"passed": True, "errors": ["x"], "risks": ["y"]},
        }

        page._apply_loaded_instruction_detail(
            {
                "prep_instruction_header": {
                    "prep_instruction_id": "INS-LOT-20260402-01",
                    "prep_instruction_version": 1,
                    "status": "released",
                },
                "mesh_prep_instruction_line": [{"mesh_prep_line_id": "M-1"}],
                "ink_prep_instruction_line": [],
                "material_prep_instruction_line": [],
                "equipment_prep_instruction_line": [],
            }
        )

        self.assertEqual(page.page_state["selected_instruction_id"], "INS-LOT-20260402-01")
        self.assertEqual(page.page_state["selected_instruction_version"], 1)
        self.assertEqual(page.page_state["page_status"], "released")
        self.assertFalse(page.page_state["dirty"])
        self.assertEqual(page.page_state["active_target_id"], "")
        self.assertIsNone(page.page_state["selected_object_row"])
        self.assertEqual(page.page_state["validation_summary"], {"passed": False, "errors": [], "risks": []})
        self.assertEqual(
            page.controller.context["prep_instruction_context"]["prep_instruction_header"]["prep_instruction_id"],
            "INS-LOT-20260402-01",
        )

    def test_load_target_instruction_if_needed_fetches_and_consumes_target(self) -> None:
        detail = {
            "prep_instruction_header": {
                "prep_instruction_id": "INS-LOT-20260402-01",
                "prep_instruction_version": 1,
                "status": "released",
            },
            "mesh_prep_instruction_line": [],
            "ink_prep_instruction_line": [],
            "material_prep_instruction_line": [],
            "equipment_prep_instruction_line": [],
        }
        backend = type(
            "Backend",
            (),
            {"prep_instructions": type("PrepApi", (), {"detail": Mock(return_value=detail)})()},
        )()
        page = PreparePage.__new__(PreparePage)
        page.controller = type(
            "Controller",
            (),
            {
                "context": {
                    "prepare_page_target_instruction": {
                        "prep_instruction_id": "INS-LOT-20260402-01",
                        "prep_instruction_version": 1,
                    }
                },
                "production_context": {
                    "prepare_page_target_instruction": {
                        "prep_instruction_id": "INS-LOT-20260402-01",
                        "prep_instruction_version": 1,
                    }
                },
                "backend": backend,
            },
        )()
        page.page_state = {
            "current_instruction_set": {},
            "selected_instruction_id": "",
            "selected_instruction_version": 0,
            "page_status": "created",
            "dirty": True,
            "active_target_id": "",
            "selected_object_row": None,
            "validation_summary": {"passed": True, "errors": ["x"], "risks": ["y"]},
        }

        page._load_target_instruction_if_needed()

        backend.prep_instructions.detail.assert_called_once_with("INS-LOT-20260402-01", 1)
        self.assertNotIn("prepare_page_target_instruction", page.controller.context)
        self.assertNotIn("prepare_page_target_instruction", page.controller.production_context)
        self.assertEqual(page.page_state["selected_instruction_id"], "INS-LOT-20260402-01")

    def test_load_target_instruction_if_needed_warns_and_falls_back_on_backend_error(self) -> None:
        backend = type(
            "Backend",
            (),
            {"prep_instructions": type("PrepApi", (), {"detail": Mock(side_effect=BackendError("boom"))})()},
        )()
        page = PreparePage.__new__(PreparePage)
        page.controller = type(
            "Controller",
            (),
            {
                "context": {
                    "prepare_page_target_instruction": {
                        "prep_instruction_id": "INS-LOT-20260402-01",
                        "prep_instruction_version": 1,
                    }
                },
                "production_context": {
                    "prepare_page_target_instruction": {
                        "prep_instruction_id": "INS-LOT-20260402-01",
                        "prep_instruction_version": 1,
                    }
                },
                "backend": backend,
            },
        )()
        page.page_state = {
            "current_instruction_set": {"prep_instruction_header": {"prep_instruction_id": "existing"}},
            "selected_instruction_id": "existing",
            "selected_instruction_version": 2,
            "page_status": "created",
            "dirty": False,
            "active_target_id": "",
            "selected_object_row": None,
            "validation_summary": {"passed": False, "errors": [], "risks": []},
        }

        with patch("prepare_page.QMessageBox.warning") as warning_mock:
            page._load_target_instruction_if_needed()

        warning_mock.assert_called_once()
        self.assertNotIn("prepare_page_target_instruction", page.controller.context)
        self.assertNotIn("prepare_page_target_instruction", page.controller.production_context)
        self.assertEqual(page.page_state["selected_instruction_id"], "existing")

    def test_distribute_instruction_set_jumps_to_monitor_before_backend_call(self) -> None:
        call_order = []

        def _show_page(page_name: str) -> None:
            call_order.append(f"show:{page_name}")

        def _distribute(_payload):
            call_order.append("distribute")
            return {
                "passed": True,
                "errors": [],
                "risks": [],
                "prep_instruction_id": "INS-1",
                "prep_instruction_version": 1,
                "status": "released",
            }

        backend = type(
            "Backend",
            (),
            {
                "prep_instructions": type(
                    "PrepApi",
                    (),
                    {
                        "distribute": Mock(side_effect=_distribute),
                        "detail": Mock(
                            return_value={
                                "prep_instruction_header": {
                                    "prep_instruction_id": "INS-1",
                                    "prep_instruction_version": 1,
                                    "status": "released",
                                },
                                "mesh_prep_instruction_line": [],
                                "ink_prep_instruction_line": [],
                                "material_prep_instruction_line": [],
                                "equipment_prep_instruction_line": [],
                            }
                        ),
                    },
                )()
            },
        )()
        page = PreparePage.__new__(PreparePage)
        page.controller = type("Controller", (), {"backend": backend, "show_page": Mock(side_effect=_show_page), "context": {}})()
        page.page_state = {
            "page_status": "validated",
            "current_instruction_set": {"prep_instruction_header": {"status": "validated"}},
            "selected_instruction_id": "",
            "selected_instruction_version": 0,
            "dirty": False,
            "validation_summary": {"passed": False, "errors": [], "risks": []},
        }
        page.lblValidationFeedback = type("Label", (), {"setText": lambda self, text: setattr(self, "text", text)})()
        page._save_current_editor = Mock(return_value=True)
        page._collect_payload = Mock(return_value={"prep_instruction_header": {}})
        page._update_validation_summary = Mock()
        page._sync_context = Mock()
        page._render_page = Mock()

        with patch("prepare_page.QMessageBox.information"):
            page._distribute_instruction_set()

        self.assertEqual(call_order[:2], ["show:monitor_page", "distribute"])
        page.controller.show_page.assert_called_once_with("monitor_page")
        self.assertEqual(page.page_state["selected_instruction_id"], "INS-1")
        self.assertEqual(page.page_state["selected_instruction_version"], 1)
        self.assertEqual(
            page.controller.context["prep_instruction_context"]["prep_instruction_header"]["prep_instruction_id"],
            "INS-1",
        )

    def test_distribute_instruction_set_keeps_validation_gate_before_navigation(self) -> None:
        backend = type("Backend", (), {"prep_instructions": type("PrepApi", (), {"distribute": Mock()})()})()
        page = PreparePage.__new__(PreparePage)
        page.controller = type("Controller", (), {"backend": backend, "show_page": Mock(), "context": {}})()
        page.page_state = {"page_status": "created"}
        page._save_current_editor = Mock(return_value=True)

        with patch("prepare_page.QMessageBox.warning") as warning_mock:
            page._distribute_instruction_set()

        warning_mock.assert_called_once()
        page.controller.show_page.assert_not_called()
        backend.prep_instructions.distribute.assert_not_called()

    def test_distribute_instruction_set_still_warns_on_backend_error_after_navigation(self) -> None:
        backend = type(
            "Backend",
            (),
            {"prep_instructions": type("PrepApi", (), {"distribute": Mock(side_effect=BackendError("boom"))})()},
        )()
        page = PreparePage.__new__(PreparePage)
        page.controller = type("Controller", (), {"backend": backend, "show_page": Mock(), "context": {}})()
        page.page_state = {"page_status": "validated"}
        page.lblValidationFeedback = type("Label", (), {"setText": lambda self, text: setattr(self, "text", text)})()
        page._save_current_editor = Mock(return_value=True)
        page._collect_payload = Mock(return_value={"prep_instruction_header": {}})

        with patch("prepare_page.QMessageBox.warning") as warning_mock:
            page._distribute_instruction_set()

        page.controller.show_page.assert_called_once_with("monitor_page")
        warning_mock.assert_called_once()

    def test_no_debug_1144_string_left_in_source(self) -> None:
        with open("prepare_page.py", "r", encoding="utf-8") as file_obj:
            content = file_obj.read()
        self.assertNotIn("1144", content)


class ProcessRoutePageNextStepUnitTest(unittest.TestCase):
    def test_on_next_allows_navigation_without_validation(self) -> None:
        page = ProcessRoutePage.__new__(ProcessRoutePage)
        controller = type(
            "Controller",
            (),
            {
                "context": {},
                "production_context": {},
                "show_page": Mock(),
            },
        )()
        page.controller = controller
        page.page_state = {"page_status": "created"}
        page._sync_process_route_context = Mock()
        page._approve_and_refresh = Mock(return_value=True)

        page._on_next()

        page._approve_and_refresh.assert_not_called()
        page._sync_process_route_context.assert_called_once_with()
        controller.show_page.assert_called_once_with("prepare_page")
        self.assertEqual(
            controller.context["prepare_page_target_instruction"],
            {"prep_instruction_id": "INS-LOT-20260402-01", "prep_instruction_version": 1},
        )
        self.assertEqual(
            controller.production_context["prepare_page_target_instruction"],
            {"prep_instruction_id": "INS-LOT-20260402-01", "prep_instruction_version": 1},
        )

    def test_on_next_validated_route_still_approves_before_navigation(self) -> None:
        page = ProcessRoutePage.__new__(ProcessRoutePage)
        controller = type(
            "Controller",
            (),
            {
                "context": {},
                "production_context": {},
                "show_page": Mock(),
            },
        )()
        page.controller = controller
        page.page_state = {"page_status": "validated"}
        page._sync_process_route_context = Mock()
        page._approve_and_refresh = Mock(return_value=True)

        page._on_next()

        page._approve_and_refresh.assert_called_once_with(show_message=False)
        controller.show_page.assert_called_once_with("prepare_page")


if __name__ == "__main__":
    unittest.main()
