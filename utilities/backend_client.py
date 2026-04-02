import os
from typing import Any, Dict, List, Optional

import requests


class BackendError(RuntimeError):
    """Raised when the backend returns an error or invalid response."""


class ImportRoutes:
    HEALTHZ = "/healthz"
    ORDERS_LIST = "/orders/list"
    ORDER_DETAIL = "/orders/{order_id}"
    ORDER_VALIDATE = "/orders/{order_id}/validate"
    ORDER_IMPORT_LOCAL = "/orders/import_local"
    LOTS_LIST = "/lots/list"
    LOT_DETAIL = "/lots/{lot_id}"
    LOTS_COMMIT = "/lots/commit"
    LOT_VALIDATE = "/lots/{lot_id}/validate"
    LOTS_IMPORT_LINES = "/lots/import_lines"
    AI_GENERATE_LOTS = "/ai/generate_lots"
    AI_VALIDATE_LOTS = "/ai/validate_lots"


class WorkflowRoutes:
    GENERATE_ROUTE = "/tasks/{task_id}/generate_route"
    GENERATE_PREP = "/tasks/{task_id}/generate_prep"
    DISPATCH_PREP = "/tasks/{task_id}/dispatch_prep"


class ProcessPlanRoutes:
    LIST = "/process_plan/list"
    DETAIL = "/process_plan/{process_plan_id}-{process_plan_version}"
    VALIDATE = "/process_plan/validate"
    APPROVE = "/process_plan/approve"


class ProcessRouteRoutes:
    LIST = "/process_route/list"
    DETAIL = "/process_route/{process_route_id}/{process_route_version}"
    VALIDATE = "/process_route/validate"
    APPROVE = "/process_route/approve"


class PrepInstructionRoutes:
    LIST = "/prep_instruction/list"
    DETAIL = "/prep_instruction/{prep_instruction_id}/{prep_instruction_version}"
    VALIDATE = "/prep_instruction/validate"
    DISTRIBUTE = "/prep_instruction/distribute_instruction"


class BackendClient:
    """Shared backend transport with domain-specific API groups."""

    def __init__(self, base_url: Optional[str] = None) -> None:
        default_url = "http://127.0.0.1:18000"
        self.base_url = (base_url or os.getenv("LINECONTROL_BACKEND_URL") or default_url).rstrip("/")
        self.imports = ImportApi(self)
        self.workflow = WorkflowApi(self)
        self.process_plans = ProcessPlanApi(self)
        self.process_routes = ProcessRouteApi(self)
        self.prep_instructions = PrepInstructionApi(self)

    def _get_json(self, path: str, params: Optional[Dict[str, Any]] = None, timeout: int = 10) -> Dict[str, Any]:
        try:
            response = requests.get(self._url(path), params=params, timeout=timeout)
        except requests.RequestException as exc:
            raise BackendError(str(exc)) from exc
        data = self._decode_any(response)
        if not isinstance(data, dict):
            raise BackendError("后端返回的数据结构不是对象。")
        return data

    def _post_json(self, path: str, payload: Optional[Dict[str, Any]] = None, timeout: int = 15) -> Dict[str, Any]:
        try:
            response = requests.post(self._url(path), json=payload or {}, timeout=timeout)
        except requests.RequestException as exc:
            raise BackendError(str(exc)) from exc
        data = self._decode_any(response)
        if not isinstance(data, dict):
            raise BackendError("后端返回的数据结构不是对象。")
        return data

    def _get_data(
        self,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        timeout: int = 10,
    ) -> Any:
        try:
            response = requests.get(self._url(path), params=params, timeout=timeout)
        except requests.RequestException as exc:
            raise BackendError(str(exc)) from exc
        return self._decode_any(response)

    def _post_data(self, path: str, payload: Optional[Dict[str, Any]] = None, timeout: int = 15) -> Any:
        try:
            response = requests.post(self._url(path), json=payload or {}, timeout=timeout)
        except requests.RequestException as exc:
            raise BackendError(str(exc)) from exc
        return self._decode_any(response)

    def _post_xml(self, path: str, payload: bytes, timeout: int = 20) -> Dict[str, Any]:
        headers = {"Content-Type": "application/xml"}
        try:
            response = requests.post(self._url(path), data=payload, headers=headers, timeout=timeout)
        except requests.RequestException as exc:
            raise BackendError(str(exc)) from exc
        data = self._decode_any(response)
        if not isinstance(data, dict):
            raise BackendError("后端返回的数据结构不是对象。")
        return data

    def _url(self, path: str) -> str:
        if path.startswith("http://") or path.startswith("https://"):
            return path
        if not path.startswith("/"):
            path = f"/{path}"
        return f"{self.base_url}{path}"

    def _decode_any(self, response: requests.Response) -> Any:
        if not response.ok:
            raise BackendError(f"状态码: {response.status_code}\n{response.text}")
        try:
            data = response.json()
        except ValueError as exc:
            raise BackendError("后端返回的不是合法 JSON。") from exc
        return data


