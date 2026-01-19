from PyQt5 import QtWidgets, uic
from PyQt5.QtWidgets import QGraphicsScene, QGraphicsRectItem, QGraphicsLineItem, QGraphicsSimpleTextItem
from PyQt5.QtGui import QPen, QBrush, QColor, QPainter, QPolygonF
from PyQt5.QtCore import QRectF, QPointF, Qt, QEvent
from utilities.constants import DEFAULT_ROUTINE_LISTS
import xml.etree.ElementTree as ET
from pathlib import Path
from PyQt5.QtWidgets import QGraphicsSimpleTextItem
import requests, json
from PyQt5.QtWidgets import QMessageBox


# Simple Node item (rect with text)
class NodeItem(QGraphicsRectItem):
    def __init__(self, rect: QRectF, text: str):
        super().__init__(rect)
        self.node_text = text  # Save node text
        self.setBrush(QBrush(QColor("#4A90E2")))  # Blue background
        self.setPen(QPen(QColor("#1A3D6D"), 3))   # Dark blue border, width 3
        self.setRect(rect)
        self.setFlag(QGraphicsRectItem.ItemIsSelectable, True)
        self.setFlag(QGraphicsRectItem.ItemIsMovable, True)

        # Rounded corner drawing (override paint method)
        self.round_radius = 24

        # Aesthetic text
        txt = QGraphicsSimpleTextItem(text, self)
        font = txt.font()
        font.setPointSize(24)
        font.setBold(True)
        txt.setFont(font)
        txt.setBrush(QBrush(QColor("#fff")))  # White font
        txt_rect = txt.boundingRect()
        txt.setPos(rect.x() + (rect.width() - txt_rect.width())/2,
                   rect.y() + (rect.height() - txt_rect.height())/2)

        # Ensure the text item does NOT consume mouse events so clicks go to the parent NodeItem
        txt.setAcceptedMouseButtons(Qt.NoButton)
        txt.setAcceptHoverEvents(False)

        # Make sure parent item can still receive mouse events
        self.setAcceptHoverEvents(True)

    def paint(self, painter, option, widget=None):
        # Draw rounded rectangle
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(self.brush())
        painter.setPen(self.pen())
        painter.drawRoundedRect(self.rect(), self.round_radius, self.round_radius)

    def mousePressEvent(self, ev):
        print("Clicked node:", self.node_text)
        QtWidgets.QMessageBox.information(None, "设备信息", f"{self.node_text}")
        super().mousePressEvent(ev)


