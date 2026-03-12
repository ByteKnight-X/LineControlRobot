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
    LOT_VALIDATE = "/lots/{lot_id}/validate"
    LOTS_IMPORT_LINES = "/lots/import_lines"
    AI_OPTIMIZE_LOTS = "/ai/optimize_lots"
    AI_VALIDATE_PENDING_LOTS = "/ai/validate_pending_lots"


class WorkflowRoutes:
    GENERATE_ROUTE = "/tasks/{task_id}/generate_route"
    GENERATE_PREP = "/tasks/{task_id}/generate_prep"
    DISPATCH_PREP = "/tasks/{task_id}/dispatch_prep"


class ProcessPlanRoutes:
    LIST = "/process_plan/list"
    DETAIL = "/process_plan/{process_plan_id}-{process_plan_version}"
    VALIDATE = "/process_plan/validate"
    APPROVE = "/process_plan/approve"


class BackendClient:
    """Shared backend transport with domain-specific API groups."""

    def __init__(self, base_url: Optional[str] = None) -> None:
        default_url = "http://127.0.0.1:18000"
        self.base_url = (base_url or os.getenv("LINECONTROL_BACKEND_URL") or default_url).rstrip("/")
        self.imports = ImportApi(self)
        self.workflow = WorkflowApi(self)
        self.process_plans = ProcessPlanApi(self)

    def _get_json(self, path: str, params: Optional[Dict[str, Any]] = None, timeout: int = 10) -> Dict[str, Any]:
        try:
            response = requests.get(self._url(path), params=params, timeout=timeout)
        except requests.RequestException as exc:
            raise BackendError(str(exc)) from exc
        return self._decode(response)

    def _post_json(self, path: str, payload: Optional[Dict[str, Any]] = None, timeout: int = 15) -> Dict[str, Any]:
        try:
            response = requests.post(self._url(path), json=payload or {}, timeout=timeout)
        except requests.RequestException as exc:
            raise BackendError(str(exc)) from exc
        return self._decode(response)

    def _post_xml(self, path: str, payload: bytes, timeout: int = 20) -> Dict[str, Any]:
        headers = {"Content-Type": "application/xml"}
        try:
            response = requests.post(self._url(path), data=payload, headers=headers, timeout=timeout)
        except requests.RequestException as exc:
            raise BackendError(str(exc)) from exc
        return self._decode(response)

    def _url(self, path: str) -> str:
        if path.startswith("http://") or path.startswith("https://"):
            return path
        if not path.startswith("/"):
            path = f"/{path}"
        return f"{self.base_url}{path}"

    def _decode(self, response: requests.Response) -> Dict[str, Any]:
        if not response.ok:
            raise BackendError(f"状态码: {response.status_code}\n{response.text}")
        try:
            data = response.json()
        except ValueError as exc:
            raise BackendError("后端返回的不是合法 JSON。") from exc
        if not isinstance(data, dict):
            raise BackendError("后端返回的数据结构不是对象。")
        return data


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

    def optimize_lots(
        self,
        order_id: str,
        selected_order_line_ids: Optional[List[int]] = None,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "order_id": order_id,
            "dry_run": dry_run,
        }
        if selected_order_line_ids:
            payload["selected_order_line_ids"] = selected_order_line_ids
        return self._client._post_json(ImportRoutes.AI_OPTIMIZE_LOTS, payload)

    def validate_pending_lots(self) -> Dict[str, Any]:
        return self._client._post_json(ImportRoutes.AI_VALIDATE_PENDING_LOTS)


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
        return [item for item in process_plans if isinstance(item, dict)]

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
        return data

    def validate(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        data = self._client._post_json(ProcessPlanRoutes.VALIDATE, payload)
        required_keys = ("passed", "errors", "risks")
        if any(key not in data for key in required_keys):
            raise BackendError("后端返回的校验结果结构无效。")
        return data

    def approve(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        data = self._client._post_json(ProcessPlanRoutes.APPROVE, payload)
        required_keys = ("approved", "process_plan_id", "process_plan_version", "status", "errors", "risks")
        if any(key not in data for key in required_keys):
            raise BackendError("后端返回的批准结果结构无效。")
        return data