def _normalize_issue_messages(value: Any, field_name: str) -> List[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise BackendError(f"后端返回的 {field_name} 结构无效。")
    messages: List[str] = []
    for index, item in enumerate(value, start=1):
        if isinstance(item, dict):
            field = str(item.get("field") or "").strip()
            message = str(item.get("message") or "").strip()
            if not message:
                raise BackendError(f"后端返回的 {field_name} 结构无效：第 {index} 项缺少 message。")
            messages.append(f"{field}: {message}" if field else message)
            continue
        if isinstance(item, str):
            text = item.strip()
            if text:
                messages.append(text)
            continue
        raise BackendError(f"后端返回的 {field_name} 结构无效：第 {index} 项类型错误。")
    return messages


def _normalize_sizes_list(value: Any, field_name: str) -> List[int]:
    if value in (None, ""):
        return []
    if isinstance(value, list):
        items = value
    else:
        raise BackendError(f"后端返回的 {field_name} 结构无效。")
    normalized: List[int] = []
    for index, item in enumerate(items, start=1):
        try:
            normalized.append(int(item))
        except (TypeError, ValueError) as exc:
            raise BackendError(f"后端返回的 {field_name} 结构无效：第 {index} 项不是整数。") from exc
    return normalized


class ImportApi:
    """B0 import-related endpoints: orders, lots, and AI split validation."""

    def __init__(self, client: BackendClient) -> None:
        self._client = client

    def healthz(self) -> Dict[str, Any]:
        return self._client._get_json(ImportRoutes.HEALTHZ)

    def list_orders(self) -> Dict[str, Any]:
        return self._client._get_json(ImportRoutes.ORDERS_LIST)

    def get_order(self, order_id: str) -> Dict[str, Any]:
        return self._client._get_json(ImportRoutes.ORDER_DETAIL.format(order_id=order_id))

    def import_local_order(self, xml_bytes: bytes) -> Dict[str, Any]:
        return self._client._post_xml(ImportRoutes.ORDER_IMPORT_LOCAL, xml_bytes)

    def validate_order(self, order_id: str) -> Dict[str, Any]:
        return self._client._post_json(ImportRoutes.ORDER_VALIDATE.format(order_id=order_id))

    def list_lots(self) -> Dict[str, Any]:
        return self._client._get_json(ImportRoutes.LOTS_LIST)

    def get_lot(self, lot_id: str) -> Dict[str, Any]:
        return self._client._get_json(ImportRoutes.LOT_DETAIL.format(lot_id=lot_id))

    def commit_lot(self, pending_lot: Dict[str, Any]) -> Dict[str, Any]:
        data = self._client._post_json(
            ImportRoutes.LOTS_COMMIT,
            {"pending_lot": pending_lot},
        )
        lot_id = data.get("lot_id")
        if not lot_id:
            raise BackendError("提交批次结果结构无效：缺少 lot_id。")
        if "passed" not in data:
            raise BackendError("提交批次结果结构无效：缺少 passed。")
        data["error_info"] = data.get("error_info") if isinstance(data.get("error_info"), list) else []
        data["risk_info"] = data.get("risk_info") if isinstance(data.get("risk_info"), list) else []
        return data

    def import_lines_to_lot(
        self,
        order_id: str,
        selected_order_line_ids: List[int],
        lot_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "order_id": order_id,
            "selected_order_line_ids": selected_order_line_ids,
        }        
        if lot_id:
            payload["lot_id"] = lot_id
        return self._client._post_json(ImportRoutes.LOTS_IMPORT_LINES, payload)

    def validate_lot(self, lot_id: str) -> Dict[str, Any]:
        return self._client._post_json(ImportRoutes.LOT_VALIDATE.format(lot_id=lot_id))

    def generate_lots(
        self,
        selected_orders: List[str],
        excluded_order_lines: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        data = self._client._post_json(
            ImportRoutes.AI_GENERATE_LOTS,
            {
                "selected_orders": selected_orders,
                "excluded_order_lines": excluded_order_lines or [],
            },
        )
        lots = data.get("lots")
        if not isinstance(lots, list):
            raise BackendError("候选批次单结构无效。")
        for index, item in enumerate(lots):
            if not isinstance(item, dict):
                raise BackendError(f"候选批次单结构无效：第 {index + 1} 个候选项不是对象。")
            header = item.get("lot_header")
            lines = item.get("lot_line")
            if not isinstance(header, dict):
                raise BackendError(f"候选批次单结构无效：第 {index + 1} 个候选项缺少 lot_header。")
            if not isinstance(lines, list):
                raise BackendError(f"候选批次单结构无效：候选批次 {header.get('lot_id', index + 1)} 缺少 lot_line 列表。")
            if not header.get("lot_id"):
                raise BackendError(f"候选批次单结构无效：第 {index + 1} 个候选项缺少 lot_header.lot_id。")
            if not header.get("source_order_id"):
                raise BackendError(
                    f"候选批次单结构无效：候选批次 {header.get('lot_id', index + 1)} 缺少 lot_header.source_order_id。"
                )
            if not header.get("production_line_id"):
                raise BackendError(
                    f"候选批次单结构无效：候选批次 {header.get('lot_id')} 缺少 lot_header.production_line_id。"
                )
            if "progress" not in header:
                raise BackendError(
                    f"候选批次单结构无效：候选批次 {header.get('lot_id')} 缺少 lot_header.progress。"
                )
            try:
                float(header.get("progress"))
            except (TypeError, ValueError):
                raise BackendError(
                    f"候选批次单结构无效：候选批次 {header.get('lot_id')} 的 lot_header.progress 不是数字。"
                )
            if not header.get("status"):
                raise BackendError(
                    f"候选批次单结构无效：候选批次 {header.get('lot_id')} 缺少 lot_header.status。"
                )
            for line_index, line in enumerate(lines, start=1):
                if not isinstance(line, dict):
                    raise BackendError(
                        f"候选批次单结构无效：候选批次 {header.get('lot_id')} 的第 {line_index} 条 lot_line 不是对象。"
                    )
                required_fields = (
                    "lot_id",
                    "lot_line_id",
                    "source_order_id",
                    "source_order_line_id",
                    "sku",
                    "color",
                    "separation_plan_id",
                    "separation_plan_version",
                    "size",
                    "quantity_planned",
                    "status",
                )
                for field in required_fields:
                    if line.get(field) in (None, ""):
                        raise BackendError(
                            f"候选批次单结构无效：候选批次 {header.get('lot_id')} 的第 {line_index} 条 lot_line 缺少 {field}。"
                        )
        return data

    def validate_lots(self, pending_lots: List[Dict[str, Any]]) -> Dict[str, Any]:
        data = self._client._post_json(
            ImportRoutes.AI_VALIDATE_LOTS,
            {"pending_lots": pending_lots},
        )
        results = data.get("validation_results")
        if not isinstance(results, list):
            raise BackendError("候选批次单校验结果结构无效。")
        normalized_results: List[Dict[str, Any]] = []
        for index, item in enumerate(results):
            if not isinstance(item, dict):
                raise BackendError(f"候选批次单校验结果结构无效：第 {index + 1} 个结果不是对象。")
            lot_id = item.get("lot_id")
            if not lot_id:
                raise BackendError(f"候选批次单校验结果结构无效：第 {index + 1} 个结果缺少 lot_id。")
            if "passed" not in item:
                raise BackendError(f"候选批次单校验结果结构无效：批次 {lot_id} 缺少 passed。")
            normalized_item = dict(item)
            errors = normalized_item.get("errors")
            risk_info = normalized_item.get("risk_info")
            normalized_item["errors"] = errors if isinstance(errors, list) else []
            normalized_item["risk_info"] = risk_info if isinstance(risk_info, list) else []
            normalized_results.append(normalized_item)
        data["validation_results"] = normalized_results
        return data


class WorkflowApi:
    """Workflow endpoints used by pages after import."""

    def __init__(self, client: BackendClient) -> None:
        self._client = client

    def generate_route(self, task_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._client._post_json(WorkflowRoutes.GENERATE_ROUTE.format(task_id=task_id), payload)

    def generate_prep(self, task_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._client._post_json(WorkflowRoutes.GENERATE_PREP.format(task_id=task_id), payload)

    def dispatch_prep(self, task_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._client._post_json(WorkflowRoutes.DISPATCH_PREP.format(task_id=task_id), payload)


class ProcessPlanApi:
    """Process-plan endpoints used by SeparationPage."""

    def __init__(self, client: BackendClient) -> None:
        self._client = client

    def list(self) -> List[Dict[str, Any]]:
        data = self._client._get_json(ProcessPlanRoutes.LIST)
        process_plans = data.get("process_plans")
        if not isinstance(process_plans, list):
            raise BackendError("后端返回的历史方案列表结构无效。")
        normalized: List[Dict[str, Any]] = []
        for index, item in enumerate(process_plans, start=1):
            if not isinstance(item, dict):
                raise BackendError(f"后端返回的历史方案列表结构无效：第 {index} 项不是对象。")
            normalized_item = dict(item)
            normalized_item["sizes"] = _normalize_sizes_list(normalized_item.get("sizes"), "process_plans[].sizes")
            normalized.append(normalized_item)
        return normalized

    def detail(self, process_plan_id: str, process_plan_version: int) -> Dict[str, Any]:
        data = self._client._get_json(
            ProcessPlanRoutes.DETAIL.format(
                process_plan_id=process_plan_id,
                process_plan_version=process_plan_version,
            )
        )
        if not isinstance(data.get("process_plan_header"), dict) or not isinstance(
            data.get("process_plan_line"), list
        ):
            raise BackendError("后端返回的方案详情结构无效。")
        header = dict(data["process_plan_header"])
        header["sizes"] = _normalize_sizes_list(header.get("sizes"), "process_plan_header.sizes")
        lines: List[Dict[str, Any]] = []
        for index, item in enumerate(data["process_plan_line"], start=1):
            if not isinstance(item, dict):
                raise BackendError(f"后端返回的方案详情结构无效：第 {index} 条方案行不是对象。")
            lines.append(dict(item))
        data["process_plan_header"] = header
        data["process_plan_line"] = lines
        return data

    def validate(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        data = self._client._post_json(ProcessPlanRoutes.VALIDATE, payload)
        required_keys = ("passed", "errors", "risks", "status")
        if any(key not in data for key in required_keys):
            raise BackendError("后端返回的校验结果结构无效。")
        data["errors"] = _normalize_issue_messages(data.get("errors"), "errors")
        data["risks"] = _normalize_issue_messages(data.get("risks"), "risks")
        return data

    def approve(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        data = self._client._post_json(ProcessPlanRoutes.APPROVE, payload)
        required_keys = ("approved", "process_plan_id", "process_plan_version", "status", "errors", "risks")
        if any(key not in data for key in required_keys):
            raise BackendError("后端返回的批准结果结构无效。")
        data["errors"] = _normalize_issue_messages(data.get("errors"), "errors")
        data["risks"] = _normalize_issue_messages(data.get("risks"), "risks")
        return data


class ProcessRouteApi:
    """Process-route endpoints used by ProcessRoutePage."""

    def __init__(self, client: BackendClient) -> None:
        self._client = client

    def list(self) -> List[Dict[str, Any]]:
        data = self._client._get_data(ProcessRouteRoutes.LIST)
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
        if isinstance(data, dict):
            for key in ("process_routes", "items", "data", "list"):
                value = data.get(key)
                if isinstance(value, list):
                    return [item for item in value if isinstance(item, dict)]
        raise BackendError("后端返回的工艺路线列表结构无效。")

    def detail(self, process_route_id: str, process_route_version: int) -> Dict[str, Any]:
        data = self._client._get_json(
            ProcessRouteRoutes.DETAIL.format(
                process_route_id=process_route_id,
                process_route_version=process_route_version,
            )
        )
        return self._normalize_detail(data)

    def validate(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        data = self._client._post_json(ProcessRouteRoutes.VALIDATE, payload)
        required_keys = ("passed", "errors", "risks")
        if any(key not in data for key in required_keys):
            raise BackendError("后端返回的工艺路线校验结果结构无效。")
        return data

    def approve(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        data = self._client._post_json(ProcessRouteRoutes.APPROVE, payload)
        required_keys = ("passed", "errors", "risks", "process_route_id", "process_route_version")
        if any(key not in data for key in required_keys):
            raise BackendError("后端返回的工艺路线批准结果结构无效。")
        if "status" not in data:
            data["status"] = "validated"
        return data

    def _normalize_detail(self, data: Dict[str, Any]) -> Dict[str, Any]:
        header = data.get("process_route_header")
        if not isinstance(header, dict):
            header = data.get("process_router_header")
        loops = data.get("process_route_loop_line")
        steps = data.get("process_route_loop_step_line")
        if not isinstance(steps, list):
            steps = data.get("process_route_loop_step")

        if not isinstance(header, dict) or not isinstance(loops, list) or not isinstance(steps, list):
            raise BackendError("后端返回的工艺路线详情结构无效。")

        return {
            "process_route_header": header,
            "process_route_loop_line": [item for item in loops if isinstance(item, dict)],
            "process_route_loop_step_line": [item for item in steps if isinstance(item, dict)],
        }


class PrepInstructionApi:
    """Production-preparation endpoints used by PreparePage."""

    def __init__(self, client: BackendClient) -> None:
        self._client = client

    def list(self) -> List[Dict[str, Any]]:
        data = self._client._get_data(PrepInstructionRoutes.LIST)
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
        if isinstance(data, dict):
            for key in ("prep_instructions", "items", "data", "list"):
                value = data.get(key)
                if isinstance(value, list):
                    return [item for item in value if isinstance(item, dict)]
        raise BackendError("后端返回的生产准备列表结构无效。")

    def detail(self, prep_instruction_id: str, prep_instruction_version: int) -> Dict[str, Any]:
        data = self._client._get_json(
            PrepInstructionRoutes.DETAIL.format(
                prep_instruction_id=prep_instruction_id,
                prep_instruction_version=prep_instruction_version,
            )
        )
        return self._normalize_detail(data)

    def validate(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        data = self._client._post_json(PrepInstructionRoutes.VALIDATE, payload)
        required_keys = ("passed", "errors", "risks")
        if any(key not in data for key in required_keys):
            raise BackendError("后端返回的生产准备校验结果结构无效。")
        return data

    def distribute(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        data = self._client._post_json(PrepInstructionRoutes.DISTRIBUTE, payload)
        required_keys = ("passed", "errors", "risks", "prep_instruction_id", "prep_instruction_version")
        if any(key not in data for key in required_keys):
            raise BackendError("后端返回的生产准备下发结果结构无效。")
        if "status" not in data:
            data["status"] = "released"
        return data

    def _normalize_detail(self, data: Dict[str, Any]) -> Dict[str, Any]:
        header = data.get("prep_instruction_header")
        mesh_lines = data.get("mesh_prep_instruction_line")
        ink_lines = data.get("ink_prep_instruction_line")
        material_lines = data.get("material_prep_instruction_line")
        equipment_lines = data.get("equipment_prep_instruction_line")

        if not isinstance(header, dict):
            raise BackendError("后端返回的生产准备详情结构无效。")
        if not all(
            isinstance(value, list)
            for value in (mesh_lines, ink_lines, material_lines, equipment_lines)
        ):
            raise BackendError("后端返回的生产准备详情结构无效。")

        return {
            "prep_instruction_header": dict(header),
            "mesh_prep_instruction_line": [item for item in mesh_lines if isinstance(item, dict)],
            "ink_prep_instruction_line": [item for item in ink_lines if isinstance(item, dict)],
            "material_prep_instruction_line": [item for item in material_lines if isinstance(item, dict)],
            "equipment_prep_instruction_line": [item for item in equipment_lines if isinstance(item, dict)],
        }