class RoutinePage(QtWidgets.QWidget):
    """Routine page."""

    def __init__(self, controller):
        """Initialize routine page UI and logic."""
        super().__init__()
        uic.loadUi("forms/routine_page.ui", self)
        self.controller = controller
        self.setup_ui()
    
    def setup_ui(self) -> None:
        """Setup UI elements and event handlers."""
        # Only consider btnMeshPreparation
        self.create_flow()
        self.btnNextStep.clicked.connect(self.next_step)

    def create_flow(self) -> None:
        """Load production_line.xml and render flow graph with loops in flowGraphicsView.
        蛇形布局：每行最多5个节点，奇偶行反向排列。
        Loop的矩形框需包含所有loop路径上的节点。
        """
        scene = QGraphicsScene(self)
        self.flowGraphicsView.setScene(scene)
        self.flowGraphicsView.setRenderHint(QPainter.Antialiasing)

        self._enable_interaction()
        route = self.controller.context.get("route")
        root = ET.fromstring(route)
        ns = {"gml": "http://graphml.graphdrawing.org/xmlns"}

        nodes_data = {}  # id -> {deviceId, deviceType, instruction}
        edges_data = []  # list of {source, target, edgeType, loopCount}

        graph = root.find("gml:graph", ns)
        for node in graph.findall("gml:node", ns):
            nid = node.get("id")
            data = {}
            for d in node.findall("gml:data", ns):
                key = d.get("key")
                if key == "k_deviceId":
                    data["deviceId"] = d.text
                elif key == "k_deviceType":
                    data["deviceType"] = d.text
                elif key == "k_instruction":
                    data["instruction"] = d.text
            nodes_data[nid] = data

        for edge in graph.findall("gml:edge", ns):
            src = edge.get("source")
            tgt = edge.get("target")
            etype = None
            lcount = None
            for d in edge.findall("gml:data", ns):
                key = d.get("key")
                if key == "k_edgeType":
                    etype = d.text
                elif key == "k_loopCount":
                    lcount = int(d.text) if d.text else None
            edges_data.append({"source": src, "target": tgt, "edgeType": etype, "loopCount": lcount})

        color_map = {
            "上料工作站": "#4CAF50",
            "丝印工作站": "#2196F3",
            "烘干机": "#FF9800",
            "下料工作站": "#9C27B0"
        }

        # 蛇形布局参数
        node_w, node_h = 280, 120
        gap_x = 200
        gap_y = 120
        start_x = 80

        total_nodes = len(nodes_data)
        max_per_row = 7
        start_y = 40  # 顶部内边距

        node_items = {}
        node_positions = {}

        ordered_ids = list(nodes_data.keys())
        for i, nid in enumerate(ordered_ids):
            row = i // max_per_row
            col = i % max_per_row
            # 左上起点，奇偶行蛇形
            if row % 2 == 0:
                x = start_x + col * (node_w + gap_x)
            else:
                x = start_x + (max_per_row - 1 - col) * (node_w + gap_x)
            y = start_y + row * (node_h + gap_y)
            rect = QRectF(x, y, node_w, node_h)
            dtype = nodes_data[nid].get("deviceType", "")
            color = color_map.get(dtype, "#4A90E2")
            node_item = NodeItem(rect, dtype)
            node_item.setBrush(QBrush(QColor(color)))
            node_item.node_text = nodes_data[nid].get("instruction", dtype)
            scene.addItem(node_item)
            node_items[nid] = node_item
            node_positions[nid] = rect.center()

            # 在每个节点上方显示id
            id_text = QGraphicsSimpleTextItem(str(nid), node_item)
            font = id_text.font()
            font.setPointSize(12)
            font.setBold(False)
            id_text.setFont(font)
            id_text.setBrush(QBrush(QColor("#222")))
            id_rect = id_text.boundingRect()
            id_text.setPos(
                rect.x() + (rect.width() - id_rect.width()) / 2,
                rect.y() - id_rect.height() - 4
            )
        # --- Loop分组：收集所有loop边，按loop分组，找到loop路径上的所有节点 ---
        # 1. 找所有loop边，按loopCount分组
        loop_edges = []
        forward_edges = []
        for e in edges_data:
            if e.get("edgeType") == "loop" and e.get("loopCount"):
                loop_edges.append(e)
            elif e.get("edgeType") == "forward":
                forward_edges.append(e)

        # 2. 构建 forward 邻接表（假定主干为线性或每节点至多一条 forward 出边）
        fwd_next = {}   # node_id -> next_node_id
        fwd_prev = {}   # node_id -> prev_node_id
        for e in forward_edges:
            s, t = e["source"], e["target"]
            fwd_next[s] = t
            fwd_prev[t] = s

        # 3. 对每个 loop 边，沿 forward 从 tgt 走到 src，收集所有节点（包含端点）
        loop_groups = []  # 每项: {"nodes": [id, ...], "loopCount": N}
        visited_loops = set()
        for e in loop_edges:
            src, tgt, lcount = e["source"], e["target"], e["loopCount"]
            if (src, tgt) in visited_loops:
                continue

            path_nodes = []
            cur = tgt
            safety = 0
            max_steps = len(nodes_data) + 5

            # 先从 tgt 开始，沿 forward 累加直到到达 src 或终止
            while cur is not None and safety < max_steps:
                path_nodes.append(cur)
                if cur == src:
                    break
                cur = fwd_next.get(cur)  # 顺主干向前
                safety += 1

            # 如果没能到达 src（可能因数据不线性），尝试从 src 逆向找回 tgt
            if path_nodes and path_nodes[-1] != src:
                path_nodes = []
                cur = src
                safety = 0
                while cur is not None and safety < max_steps:
                    path_nodes.append(cur)
                    if cur == tgt:
                        break
                    cur = fwd_prev.get(cur)  # 逆主干向后
                    safety += 1
                # 逆向得到的是 src→...→tgt，翻转为 tgt→...→src
                path_nodes.reverse()

            # 兜底：若仍不包含两端点，则至少记录 [tgt, src]
            if not path_nodes or path_nodes[0] != tgt or path_nodes[-1] != src:
                path_nodes = [tgt, src]

            loop_groups.append({"nodes": path_nodes, "loopCount": lcount})
            visited_loops.add((src, tgt))

        # --- 画forward边 ---
        for e in forward_edges:
            src_id = e["source"]
            tgt_id = e["target"]
            if src_id not in node_positions or tgt_id not in node_positions:
                continue
            src_rect = node_items[src_id].rect()
            tgt_rect = node_items[tgt_id].rect()
            p1 = QPointF(src_rect.right(), src_rect.center().y())
            p2 = QPointF(tgt_rect.left(), tgt_rect.center().y())
            src_row = ordered_ids.index(src_id) // max_per_row
            tgt_row = ordered_ids.index(tgt_id) // max_per_row
            if src_row != tgt_row:
                p1 = QPointF(src_rect.center().x(), src_rect.bottom())
                p2 = QPointF(tgt_rect.center().x(), tgt_rect.top())
            elif src_row % 2 == 1:
                p1 = QPointF(src_rect.left(), src_rect.center().y())
                p2 = QPointF(tgt_rect.right(), tgt_rect.center().y())
            self._draw_arrow(scene, p1, p2, QColor("#333"), 4)

        # --- 画loop分组的矩形框（包含所有loop路径节点） ---
        for group in loop_groups:
            node_ids = group["nodes"]
            lcount = group["loopCount"]
            rects = [node_items[nid].rect() for nid in node_ids if nid in node_items]
            if not rects:
                continue
            left = min(r.left() for r in rects) - 20
            top = min(r.top() for r in rects) - 20
            right = max(r.right() for r in rects) + 20
            bottom = max(r.bottom() for r in rects) + 20
            loop_rect = QRectF(left, top, right - left, bottom - top)
            loop_box = QGraphicsRectItem(loop_rect)
            loop_box.setPen(QPen(QColor("#E91E63"), 3, Qt.DashLine))
            loop_box.setBrush(QBrush(Qt.transparent))
            scene.addItem(loop_box)
            label = QGraphicsSimpleTextItem(f"×{lcount}")
            label.setBrush(QBrush(QColor("#E91E63")))
            font = label.font()
            font.setPointSize(18)
            font.setBold(True)
            label.setFont(font)
            label_rect = label.boundingRect()
            label.setPos(loop_rect.right() - label_rect.width() - 10,
                         loop_rect.top() - label_rect.height() - 5)
            scene.addItem(label)

        # 缩放流程图，占满整个视图
        self.flowGraphicsView.scale(0.5, 0.5)

    def _draw_arrow(self, scene, p1: QPointF, p2: QPointF, color: QColor, width: int):
        """Draw straight line with arrow head."""
        line = QGraphicsLineItem(p1.x(), p1.y(), p2.x(), p2.y())
        line.setPen(QPen(color, width))
        scene.addItem(line)
        
        direction = p2 - p1
        self._draw_arrow_head(scene, p2, direction, color)

    def _draw_arrow_head(self, scene, tip: QPointF, direction: QPointF, color: QColor):
        """Draw arrow head at tip pointing in direction."""
        length = (direction.x()**2 + direction.y()**2)**0.5
        if length == 0:
            return
        ux, uy = direction.x()/length, direction.y()/length
        ah = 12.0
        perp_x, perp_y = -uy, ux
        left = QPointF(tip.x() - ux*ah + perp_x*(ah/2), tip.y() - uy*ah + perp_y*(ah/2))
        right = QPointF(tip.x() - ux*ah - perp_x*(ah/2), tip.y() - uy*ah - perp_y*(ah/2))
        poly = QPolygonF([tip, left, right])
        scene.addPolygon(poly, QPen(color), QBrush(color))

    def _bezier_curve(self, p0: QPointF, p1: QPointF, p2: QPointF, steps: int):
        """Generate points along quadratic Bezier curve."""
        points = []
        for i in range(steps + 1):
            t = i / steps
            x = (1-t)**2 * p0.x() + 2*(1-t)*t * p1.x() + t**2 * p2.x()
            y = (1-t)**2 * p0.y() + 2*(1-t)*t * p1.y() + t**2 * p2.y()
            points.append(QPointF(x, y))
        return points

    def _enable_interaction(self) -> None:
        """Add zoom and pan to flowGraphicsView."""
        gv = self.flowGraphicsView
        # Pan: hold left mouse to select items; hold middle mouse or set drag mode for right button
        gv.setDragMode(QtWidgets.QGraphicsView.ScrollHandDrag)
        gv.setTransformationAnchor(QtWidgets.QGraphicsView.AnchorUnderMouse)
        gv.setResizeAnchor(QtWidgets.QGraphicsView.AnchorViewCenter)
        gv.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)

        # Install event filter for mouse wheel zoom
        if not hasattr(self, "_wheel_filter_installed"):
            gv.viewport().installEventFilter(self)
            self._wheel_filter_installed = True

        # Optional: keyboard shortcuts for zoom in/out and reset
        QtWidgets.QShortcut(Qt.Key_Plus, gv, activated=lambda: gv.scale(1.2, 1.2))
        QtWidgets.QShortcut(Qt.Key_Minus, gv, activated=lambda: gv.scale(1/1.2, 1/1.2))
        QtWidgets.QShortcut(Qt.Key_0, gv, activated=self._reset_view)

    def _fit_view(self, bbox) -> None:
        """Fit once after building scene; do not override user zoom later."""
        self.flowGraphicsView.fitInView(bbox, Qt.KeepAspectRatio)

    def _reset_view(self):
        scene = self.flowGraphicsView.scene()
        if not scene:
            return
        bbox = scene.itemsBoundingRect().adjusted(-50, -50, 50, 50)
        self.flowGraphicsView.resetTransform()
        self.flowGraphicsView.fitInView(bbox, Qt.KeepAspectRatio)

    def eventFilter(self, obj, event):
        """Wheel zoom: Ctrl+Wheel or plain wheel to zoom; Shift+Wheel for horizontal pan."""
        
        if obj is self.flowGraphicsView.viewport() and event.type() == QEvent.Wheel:
            # Zoom factor
            zoom_in_factor = 1.15
            zoom_out_factor = 1.0 / zoom_in_factor
            delta = event.angleDelta().y()
            factor = zoom_in_factor if delta > 0 else zoom_out_factor
            # Apply zoom
            self.flowGraphicsView.scale(factor, factor)
            return True  # Consume event
        return super().eventFilter(obj, event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
    
    def next_step(self):
        """Proceed to the next step in the workflow."""
        layering = self.controller.context.get("layering_data") or {}
        task_id = layering.get("task_id")
        if not task_id:
            QMessageBox.warning(self, "缺少 task_id", "未找到 task_id，无法确认工艺路线。")
            return

        url = f"http://127.0.0.1:8000/tasks/{task_id}/generate_prep"
        payload = {
            "approved": True,
            "route": self.controller.context.get("route"),
            "separation_plan": layering.get("separationPlan"),
            "sop": layering.get("sop"),
        }
        try:
            resp = requests.post(url, json=payload, timeout=10)
        except Exception as exc:
            QMessageBox.critical(self, "请求失败", str(exc))
            return

        if not resp.ok:
            QMessageBox.critical(self, "确认失败", f"状态码: {resp.status_code}\n{resp.text}")
            return

        try:
            data = resp.json()
            # store full response for later pages (prep instructions, etc.)
            self.controller.context["prep_instructions"] = data
            pretty = json.dumps(data, ensure_ascii=False, indent=2)
            QMessageBox.information(self, "工艺路线确认成功", pretty)
        except Exception:
            self.controller.context["prep_instructions"] = resp.text
            QMessageBox.information(self, "工艺路线确认成功", resp.text)

        # navigate to prepare page
        print(f"{self.controller.context["prep_instructions"]}")
        self.controller.show_page("prepare_page", self.controller.btnPrepare)