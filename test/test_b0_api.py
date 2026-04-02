import os
import unittest
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests


BASE_URL = os.getenv("LINECONTROL_BACKEND_URL", "http://127.0.0.1:18000").rstrip("/")
XML_PATH = Path(__file__).resolve().parents[1] / "resource" / "order_valid.xml"
ORDER_ID = "PO-20260206-01"


class B0ApiTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        try:
            response = requests.get(f"{BASE_URL}/healthz", timeout=3)
            response.raise_for_status()
        except requests.RequestException as exc:
            raise unittest.SkipTest(f"后端未启动或不可访问: {exc}") from exc

    def test_healthz(self) -> None:
        response = requests.get(f"{BASE_URL}/healthz", timeout=3)
        self.assertEqual(response.status_code, 200)

    def test_import_local_order(self) -> None:
        payload = XML_PATH.read_bytes()
        response = requests.post(
            f"{BASE_URL}/orders/import_local",
            data=payload,
            headers={"Content-Type": "application/xml"},
            timeout=10,
        )
        self.assertEqual(response.status_code, 200, response.text)

        body = self._as_dict(response)
        self.assertIn("passed", body)
        self.assertIn("errors", body)
        self.assertIn("risks", body)
        self.assertIsInstance(body["errors"], list)
        self.assertIsInstance(body["risks"], list)

    def test_imported_order_can_be_queried(self) -> None:
        self._import_order()
        response = requests.get(f"{BASE_URL}/orders/{ORDER_ID}", timeout=10)
        self.assertEqual(response.status_code, 200, response.text)

        body = self._as_dict(response)
        self.assertEqual(body.get("header", {}).get("order_id"), ORDER_ID)
        self.assertIsInstance(body.get("lines"), list)

    def test_order_lines_can_create_lot(self) -> None:
        self._import_order()
        line_ids = self._extract_order_line_ids(ORDER_ID)
        self.assertTrue(line_ids, "导入成功后未发现可用于建批的订单行。")

        response = requests.post(
            f"{BASE_URL}/lots/import_lines",
            json={
                "order_id": ORDER_ID,
                "selected_order_line_ids": line_ids[:2],
            },
            timeout=10,
        )
        self.assertEqual(response.status_code, 200, response.text)

        body = self._as_dict(response)
        lot_id = body.get("lot_id") or body.get("id")
        self.assertTrue(lot_id, body)

    def test_lot_validate_returns_passed_errors_and_risks(self) -> None:
        self._import_order()
        line_ids = self._extract_order_line_ids(ORDER_ID)
        lot_id = self._create_lot(ORDER_ID, line_ids[:2])

        response = requests.post(f"{BASE_URL}/lots/{lot_id}/validate", timeout=10)
        self.assertEqual(response.status_code, 200, response.text)

        body = self._as_dict(response)
        self.assertIn("passed", body)
        self.assertIn("errors", body)
        self.assertIn("risks", body)
        self.assertIsInstance(body["errors"], list)
        self.assertIsInstance(body["risks"], list)

    def test_list_endpoints_are_reachable_after_import(self) -> None:
        self._import_order()
        line_ids = self._extract_order_line_ids(ORDER_ID)
        self._create_lot(ORDER_ID, line_ids[:2])

        orders_response = requests.get(f"{BASE_URL}/orders/list", timeout=10)
        self.assertEqual(orders_response.status_code, 200, orders_response.text)
        orders_body = self._as_dict(orders_response)
        self.assertIsInstance(orders_body.get("production_order_list"), list)

        lots_response = requests.get(f"{BASE_URL}/lots/list", timeout=10)
        self.assertEqual(lots_response.status_code, 200, lots_response.text)
        lots_body = self._as_dict(lots_response)
        self.assertIsInstance(lots_body.get("lots"), list)

    def _import_order(self) -> str:
        payload = XML_PATH.read_bytes()
        response = requests.post(
            f"{BASE_URL}/orders/import_local",
            data=payload,
            headers={"Content-Type": "application/xml"},
            timeout=10,
        )
        self.assertEqual(response.status_code, 200, response.text)
        body = self._as_dict(response)
        self.assertIn("passed", body)
        return ORDER_ID

    def _extract_order_line_ids(self, order_id: str) -> List[int]:
        response = requests.get(f"{BASE_URL}/orders/{order_id}", timeout=10)
        self.assertEqual(response.status_code, 200, response.text)
        body = self._as_dict(response)

        candidate_keys = ("lines", "order_lines", "items")
        lines: List[Dict[str, Any]] = []
        for key in candidate_keys:
            value = body.get(key)
            if isinstance(value, list):
                lines = [item for item in value if isinstance(item, dict)]
                if lines:
                    break

        line_ids: List[int] = []
        for line in lines:
            value = line.get("id") or line.get("line_id") or line.get("order_line_id")
            if value is None:
                continue
            try:
                line_ids.append(int(value))
            except (TypeError, ValueError):
                continue
        return line_ids

    def _create_lot(self, order_id: str, line_ids: List[int]) -> str:
        self.assertTrue(line_ids, "建批前缺少订单行。")
        response = requests.post(
            f"{BASE_URL}/lots/import_lines",
            json={
                "order_id": order_id,
                "selected_order_line_ids": line_ids,
            },
            timeout=10,
        )
        self.assertEqual(response.status_code, 200, response.text)
        body = self._as_dict(response)
        lot_id: Optional[Any] = body.get("lot_id") or body.get("id")
        self.assertTrue(lot_id, body)
        return str(lot_id)

    def _as_dict(self, response: requests.Response) -> Dict[str, Any]:
        try:
            body = response.json()
        except ValueError as exc:
            self.fail(f"响应不是合法 JSON: {response.text}")  # pragma: no cover
            raise exc
        self.assertIsInstance(body, dict)
        return body


if __name__ == "__main__":
    unittest.main()
