import json
from typing import Any, Dict, Optional


TAB_KEY_TO_FIELD = {
    "mesh_prep": "mesh_prep_instruction_line",
    "material_prep": "material_prep_instruction_line",
    "ink_prep": "ink_prep_instruction_line",
    "equipment_prep": "equipment_prep_instruction_line",
}

TAB_KEY_TO_TITLE = {
    "mesh_prep": "网版准备指令",
    "material_prep": "物料准备指令",
    "ink_prep": "油墨胶浆准备指令",
    "equipment_prep": "设备准备指令",
}

STATUS_TEXT = {
    "created": "草稿",
    "validated": "已校验",
    "released": "已下发",
    "finished": "已完成",
}


def safe_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def build_constraint_context(route_header: Dict[str, Any], raw_text: Any) -> Dict[str, str]:
    if not isinstance(route_header, dict):
        route_header = {}
    return {
        "raw_text": safe_text(raw_text),
        "production_line_id": (
            safe_text(route_header.get("production_line_id"))
            or safe_text(route_header.get("line_spec_id"))
        ),
    }


def build_empty_prep_instruction_context(controller_context: Dict[str, Any]) -> Dict[str, Any]:
    lot_header = controller_context.get("lot_context", {}).get("lot_header", {})
    route_header = controller_context.get("process_route_context", {}).get("process_route_header", {})
    raw_constraint_context = controller_context.get("constraint_context", {})
    constraint_context = raw_constraint_context if isinstance(raw_constraint_context, dict) else {}
    production_line_id = (
        safe_text(constraint_context.get("production_line_id"))
        or safe_text(route_header.get("production_line_id"))
        or safe_text(route_header.get("line_spec_id"))
    )
    return {
        "prep_instruction_header": {
            "lot_id": safe_text(lot_header.get("lot_id")),
            "production_line_id": production_line_id,
            "process_route_id": safe_text(route_header.get("process_route_id")),
            "process_route_version": safe_int(route_header.get("process_route_version"), 0),
            "prep_instruction_id": "",
            "prep_instruction_version": 0,
            "approved_by": "",
            "status": "created",
        },
        "mesh_prep_instruction_line": [],
        "ink_prep_instruction_line": [],
        "material_prep_instruction_line": [],
        "equipment_prep_instruction_line": [],
    }


def normalize_prep_instruction_context(data: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    source = data or {}
    header = source.get("prep_instruction_header")
    if not isinstance(header, dict):
        header = {}
    normalized = {
        "prep_instruction_header": {
            "lot_id": safe_text(header.get("lot_id")),
            "production_line_id": safe_text(header.get("production_line_id")),
            "process_route_id": safe_text(header.get("process_route_id")),
            "process_route_version": safe_int(header.get("process_route_version"), 0),
            "prep_instruction_id": safe_text(header.get("prep_instruction_id")),
            "prep_instruction_version": safe_int(header.get("prep_instruction_version"), 0),
            "approved_by": safe_text(header.get("approved_by")),
            "status": safe_text(header.get("status")).lower() or "created",
        }
    }
    for field in TAB_KEY_TO_FIELD.values():
        value = source.get(field)
        normalized[field] = [dict(item) for item in value if isinstance(item, dict)] if isinstance(value, list) else []
    return normalized


def to_pretty_json(data: Dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True)


def parse_instruction_text(text: str) -> Dict[str, Any]:
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise ValueError("当前指令内容必须是 JSON 对象。")
    return parsed


def status_to_text(status: str) -> str:
    return STATUS_TEXT.get(safe_text(status).lower(), safe_text(status) or "未知")


def summarize_risk_text(validation_summary: Dict[str, Any]) -> str:
    risks = validation_summary.get("risks")
    if not isinstance(risks, list):
        risks = []
    return f"风险：{len(risks)}"


def build_validation_feedback(validation_summary: Dict[str, Any]) -> str:
    passed = bool(validation_summary.get("passed"))
    errors = validation_summary.get("errors")
    risks = validation_summary.get("risks")
    if not isinstance(errors, list):
        errors = []
    if not isinstance(risks, list):
        risks = []
    error_lines = [f"- {item}" for item in errors] or ["- 无"]
    risk_lines = [f"- {item}" for item in risks] or ["- 无"]
    lines = [
        f"校验结果：{'通过' if passed else '未通过'}",
        "错误：",
        *error_lines,
        "风险：",
        *risk_lines,
    ]
    return "\n".join(lines)


def identify_instruction_target(line: Dict[str, Any], fallback_index: int) -> str:
    for key in (
        "equipment_id",
        "device_id",
        "deviceId",
        "material_id",
        "materialId",
        "material_name",
        "materialName",
        "mesh_id",
        "screen_id",
        "screenId",
        "ink_id",
        "ink_material_id",
        "inkMaterialId",
        "target_id",
        "targetId",
        "instruction_id",
        "id",
        "name",
    ):
        value = safe_text(line.get(key))
        if value:
            return value
    return f"第{fallback_index + 1}项"
